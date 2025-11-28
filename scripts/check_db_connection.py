"""
Script para verificar la configuración de conexión a SQL Server.

Este script muestra qué servidor y base de datos está usando la aplicación.
"""

import sys
from pathlib import Path

# Agregar src al path para importar módulos
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from config import (
    SQL_SERVER_DRIVER,
    SQL_SERVER_SERVER,
    SQL_SERVER_DATABASE,
    SQL_SERVER_UID,
    SQL_SERVER_PWD,
    SQL_SERVER_SAP_DRIVER,
    SQL_SERVER_SAP_SERVER,
    SQL_SERVER_SAP_DATABASE,
    SQL_SERVER_SAP_UID,
    SQL_SERVER_SAP_PWD
)
from database.connection import get_db_connection, get_sap_db_connection

print()
print("=" * 70)
print("🔍 VERIFICACIÓN DE CONFIGURACIÓN DE CONEXIÓN SQL SERVER")
print("=" * 70)
print()

print("📋 Configuración Servidor Principal (Almacenamiento):")
print(f"   Driver: {SQL_SERVER_DRIVER}")
print(f"   Servidor: {SQL_SERVER_SERVER}")
print(f"   Base de datos: {SQL_SERVER_DATABASE}")
if SQL_SERVER_UID:
    print(f"   Usuario: {SQL_SERVER_UID}")
    print(f"   Contraseña: {'*' * len(SQL_SERVER_PWD) if SQL_SERVER_PWD else '(vacía)'}")
else:
    print(f"   Autenticación: Windows (Trusted Connection)")
print()

print("📋 Configuración Servidor SAP (Consultas OPENQUERY):")
print(f"   Driver: {SQL_SERVER_SAP_DRIVER}")
print(f"   Servidor: {SQL_SERVER_SAP_SERVER}")
print(f"   Base de datos: {SQL_SERVER_SAP_DATABASE}")
if SQL_SERVER_SAP_UID:
    print(f"   Usuario: {SQL_SERVER_SAP_UID}")
    print(f"   Contraseña: {'*' * len(SQL_SERVER_SAP_PWD) if SQL_SERVER_SAP_PWD else '(vacía)'}")
else:
    print(f"   Autenticación: Windows (Trusted Connection)")
print()

print("=" * 70)
print("🔗 SERVIDOR PRINCIPAL (Almacenamiento)")
print("=" * 70)
try:
    conn = get_db_connection()
    
    # Obtener información de la conexión
    cursor = conn.cursor()
    
    # Obtener nombre de la base de datos actual
    cursor.execute("SELECT DB_NAME()")
    db_result = cursor.fetchone()
    current_db = db_result[0] if db_result else "UNKNOWN"
    
    # Obtener nombre del servidor
    cursor.execute("SELECT @@SERVERNAME")
    server_result = cursor.fetchone()
    server_name = server_result[0] if server_result else "UNKNOWN"
    
    # Verificar si existe la tabla producto_sap_cache
    cursor.execute("""
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_NAME = 'producto_sap_cache'
    """)
    table_result = cursor.fetchone()
    table_exists = (table_result[0] if table_result else 0) > 0
    
    # Verificar si existe la tabla pack_conversion
    cursor.execute("""
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_NAME = 'pack_conversion'
    """)
    pack_result = cursor.fetchone()
    pack_table_exists = (pack_result[0] if pack_result else 0) > 0
    
    print("✅ Conexión exitosa!")
    print()
    print("📊 Información de la conexión:")
    print(f"   Servidor conectado: {server_name}")
    print(f"   Base de datos actual: {current_db}")
    print()
    
    print("📋 Estado de las tablas SAP:")
    if pack_table_exists:
        print("   ✅ pack_conversion: EXISTE")
        cursor.execute("SELECT COUNT(*) FROM pack_conversion")
        pack_result = cursor.fetchone()
        pack_count = pack_result[0] if pack_result else 0
        print(f"      Registros: {pack_count}")
    else:
        print("   ❌ pack_conversion: NO EXISTE")
    
    if table_exists:
        print("   ✅ producto_sap_cache: EXISTE")
        cursor.execute("SELECT COUNT(*) FROM producto_sap_cache")
        cache_result = cursor.fetchone()
        cache_count = cache_result[0] if cache_result else 0
        print(f"      Registros: {cache_count}")
    else:
        print("   ❌ producto_sap_cache: NO EXISTE")
    
    print()
    
    # Verificar si la base de datos es la correcta
    if current_db.lower() != "store_control":
        print("⚠️ ADVERTENCIA:")
        print(f"   Estás conectado a la base de datos: {current_db}")
        print(f"   Pero deberías estar en: store_control")
        print()
        print("   Solución:")
        print("   Configura en tu archivo .env:")
        print(f"   SQL_SERVER_SERVER=210.17.1.54")
        print(f"   SQL_SERVER_DATABASE=store_control")
    else:
        print("✅ Base de datos correcta: store_control")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error al conectar: {e}")
    print()
    print("💡 Verifica:")
    print("   1. Que el servidor esté accesible")
    print("   2. Que las credenciales sean correctas")
    print("   3. Que la base de datos exista")
    print("   4. Tu archivo .env tenga la configuración correcta")

print()
print("=" * 70)
print("🔗 SERVIDOR SAP (Consultas OPENQUERY)")
print("=" * 70)
try:
    conn_sap = get_sap_db_connection()
    
    cursor = conn_sap.cursor()
    cursor.execute("SELECT DB_NAME()")
    db_result_sap = cursor.fetchone()
    current_db_sap = db_result_sap[0] if db_result_sap else "UNKNOWN"
    cursor.execute("SELECT @@SERVERNAME")
    server_result_sap = cursor.fetchone()
    server_name_sap = server_result_sap[0] if server_result_sap else "UNKNOWN"
    
    print("✅ Conexión exitosa!")
    print()
    print("📊 Información de la conexión:")
    print(f"   Servidor conectado: {server_name_sap}")
    print(f"   Base de datos actual: {current_db_sap}")
    print()
    
    # Verificar servidor vinculado (si es posible)
    try:
        cursor.execute("""
            SELECT name 
            FROM sys.servers 
            WHERE name = 'MYHANADB'
        """)
        linked_server = cursor.fetchone()
        if linked_server:
            print("✅ Servidor vinculado MYHANADB: CONFIGURADO")
        else:
            print("⚠️ Servidor vinculado MYHANADB: NO ENCONTRADO")
    except:
        print("⚠️ No se pudo verificar el servidor vinculado")
    
    cursor.close()
    conn_sap.close()
    
except Exception as e:
    print(f"❌ Error al conectar: {e}")
    print()
    print("💡 Verifica:")
    print("   1. Que el servidor SAP esté accesible")
    print("   2. Que las credenciales sean correctas")
    print("   3. Tu archivo .env tenga SQL_SERVER_SAP_* configurado")

print()
print("=" * 70)
print()

