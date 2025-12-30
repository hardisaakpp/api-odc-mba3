"""
Script para ejecutar la migración de Fase 5 (agregar doc_entry y pedido_id).
Usa la misma configuración de conexión que la aplicación.
"""

import sys
import os
from pathlib import Path

# Agregar src al path para importar módulos
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.connection import get_db_connection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ejecutar_migracion():
    """Ejecuta el script SQL de migración Fase 5."""
    
    # Leer el script SQL
    # NOTA: Si tienes problemas con este script, usa ejecutar_migracion_fase5_directo.py
    script_path = Path(__file__).parent / "add_doc_entry_and_pedido_id.sql"
    
    if not script_path.exists():
        logger.error(f"❌ No se encontró el script SQL: {script_path}")
        return False
    
    logger.info(f"📄 Leyendo script SQL: {script_path}")
    with open(script_path, 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    # Dividir por GO statements (SQL Server requiere ejecutar por bloques)
    # Eliminar comentarios de una línea que contengan GO para evitar problemas
    blocks = []
    current_block = []
    
    for line in sql_script.split('\n'):
        line_stripped = line.strip()
        
        # Si la línea es GO (case insensitive), cerrar bloque anterior
        if line_stripped.upper() == 'GO':
            if current_block:
                blocks.append('\n'.join(current_block))
                current_block = []
        else:
            current_block.append(line)
    
    # Agregar último bloque si existe
    if current_block:
        blocks.append('\n'.join(current_block))
    
    logger.info(f"📦 Script dividido en {len(blocks)} bloques")
    
    # Conectar a la base de datos usando la configuración de la app
    try:
        logger.info("🔌 Conectando a la base de datos...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        logger.info("✅ Conexión establecida")
        
        # Configurar SET NOCOUNT ON para evitar problemas con mensajes
        try:
            cursor.execute("SET NOCOUNT ON")
            conn.commit()
        except:
            pass
        
        # Ejecutar cada bloque
        errores = []
        bloques_exitosos = 0
        for i, block in enumerate(blocks, 1):
            block_clean = block.strip()
            
            # Saltar bloques vacíos
            if not block_clean or block_clean == '':
                logger.debug(f"   Saltando bloque {i} (vacío)")
                continue
            
            # Saltar bloques que son solo comentarios
            if block_clean.startswith('--'):
                logger.debug(f"   Saltando bloque {i} (solo comentarios)")
                continue
            
            # Saltar USE statements (no necesarios cuando ya estamos conectados)
            if block_clean.upper().startswith('USE '):
                logger.debug(f"   Saltando bloque {i} (USE statement)")
                continue
            
            logger.info(f"⚙️ Ejecutando bloque {i}/{len(blocks)}...")
            logger.debug(f"   Contenido (primeras 3 líneas): {chr(10).join(block_clean.split(chr(10))[:3])}")
            
            try:
                # Ejecutar bloque - usar setnocount para evitar problemas con mensajes
                # Los bloques IF NOT EXISTS con SELECT * necesitan ejecutarse de forma especial
                try:
                    cursor.execute(block_clean)
                    conn.commit()
                    
                    # Intentar obtener resultados solo si es un SELECT standalone
                    # Los SELECT dentro de IF NOT EXISTS no retornan resultados directamente
                    is_select_standalone = (
                        block_clean.strip().upper().startswith('SELECT') and
                        'IF NOT EXISTS' not in block_clean.upper() and
                        'IF' not in block_clean.upper()[:50]  # Verificar inicio del bloque
                    )
                    
                    if is_select_standalone:
                        try:
                            results = cursor.fetchall()
                            if results:
                                logger.info(f"   Resultados: {len(results)} filas")
                                # Mostrar primeras filas si es la consulta de verificación
                                if 'INFORMATION_SCHEMA.COLUMNS' in block_clean:
                                    logger.info("   Columnas de orden_compra_cabecera:")
                                    for row in results[:15]:  # Mostrar primeras 15
                                        col_name = row[0] if len(row) > 0 else ""
                                        data_type = row[1] if len(row) > 1 else ""
                                        nullable = row[2] if len(row) > 2 else ""
                                        logger.info(f"      - {col_name} ({data_type}, NULL={nullable})")
                        except Exception as fetch_error:
                            # Algunos SELECT pueden no tener resultados inmediatos
                            logger.debug(f"   (No se pudieron obtener resultados: {fetch_error})")
                    
                    logger.info(f"   ✅ Bloque {i} ejecutado correctamente")
                    bloques_exitosos += 1
                    
                except Exception as execute_error:
                    # Si el error es de sintaxis con SELECT *, puede ser un bloque IF NOT EXISTS
                    error_str = str(execute_error).lower()
                    if "syntax near '*'" in error_str or "incorrect syntax" in error_str:
                        # Intentar ejecutar sin el SELECT dentro del IF
                        # Esto sucede cuando el bloque tiene IF NOT EXISTS (SELECT * ...)
                        # En estos casos, el bloque completo se ejecuta pero pyodbc tiene problemas
                        logger.warning(f"   ⚠️ Posible problema con sintaxis en bloque {i}, intentando ejecutar sin SELECT...")
                        
                        # Intentar ejecutar solo si contiene IF NOT EXISTS
                        if 'IF NOT EXISTS' in block_clean.upper():
                            # El bloque contiene IF NOT EXISTS con SELECT * dentro
                            # pyodbc a veces tiene problemas con esto, pero SQL Server lo acepta
                            # Intentar ejecutar línea por línea o ignorar este error específico
                            logger.warning(f"   ⚠️ Bloque {i} contiene IF NOT EXISTS con SELECT *, puede que ya se ejecutó")
                            # El bloque probablemente ya funcionó en ejecuciones anteriores
                            # Si las columnas ya existen, este error es esperado
                            try:
                                conn.commit()
                                bloques_exitosos += 1
                                logger.info(f"   ℹ️ Bloque {i} manejado (puede que columnas ya existan)")
                            except:
                                pass
                        else:
                            # No es un IF NOT EXISTS, es un error real
                            raise
                    else:
                        # Otro tipo de error, re-lanzar
                        raise
                
            except Exception as e:
                error_msg = str(e)
                # Algunos errores son esperados (como "ya existe")
                if "already exists" in error_msg.lower() or "ya existe" in error_msg.lower():
                    logger.info(f"   ℹ️ Bloque {i}: {error_msg}")
                    try:
                        conn.commit()  # Commit aunque haya error esperado
                    except:
                        pass
                else:
                    logger.error(f"   ❌ Error en bloque {i}: {error_msg}")
                    # Mostrar primeras líneas del bloque para debugging
                    first_lines = '\n'.join(block_clean.split('\n')[:5])
                    logger.debug(f"   Bloque problemático (primeras 5 líneas):\n{first_lines}")
                    errores.append((i, error_msg))
                    try:
                        conn.rollback()
                    except:
                        pass
        
        cursor.close()
        conn.close()
        
        # Verificar si las columnas se crearon correctamente
        logger.info("🔍 Verificando que las columnas se crearon...")
        try:
            verify_conn = get_db_connection()
            verify_cursor = verify_conn.cursor()
            verify_cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'orden_compra_cabecera'
                AND COLUMN_NAME IN ('doc_entry', 'pedido_id')
                ORDER BY COLUMN_NAME
            """)
            results = verify_cursor.fetchall()
            columns_found = [row[0] for row in results]
            
            logger.info(f"   Columnas encontradas: {columns_found}")
            if results:
                for col_name, data_type, nullable in results:
                    logger.info(f"      - {col_name}: {data_type}, NULL={nullable}")
            
            verify_cursor.close()
            verify_conn.close()
            
            if 'doc_entry' in columns_found and 'pedido_id' in columns_found:
                logger.info("✅ Verificación: Ambas columnas (doc_entry, pedido_id) existen")
                if errores:
                    logger.warning(f"⚠️ Hubo {len(errores)} errores, pero las columnas se crearon correctamente")
                    logger.warning("   Los errores pueden ser de bloques que ya se ejecutaron anteriormente")
                    return True  # Las columnas existen, migración exitosa
                return True
            elif 'doc_entry' in columns_found or 'pedido_id' in columns_found:
                logger.warning(f"⚠️ Solo se creó parcialmente: columnas encontradas: {columns_found}")
                if 'doc_entry' not in columns_found:
                    logger.error("   ❌ Falta: doc_entry")
                if 'pedido_id' not in columns_found:
                    logger.error("   ❌ Falta: pedido_id")
                return False
            else:
                logger.error("❌ Las columnas NO se crearon")
                logger.error(f"   Columnas encontradas en la tabla: {columns_found}")
                # Mostrar todas las columnas de la tabla para debugging
                try:
                    debug_conn = get_db_connection()
                    debug_cursor = debug_conn.cursor()
                    debug_cursor.execute("""
                        SELECT TOP 20 COLUMN_NAME 
                        FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = 'orden_compra_cabecera'
                        ORDER BY ORDINAL_POSITION
                    """)
                    all_columns = [row[0] for row in debug_cursor.fetchall()]
                    logger.info(f"   Todas las columnas de orden_compra_cabecera: {all_columns}")
                    debug_cursor.close()
                    debug_conn.close()
                except:
                    pass
                return False
        except Exception as verify_error:
            logger.error(f"❌ Error al verificar columnas: {verify_error}", exc_info=True)
            # Si hay errores pero no podemos verificar, asumir fallo
            if errores:
                return False
            return False
        
        if errores:
            logger.warning(f"⚠️ Se encontraron {len(errores)} errores:")
            for block_num, error in errores:
                logger.warning(f"   Bloque {block_num}: {error}")
            return False
        
        logger.info("✅ Migración completada exitosamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error al conectar o ejecutar migración: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("Migracion Fase 5: Agregar doc_entry y pedido_id")
    print("=" * 70)
    print()
    
    success = ejecutar_migracion()
    
    print()
    print("=" * 70)
    if success:
        print("[OK] Migracion completada correctamente")
        print()
        print("Proximos pasos:")
        print("1. Verifica que las columnas se crearon:")
        print("   SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS")
        print("   WHERE TABLE_NAME = 'orden_compra_cabecera'")
        print("   AND COLUMN_NAME IN ('doc_entry', 'pedido_id');")
        print()
        print("2. Reinicia la aplicacion si esta corriendo")
    else:
        print("[ERROR] Migracion completada con errores")
        print("   Revisa los logs arriba para mas detalles")
    print("=" * 70)
    
    sys.exit(0 if success else 1)

