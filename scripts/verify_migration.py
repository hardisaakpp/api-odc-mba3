"""
Script para verificar que las columnas de auditoria se agregaron correctamente.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("/opt/odc-sap/.env")

from src.database.connection import get_db_connection

def verify_columns():
    """Verifica las columnas de auditoria en las tablas."""
    
    tablas = [
        'pedido',
        'pedido_detalle', 
        'pedido_detalle_tienda',
        'tienda',
        'orden_compra_cabecera',
        'orden_compra_detalle',
        'despacho_cabecera',
        'despacho_detalle',
        'sku_homologacion',
        'remision_cabecera',
        'archivo_plantilla',
        'distribucion_confirmada'
    ]
    
    campos_auditoria = [
        'creado_por',
        'creado_fecha', 
        'modificado_por',
        'modificado_fecha',
        'origen',
        'ip_origen'
    ]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("=" * 80)
    print("[*] Verificacion de campos de auditoria")
    print("=" * 80)
    print()
    
    for tabla in tablas:
        cursor.execute(f"""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = '{tabla}'
            AND COLUMN_NAME IN ('creado_por', 'creado_fecha', 'modificado_por', 
                               'modificado_fecha', 'origen', 'ip_origen',
                               'created_at', 'updated_at')
            ORDER BY COLUMN_NAME
        """)
        
        columnas = [row[0] for row in cursor.fetchall()]
        
        print(f"[{tabla}]")
        print(f"  Campos encontrados: {', '.join(columnas) if columnas else 'ninguno'}")
        
        # Verificar cuales faltan
        campos_esperados = set(campos_auditoria)
        campos_existentes = set(columnas)
        
        # Mapear created_at -> creado_fecha si existe
        if 'created_at' in campos_existentes:
            campos_existentes.add('creado_fecha')
        if 'updated_at' in campos_existentes:
            campos_existentes.add('modificado_fecha')
        
        faltantes = campos_esperados - campos_existentes
        if faltantes:
            print(f"  Campos faltantes: {', '.join(faltantes)}")
        else:
            print(f"  [OK] Todos los campos de auditoria presentes")
        print()
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    verify_columns()
