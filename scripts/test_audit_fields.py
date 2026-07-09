"""
Script de pruebas para verificar que los campos de auditoria se registran correctamente.
"""

import sys
import os
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("/opt/odc-sap/.env")

from src.database.connection import get_db_connection
from src.utils.audit_context import AuditContext, get_audit_context, ORIGEN_WEB, ORIGEN_API

def test_audit_context_creation():
    """Prueba 1: Verificar creacion de AuditContext."""
    print("[TEST 1] Creacion de AuditContext")
    print("-" * 50)
    
    # Crear contexto manualmente
    audit = AuditContext(
        usuario="test_user",
        origen=ORIGEN_WEB,
        ip_origen="192.168.1.100"
    )
    
    assert audit.usuario == "test_user", "Usuario incorrecto"
    assert audit.origen == ORIGEN_WEB, "Origen incorrecto"
    assert audit.ip_origen == "192.168.1.100", "IP incorrecta"
    assert audit.get_creado_por() == "test_user", "get_creado_por() incorrecto"
    assert audit.get_modificado_por() == "test_user", "get_modificado_por() incorrecto"
    
    print("  [OK] AuditContext se crea correctamente")
    print("  [OK] Metodos get_creado_por() y get_modificado_por() funcionan")
    print()
    return True

def test_audit_context_defaults():
    """Prueba 2: Verificar valores por defecto de AuditContext."""
    print("[TEST 2] Valores por defecto de AuditContext")
    print("-" * 50)
    
    # Crear contexto sin usuario
    audit = AuditContext()
    
    assert audit.usuario == "SYSTEM", "Usuario por defecto deberia ser SYSTEM"
    assert audit.origen == ORIGEN_API, "Origen por defecto deberia ser API"
    assert audit.ip_origen is None, "IP por defecto deberia ser None"
    
    print("  [OK] Usuario por defecto: SYSTEM")
    print("  [OK] Origen por defecto: API")
    print("  [OK] IP por defecto: None")
    print()
    return True

def test_orden_compra_repository_insert():
    """Prueba 3: Verificar que OrdenCompraRepository registra campos de auditoria."""
    print("[TEST 3] OrdenCompraRepository.insert_cabecera con audit_context")
    print("-" * 50)
    
    from src.database.repositories.orden_compra_repository import OrdenCompraRepository
    
    conn = get_db_connection()
    repo = OrdenCompraRepository(conn)
    
    # Crear contexto de auditoria
    audit = AuditContext(
        usuario="test_audit_user",
        origen=ORIGEN_WEB,
        ip_origen="10.0.0.50"
    )
    
    # Datos de prueba
    datos_cabecera = {
        "despacho_id": None,
        "pedido_id": None,
        "proveedor": "TEST_PROVEEDOR_AUDIT",
        "fecha_generacion": datetime.now().date(),
        "referencia_despacho": "TEST_REF_AUDIT",
        "codigo_bodega": "TEST_BOD",
        "estado": "PRUEBA"
    }
    
    try:
        # Insertar con audit_context
        oc_id = repo.insert_cabecera(datos_cabecera, audit_context=audit)
        print(f"  [OK] OC insertada con ID: {oc_id}")
        
        # Verificar que los campos de auditoria se guardaron
        cursor = conn.cursor()
        cursor.execute("""
            SELECT creado_por, origen, ip_origen 
            FROM orden_compra_cabecera 
            WHERE oc_id = ?
        """, (oc_id,))
        
        row = cursor.fetchone()
        if row:
            creado_por, origen, ip_origen = row
            
            assert creado_por == "test_audit_user", f"creado_por incorrecto: {creado_por}"
            assert origen == ORIGEN_WEB, f"origen incorrecto: {origen}"
            assert ip_origen == "10.0.0.50", f"ip_origen incorrecto: {ip_origen}"
            
            print(f"  [OK] creado_por = {creado_por}")
            print(f"  [OK] origen = {origen}")
            print(f"  [OK] ip_origen = {ip_origen}")
        else:
            print("  [ERROR] No se encontro el registro insertado")
            return False
        
        # Limpiar: eliminar el registro de prueba
        cursor.execute("DELETE FROM orden_compra_cabecera WHERE oc_id = ?", (oc_id,))
        conn.commit()
        print(f"  [OK] Registro de prueba eliminado")
        
        cursor.close()
        
    except Exception as e:
        print(f"  [ERROR] {str(e)}")
        conn.rollback()
        conn.close()
        return False
    
    conn.close()
    print()
    return True

