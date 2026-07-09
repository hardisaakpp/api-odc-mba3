"""
Script para verificar si las tablas de pedidos existen en SQL Server.
"""

import sys
import os
from pathlib import Path

# Configurar encoding para Windows
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]

# Agregar el directorio raíz del proyecto al path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import SQL_SERVER_SERVER, SQL_SERVER_DATABASE
from src.database.connection import get_db_connection

print()
print("=" * 70)
print("VERIFICACION DE TABLAS DE PEDIDOS")
print("=" * 70)
print()

# Tablas que deben existir
TABLAS_REQUERIDAS = [
    "tienda",
    "pedido",
    "pedido_detalle",
    "pedido_detalle_tienda"
]

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print(f"Conectado a: {SQL_SERVER_SERVER}/{SQL_SERVER_DATABASE}")
    print()
    
    tablas_existentes = []
    tablas_faltantes = []
    
    for tabla in TABLAS_REQUERIDAS:
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?
        """, (tabla,))
        result = cursor.fetchone()
        existe = (result[0] if result else 0) > 0
        
        if existe:
            # Contar registros
            cursor.execute(f"SELECT COUNT(*) FROM [dbo].[{tabla}]")
            count_result = cursor.fetchone()
            count = count_result[0] if count_result else 0
            tablas_existentes.append((tabla, count))
            print(f"   [OK] {tabla}: EXISTE ({count} registros)")
        else:
            tablas_faltantes.append(tabla)
            print(f"   [X] {tabla}: NO EXISTE")
    
    print()
    print("=" * 70)
    
    if tablas_faltantes:
        print("ACCION REQUERIDA:")
        print()
        print(f"   Faltan {len(tablas_faltantes)} tabla(s): {', '.join(tablas_faltantes)}")
        print()
        print("   Para crear las tablas, ejecuta el script SQL:")
        print("   scripts/create_pedido_tables.sql")
        print()
        print("   Instrucciones:")
        print("   1. Abre SQL Server Management Studio (SSMS)")
        print(f"   2. Conectate a: {SQL_SERVER_SERVER}")
        print(f"   3. Selecciona la base de datos: {SQL_SERVER_DATABASE}")
        print("   4. Abre y ejecuta: scripts/create_pedido_tables.sql")
        print()
    else:
        print("Todas las tablas existen correctamente!")
        print()
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"[ERROR] Error al verificar tablas: {e}")
    print()
    print("💡 Verifica:")
    print("   1. Que el servidor esté accesible")
    print("   2. Que las credenciales sean correctas")
    print("   3. Tu archivo .env tenga la configuración correcta")

print("=" * 70)
print()

