"""
Verificacion detallada de columnas en tablas especificas.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("/opt/odc-sap/.env")

from src.database.connection import get_db_connection

def verify_table(tabla_nombre):
    """Muestra todas las columnas de una tabla."""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(f"""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = '{tabla_nombre}'
        ORDER BY ORDINAL_POSITION
    """)
    
    print(f"Columnas de [{tabla_nombre}]:")
    print("-" * 60)
    
    for row in cursor.fetchall():
        col_name, data_type, nullable, max_len = row
        tipo = f"{data_type}({max_len})" if max_len else data_type
        print(f"  {col_name:30} {tipo:20} {'NULL' if nullable == 'YES' else 'NOT NULL'}")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    tablas = ['distribucion_confirmada', 'pedido', 'orden_compra_cabecera']
    for tabla in tablas:
        verify_table(tabla)
        print()