def test_orden_compra_update_estado():
    """Prueba 4: Verificar que update_estado registra modificado_por y modificado_fecha."""
    print("[TEST 4] OrdenCompraRepository.update_estado con audit_context")
    print("-" * 50)
    
    from src.database.repositories.orden_compra_repository import OrdenCompraRepository
    
    conn = get_db_connection()
    repo = OrdenCompraRepository(conn)
    
    # Primero insertar un registro
    audit_insert = AuditContext(
        usuario="user_creador",
        origen=ORIGEN_API,
        ip_origen="10.0.0.1"
    )
    
    datos_cabecera = {
        "despacho_id": None,
        "pedido_id": None,
        "proveedor": "TEST_UPDATE_AUDIT",
        "fecha_generacion": datetime.now().date(),
        "referencia_despacho": "TEST_UPDATE_REF",
        "codigo_bodega": "TEST_BOD",
        "estado": "PENDIENTE"
    }
    
    try:
        oc_id = repo.insert_cabecera(datos_cabecera, audit_context=audit_insert)
        print(f"  [OK] OC insertada: {oc_id}")
        
        # Ahora actualizar con otro usuario
        audit_update = AuditContext(
            usuario="user_modificador",
            origen=ORIGEN_WEB,
            ip_origen="10.0.0.99"
        )
        
        repo.update_estado(oc_id, "ENVIADA", audit_context=audit_update)
        print(f"  [OK] Estado actualizado a ENVIADA")
        
        # Verificar los campos de modificacion
        cursor = conn.cursor()
        cursor.execute("""
            SELECT creado_por, modificado_por, modificado_fecha, estado
            FROM orden_compra_cabecera 
            WHERE oc_id = ?
        """, (oc_id,))
        
        row = cursor.fetchone()
        if row:
            creado_por, modificado_por, modificado_fecha, estado = row
            
            assert creado_por == "user_creador", f"creado_por cambio incorrectamente: {creado_por}"
            assert modificado_por == "user_modificador", f"modificado_por incorrecto: {modificado_por}"
            assert modificado_fecha is not None, "modificado_fecha deberia tener valor"
            assert estado == "ENVIADA", f"estado incorrecto: {estado}"
            
            print(f"  [OK] creado_por = {creado_por} (sin cambios)")
            print(f"  [OK] modificado_por = {modificado_por}")
            print(f"  [OK] modificado_fecha = {modificado_fecha}")
            print(f"  [OK] estado = {estado}")
        else:
            print("  [ERROR] No se encontro el registro")
            return False
        
        # Limpiar
        cursor.execute("DELETE FROM orden_compra_cabecera WHERE oc_id = ?", (oc_id,))
        conn.commit()
        print(f"  [OK] Registro de prueba eliminado")
        
        cursor.close()
        
    except Exception as e:
        print(f"  [ERROR] {str(e)}")
        conn.rollback()
        conn.close()
        return False
    
    conn.close()
    print()
    return True

def test_despacho_repository():
    """Prueba 5: Verificar que DespachoRepository acepta audit_context."""
    print("[TEST 5] DespachoRepository - Verificacion de firma de metodos")
    print("-" * 50)
    
    from src.database.repositories.despacho_repository import DespachoRepository
    from src.database.repositories.despacho.despacho_cabecera_repository import DespachoCabeceraRepository
    from src.database.repositories.despacho.despacho_detalle_repository import DespachoDetalleRepository
    import inspect
    
    # Verificar que los metodos aceptan audit_context
    # DespachoCabeceraRepository.insert
    sig = inspect.signature(DespachoCabeceraRepository.insert)
    params = list(sig.parameters.keys())
    assert 'audit_context' in params, "insert() no tiene parametro audit_context"
    print(f"  [OK] DespachoCabeceraRepository.insert() acepta audit_context")
    
    # DespachoCabeceraRepository.update
    sig = inspect.signature(DespachoCabeceraRepository.update)
    params = list(sig.parameters.keys())
    assert 'audit_context' in params, "update() no tiene parametro audit_context"
    print(f"  [OK] DespachoCabeceraRepository.update() acepta audit_context")
    
    # DespachoDetalleRepository.insert_many
    sig = inspect.signature(DespachoDetalleRepository.insert_many)
    params = list(sig.parameters.keys())
    assert 'audit_context' in params, "insert_many() no tiene parametro audit_context"
    print(f"  [OK] DespachoDetalleRepository.insert_many() acepta audit_context")
    
    # DespachoRepository (facade)
    sig = inspect.signature(DespachoRepository.insert_cabecera)
    params = list(sig.parameters.keys())
    assert 'audit_context' in params, "insert_cabecera() no tiene parametro audit_context"
    print(f"  [OK] DespachoRepository.insert_cabecera() acepta audit_context")
    
    sig = inspect.signature(DespachoRepository.update_cabecera)
    params = list(sig.parameters.keys())
    assert 'audit_context' in params, "update_cabecera() no tiene parametro audit_context"
    print(f"  [OK] DespachoRepository.update_cabecera() acepta audit_context")
    
    sig = inspect.signature(DespachoRepository.insert_detalles)
    params = list(sig.parameters.keys())
    assert 'audit_context' in params, "insert_detalles() no tiene parametro audit_context"
    print(f"  [OK] DespachoRepository.insert_detalles() acepta audit_context")
    
    print()
    return True

def run_all_tests():
    """Ejecuta todas las pruebas."""
    print("=" * 60)
    print("[*] PRUEBAS DE CAMPOS DE AUDITORIA")
    print("=" * 60)
    print()
    
    tests = [
        ("AuditContext Creation", test_audit_context_creation),
        ("AuditContext Defaults", test_audit_context_defaults),
        ("OrdenCompra INSERT", test_orden_compra_repository_insert),
        ("OrdenCompra UPDATE", test_orden_compra_update_estado),
        ("Despacho INSERT/UPDATE", test_despacho_repository),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  [EXCEPTION] {str(e)}")
            failed += 1
    
    print("=" * 60)
    print(f"[*] RESULTADOS: {passed} pasaron, {failed} fallaron")
    print("=" * 60)
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
