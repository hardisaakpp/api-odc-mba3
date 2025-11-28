"""
Script para verificar y mostrar certificados SSL/TLS de un servidor.
Equivalente a: openssl s_client -connect hostname:port -showcerts

Uso:
    python scripts/check_ssl_certificate.py [hostname] [port]
    
Ejemplo:
    python scripts/check_ssl_certificate.py sapserver.local 50000
"""

import ssl
import socket
from datetime import datetime


def check_http_first(hostname, port):
    """Verifica si el puerto responde primero con HTTP antes de SSL."""
    try:
        print(f"\n🔍 Verificando si el puerto {port} es HTTP primero...")
        with socket.create_connection((hostname, port), timeout=5) as sock:
            # Intentar leer respuesta HTTP
            sock.settimeout(2)
            try:
                data = sock.recv(1024)
                if data:
                    print(f"   📄 Respuesta recibida (primeros 200 chars):")
                    print(f"   {data[:200].decode('utf-8', errors='ignore')}")
                    return True
            except socket.timeout:
                pass
        return False
    except Exception as e:
        print(f"   ⚠️  No se pudo verificar HTTP: {e}")
        return False


def check_ssl_certificate(hostname, port):
    """
    Verifica y muestra los certificados SSL/TLS de un servidor.
    Intenta múltiples configuraciones SSL para compatibilidad con servidores antiguos.
    """
    print(f"Conectando a {hostname}:{port}...")
    print("=" * 60)
    
    # Primero verificar si es HTTP
    check_http_first(hostname, port)
    
    # Lista de configuraciones SSL a intentar (de más permisiva a más restrictiva)
    ssl_configs = [
        {
            "name": "SSL/TLS sin restricciones (máxima compatibilidad)",
            "context": lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
            "options": [
                ssl.OP_NO_SSLv2,
                ssl.OP_NO_SSLv3,
            ],
            "min_version": None,  # Sin restricción mínima
            "max_version": None,  # Sin restricción máxima
            "use_sni": False,
        },
        {
            "name": "TLS 1.0+ (compatible con servidores antiguos)",
            "context": lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
            "options": [
                ssl.OP_NO_SSLv2,
                ssl.OP_NO_SSLv3,
            ],
            "min_version": ssl.TLSVersion.MINIMUM_SUPPORTED,
            "max_version": None,
            "use_sni": False,
        },
        {
            "name": "TLS 1.2+ (estándar moderno)",
            "context": lambda: ssl.create_default_context(),
            "options": [],
            "min_version": ssl.TLSVersion.TLSv1_2,
            "max_version": None,
            "use_sni": True,
        },
    ]
    
    last_error = None
    
    for config in ssl_configs:
        print(f"\n🔄 Intentando: {config['name']}...")
        try:
            # Crear contexto SSL según la configuración
            context = config["context"]()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            # Aplicar opciones
            for option in config.get("options", []):
                context.options |= option
            
            # Configurar versiones mínimas/máximas
            if config.get("min_version") is not None:
                context.minimum_version = config["min_version"]
            if config.get("max_version") is not None:
                context.maximum_version = config["max_version"]
            
            # Conectar
            with socket.create_connection((hostname, port), timeout=10) as sock:
                server_hostname = hostname if config.get("use_sni", True) else None
                with context.wrap_socket(sock, server_hostname=server_hostname) as ssock:
                    # Obtener certificado del servidor
                    cert_binary = ssock.getpeercert(binary_form=True)
                    cert_der = ssock.getpeercert()
                    
                    # Convertir a formato PEM
                    cert_pem = ssl.DER_cert_to_PEM_cert(cert_binary)
                    
                    print("\n" + "=" * 60)
                    print("✅ CONEXIÓN EXITOSA")
                    print("=" * 60)
                    print(f"Configuración usada: {config['name']}")
                    
                    print("\n📜 CERTIFICADO DEL SERVIDOR:")
                    print("-" * 60)
                    print(cert_pem)
                    
                    # Información del certificado
                    if cert_der:
                        print("\n📋 INFORMACIÓN DEL CERTIFICADO:")
                        print("-" * 60)
                        
                        # Subject
                        subject_dict = {}
                        for item in cert_der.get('subject', []):
                            if isinstance(item, tuple) and len(item) > 0:
                                key, value = item[0]
                                subject_dict[key] = value
                        print(f"Subject: {subject_dict}")
                        
                        # Issuer
                        issuer_dict = {}
                        for item in cert_der.get('issuer', []):
                            if isinstance(item, tuple) and len(item) > 0:
                                key, value = item[0]
                                issuer_dict[key] = value
                        print(f"Issuer: {issuer_dict}")
                        
                        # Fechas
                        try:
                            not_before = datetime.strptime(cert_der['notBefore'], '%b %d %H:%M:%S %Y %Z')
                            not_after = datetime.strptime(cert_der['notAfter'], '%b %d %H:%M:%S %Y %Z')
                            print(f"Válido desde: {not_before}")
                            print(f"Válido hasta: {not_after}")
                            
                            # Verificar si está expirado
                            now = datetime.now()
                            if now > not_after:
                                print(f"⚠️  CERTIFICADO EXPIRADO (hace {(now - not_after).days} días)")
                            elif now < not_before:
                                print(f"⚠️  CERTIFICADO AÚN NO VÁLIDO")
                            else:
                                days_left = (not_after - now).days
                                print(f"✅ Certificado válido ({days_left} días restantes)")
                        except Exception as e:
                            print(f"Fechas: {cert_der.get('notBefore')} - {cert_der.get('notAfter')}")
                        
                        # Versión SSL/TLS
                        print(f"\n🔐 PROTOCOLO:")
                        print(f"Versión: {ssock.version()}")
                        cipher_info = ssock.cipher()
                        if cipher_info:
                            print(f"Cipher: {cipher_info[0]}")
                            print(f"Versión del protocolo: {cipher_info[1]}")
                            print(f"Bits: {cipher_info[2]}")
                    
                    # Intentar obtener cadena de certificados
                    try:
                        cert_chain = ssock.getpeercert_chain()
                        if cert_chain and len(cert_chain) > 1:
                            print(f"\n🔗 CADENA DE CERTIFICADOS ({len(cert_chain)} certificados):")
                            for i, cert in enumerate(cert_chain[1:], 1):
                                print(f"\n--- Certificado Intermedio {i} ---")
                                cert_pem_chain = ssl.DER_cert_to_PEM_cert(cert)
                                print(cert_pem_chain)
                    except Exception as e:
                        print(f"\n⚠️  No se pudo obtener cadena de certificados: {e}")
                    
                    print("\n" + "=" * 60)
                    return  # Éxito, salir
                    
        except ssl.SSLError as e:
            last_error = e
            error_str = str(e)
            print(f"   ❌ Error SSL: {e}")
            
            # Diagnóstico adicional del error
            if "handshake failure" in error_str.lower():
                print(f"   💡 El servidor rechazó el handshake SSL")
                print(f"   💡 Posible causa: requiere autenticación mutua (certificado cliente)")
            elif "certificate" in error_str.lower():
                print(f"   💡 Error relacionado con certificados")
            elif "unsupported protocol" in error_str.lower():
                print(f"   💡 Protocolo no soportado")
            continue
        except socket.timeout:
            print(f"   ❌ Timeout")
            last_error = "Timeout"
            continue
        except Exception as e:
            last_error = e
            print(f"   ❌ Error: {e}")
            continue
    
    # Si llegamos aquí, todas las configuraciones fallaron
    print("\n" + "=" * 60)
    print("❌ NO SE PUDO ESTABLECER CONEXIÓN SSL")
    print("=" * 60)
    print(f"Último error: {last_error}")
    print("\n💡 Posibles causas:")
    print("   - El servidor requiere autenticación mutua (certificado cliente)")
    print("   - El servidor está configurado para rechazar conexiones directas SSL")
    print("   - El puerto requiere primero una conexión HTTP antes de upgrade a HTTPS")
    print("   - El servidor usa un protocolo SSL muy antiguo no soportado por Python")
    print("   - El servidor requiere headers específicos o User-Agent")
    print("\n💡 Sugerencias:")
    print("   1. Verifica conectividad básica:")
    print("      ping sapserver.local")
    print("      telnet sapserver.local 50000")
    print("\n   2. Si el servidor requiere certificado cliente:")
    print("      - Necesitas obtener el certificado cliente (.p12 o .pfx)")
    print("      - Configurarlo en el cliente SAP Service Layer")
    print("\n   3. Prueba con requests (como lo hace tu aplicación):")
    print("      python -c \"import requests; r=requests.get('https://sapserver.local:50000', verify=False, timeout=5); print(r)\"")
    print("\n   4. Verifica la configuración en .env:")
    print("      SAP_SERVICE_LAYER_VERIFY_SSL=false  # Para desarrollo con certificados autofirmados")
    print("\n   5. Si tienes OpenSSL instalado, prueba:")
    print("      openssl s_client -connect sapserver.local:50000 -showcerts")


if __name__ == "__main__":
    import sys
    
    # Parámetros por defecto
    hostname = "sapserver.local"
    port = 50000
    
    # Permitir pasar parámetros desde línea de comandos
    if len(sys.argv) > 1:
        hostname = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    check_ssl_certificate(hostname, port)

