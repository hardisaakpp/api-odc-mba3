"""
Script DIRECTO para ejecutar la migración de Fase 5.
Ejecuta los comandos SQL directamente sin dividir por GO.
"""

import sys
from pathlib import Path

# Agregar src al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db_connection
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def ejecutar_migracion_directa():
    """Ejecuta los comandos SQL directamente."""
    
    logger.info("Conectando a la base de datos...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    logger.info("Conexion establecida")
    
    comandos = [
        # Agregar doc_entry
        """
        BEGIN TRY
            ALTER TABLE orden_compra_cabecera ADD doc_entry INT NULL;
            PRINT 'Campo doc_entry agregado';
        END TRY
        BEGIN CATCH
            IF ERROR_NUMBER() = 4922
                PRINT 'Campo doc_entry ya existe';
            ELSE
                THROW;
        END CATCH
        """,
        
        # Agregar pedido_id
        """
        BEGIN TRY
            ALTER TABLE orden_compra_cabecera ADD pedido_id UNIQUEIDENTIFIER NULL;
            PRINT 'Campo pedido_id agregado';
        END TRY
        BEGIN CATCH
            IF ERROR_NUMBER() = 4922
                PRINT 'Campo pedido_id ya existe';
            ELSE
                THROW;
        END CATCH
        """,
        
        # Crear índice en doc_entry
        """
        BEGIN TRY
            CREATE UNIQUE INDEX idx_oc_doc_entry 
            ON orden_compra_cabecera(doc_entry) 
            WHERE doc_entry IS NOT NULL;
            PRINT 'Indice idx_oc_doc_entry creado';
        END TRY
        BEGIN CATCH
            IF ERROR_NUMBER() = 1913 OR ERROR_NUMBER() = 1914
                PRINT 'Indice idx_oc_doc_entry ya existe';
            ELSE
                THROW;
        END CATCH
        """,
        
        # Crear índice en pedido_id
        """
        BEGIN TRY
            CREATE INDEX idx_oc_pedido_id 
            ON orden_compra_cabecera(pedido_id)
            WHERE pedido_id IS NOT NULL;
            PRINT 'Indice idx_oc_pedido_id creado';
        END TRY
        BEGIN CATCH
            IF ERROR_NUMBER() = 1913 OR ERROR_NUMBER() = 1914
                PRINT 'Indice idx_oc_pedido_id ya existe';
            ELSE
                THROW;
        END CATCH
        """
    ]
    
    errores = []
    
    for i, comando in enumerate(comandos, 1):
        logger.info(f"Ejecutando comando {i}/{len(comandos)}...")
        try:
            cursor.execute(comando)
            conn.commit()
            logger.info(f"   OK: Comando {i} ejecutado correctamente")
        except Exception as e:
            error_msg = str(e)
            # Error 4922 = columna ya existe (OK)
            # Error 1913/1914 = índice ya existe (OK)
            if "4922" in error_msg or "1913" in error_msg or "1914" in error_msg:
                logger.info(f"   INFO: Comando {i} - {error_msg}")
                try:
                    conn.commit()
                except:
                    pass
            else:
                logger.error(f"   ERROR: Comando {i} - {error_msg}")
                errores.append((i, error_msg))
                try:
                    conn.rollback()
                except:
                    pass
    
    cursor.close()
    
    # Verificar
    logger.info("Verificando columnas creadas...")
    verify_cursor = conn.cursor()
    verify_cursor.execute("""
        SELECT COLUMN_NAME, DATA_TYPE 
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'orden_compra_cabecera'
        AND COLUMN_NAME IN ('doc_entry', 'pedido_id')
        ORDER BY COLUMN_NAME
    """)
    results = verify_cursor.fetchall()
    verify_cursor.close()
    conn.close()
    
    columns_found = [row[0] for row in results] if results else []
    
    logger.info(f"Columnas encontradas: {columns_found}")
    
    if 'doc_entry' in columns_found and 'pedido_id' in columns_found:
        logger.info("SUCCESS: Ambas columnas se crearon correctamente")
        return True
    else:
        logger.error(f"ERROR: Columnas faltantes. Encontradas: {columns_found}")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("Migracion Fase 5: Agregar doc_entry y pedido_id (DIRECTO)")
    print("=" * 70)
    print()
    
    success = ejecutar_migracion_directa()
    
    print()
    print("=" * 70)
    if success:
        print("[OK] Migracion completada correctamente")
    else:
        print("[ERROR] Migracion fallo")
    print("=" * 70)
    
    sys.exit(0 if success else 1)

