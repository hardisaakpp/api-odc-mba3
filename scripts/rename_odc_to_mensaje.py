"""
Script para renombrar la columna 'odc' a 'mensaje' en la tabla pedido.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db_connection

def main():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check current column names
    cursor.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = 'pedido' AND COLUMN_NAME IN ('odc', 'mensaje')"
    )
    rows = cursor.fetchall()
    columns = [r[0] for r in rows]
    print(f"Columnas encontradas: {columns}")

    if "odc" in columns and "mensaje" not in columns:
        print("Renombrando columna odc -> mensaje...")
        cursor.execute("EXEC sp_rename 'dbo.pedido.odc', 'mensaje', 'COLUMN'")
        conn.commit()
        print("Columna renombrada exitosamente.")
    elif "mensaje" in columns:
        print("La columna ya se llama 'mensaje'. No se requiere cambio.")
    else:
        print("ERROR: No se encontro la columna 'odc' ni 'mensaje'.")

    cursor.close()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
