"""
Script temporal para ejecutar la migracion de campos de auditoria.
Usa la conexion existente del proyecto para evitar problemas con caracteres especiales.
"""

import sys
import os
import re

# Agregar el directorio raiz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("/opt/odc-sap/.env")

from src.database.connection import get_db_connection

def run_migration():
    """Ejecuta la migracion SQL."""
    
    # Leer el archivo SQL
    sql_file = os.path.join(
        os.path.dirname(__file__), 
        "migrations", 
        "add_audit_fields_complete.sql"
    )
    
    with open(sql_file, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    # Dividir por GO (con regex para manejar diferentes saltos de linea)
    # GO debe estar solo en una linea
    batches = re.split(r'\r?\nGO\r?\n', sql_content)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("=" * 70)
    print("[*] Ejecutando migracion: add_audit_fields_complete.sql")
    print("=" * 70)
    print()
    
    successful_batches = 0
    skipped_batches = 0
    failed_batches = 0
    
    for i, batch in enumerate(batches, 1):
        # Limpiar el batch
        batch = batch.strip()
        
        # Saltar batches vacios o solo comentarios
        if not batch:
            continue
        
        # Saltar si solo tiene comentarios
        lines_no_comments = [l for l in batch.split('\n') if not l.strip().startswith('--') and l.strip()]
        if not lines_no_comments:
            continue
        
        # Eliminar lineas de SET NOCOUNT
        if batch == "SET NOCOUNT ON;":
            continue
        if batch == "SET NOCOUNT OFF;":
            continue
        
        # Saltar si solo tiene PRINT statements
        has_sql = False
        for line in batch.split('\n'):
            line_clean = line.strip()
            if line_clean and not line_clean.startswith('--') and not line_clean.startswith('PRINT'):
                has_sql = True
                break
        
        if not has_sql:
            continue
            
        # Extraer descripcion del batch
        description = ""
        for line in batch.split("\n"):
            line = line.strip()
            if "TABLA:" in line:
                # Extraer nombre de la tabla
                match = re.search(r'TABLA:\s*(\w+)', line)
                if match:
                    description = f"Tabla: {match.group(1)}"
                break
        
        try:
            cursor.execute(batch)
            conn.commit()
            successful_batches += 1
            if description:
                print(f"[OK] {description}")
            else:
                # Mostrar primeras palabras del batch
                first_sql = lines_no_comments[0][:50] if lines_no_comments else "batch"
                print(f"[OK] Batch {i}: {first_sql}...")
        except Exception as e:
            error_msg = str(e)
            # Ignorar errores de "ya existe"
            if "already has a column" in error_msg.lower() or "column names in each table must be unique" in error_msg.lower():
                skipped_batches += 1
                if description:
                    print(f"[SKIP] {description} - columna ya existe")
                else:
                    print(f"[SKIP] Batch {i}: Columna ya existe (OK)")
            else:
                failed_batches += 1
                print(f"[ERROR] Batch {i}: {error_msg[:150]}")
    
    cursor.close()
    conn.close()
    
    print()
    print("=" * 70)
    print(f"[*] Resumen:")
    print(f"    - Exitosos: {successful_batches}")
    print(f"    - Omitidos (ya existen): {skipped_batches}")
    print(f"    - Errores: {failed_batches}")
    print("=" * 70)

if __name__ == "__main__":
    run_migration()
