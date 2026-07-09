#!/usr/bin/env python
"""
Script de procesamiento de plantilla de pedido v1.0

Uso:
    python procesar_plantilla_pedido.py <archivo.xlsx> [opciones]

Ejemplo:
    python procesar_plantilla_pedido.py Template_Pedido_Inicial_v1.0.xlsx
    python procesar_plantilla_pedido.py pedido.xlsx --usuario-id "usuario@empresa.com" --validar-sap
"""

import sys
import logging
import json
from pathlib import Path
from typing import Optional
import argparse

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def procesar_plantilla(
    ruta_archivo: str,
    usuario_id: Optional[str] = None,
    validar_sap: bool = False,
    sap_obligatorio: bool = False,
    verbose: bool = False,
    output_json: Optional[str] = None
) -> int:
    """
    Procesa un archivo Excel de plantilla de pedido.
    
    Args:
        ruta_archivo: Ruta al archivo Excel
        usuario_id: ID del usuario que procesa el archivo
        validar_sap: Si True, valida códigos contra SAP
        sap_obligatorio: Si True, errores de SAP bloquean procesamiento
        verbose: Si True, muestra logs más detallados
        output_json: Si se especifica, guarda resultado en JSON
    
    Returns:
        0 si éxito, 1 si error
    """
    
    # Configurar nivel de logging
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=" * 80)
    logger.info("PROCESADOR DE PLANTILLA DE PEDIDO v1.0")
    logger.info("=" * 80)
    
    # Validar archivo
    ruta = Path(ruta_archivo)
    if not ruta.exists():
        logger.error(f"❌ Archivo no encontrado: {ruta_archivo}")
        return 1
    
    if not ruta.suffix.lower() in ['.xlsx', '.xls']:
        logger.error(f"❌ Archivo debe ser Excel (.xlsx o .xls): {ruta_archivo}")
        return 1
    
    logger.info(f"📄 Archivo: {ruta.name} ({ruta.stat().st_size / 1024:.1f} KB)")
    
    # Importar servicios
    try:
        from src.database.services.pedido_service import PedidoService
        logger.info("✅ Servicio de Pedidos importado exitosamente")
    except ImportError as e:
        logger.error(f"❌ Error importando servicio de pedidos: {e}")
        logger.error("   Asegúrate de estar en el directorio raíz del proyecto")
        return 1
    
    # Leer archivo
    try:
        logger.info("📂 Leyendo archivo Excel...")
        file_content = ruta.read_bytes()
        logger.info(f"   ✅ Archivo leído: {len(file_content)} bytes")
    except Exception as e:
        logger.error(f"❌ Error al leer archivo: {e}")
        return 1
    
    # Procesar
    try:
        logger.info("🔄 Iniciando procesamiento...")
        service = PedidoService()
        
        resultado = service.validar_y_procesar_archivo_excel(
            file_content=file_content,
            filename=ruta.name,
            usuario_id=usuario_id or "USUARIO_DESCONOCIDO",
            validar_antes_de_guardar=True,
            tiendas_permitidas=None,
            bloquea_con_errores=True,
            validar_sap=validar_sap,
            sap_obligatorio=sap_obligatorio
        )
        
        # Mostrar resultado
        logger.info("=" * 80)
        logger.info("RESULTADO DEL PROCESAMIENTO")
        logger.info("=" * 80)
        
        status = resultado.get("status", "unknown")
        formato = resultado.get("formato_detectado", "desconocido")
        pedido_id = resultado.get("pedido_id")
        
        logger.info(f"Estado: {status}")
        logger.info(f"Formato: {formato}")
        
        if status == "success":
            logger.info("✅ Procesamiento exitoso")
            logger.info(f"   • Pedido ID: {pedido_id}")
            logger.info(f"   • Artículos cargados: {resultado.get('articulos_cargados', 0)}")
            logger.info(f"   • Distribuciones cargadas: {resultado.get('distribuciones_cargados', 0)}")
            
            # Mostrar resumen si existe
            resumen = resultado.get("resumen", {})
            if resumen:
                logger.info(f"\n📊 Resumen:")
                logger.info(f"   • Hojas procesadas: {', '.join(resumen.get('hojas_procesadas', []))}")
                logger.info(f"   • Tiendas validadas: {resumen.get('tiendas_validadas', 0)}")
                logger.info(f"   • Productos cargados: {resumen.get('productos_cargados', 0)}")
                logger.info(f"   • Distribuciones totales: {resumen.get('distribuciones_totales', 0)}")
            
            # Mostrar warnings si existen
            warnings = resultado.get("warnings", [])
            if warnings:
                logger.info(f"\n⚠️ Warnings ({len(warnings)}):")
                for i, warning in enumerate(warnings[:5], 1):
                    logger.warning(f"   {i}. {warning}")
                if len(warnings) > 5:
                    logger.warning(f"   ... y {len(warnings) - 5} más")
        
        elif status == "validation_error":
            logger.error("❌ Error de validación")
            validation = resultado.get("validation", {})
            if validation:
                errors = validation.get("errors", [])
                if errors:
                    logger.error(f"\nErrores de validación ({len(errors)}):")
                    for i, error in enumerate(errors[:5], 1):
                        logger.error(f"   {i}. {error}")
                    if len(errors) > 5:
                        logger.error(f"   ... y {len(errors) - 5} más")
        
        else:
            logger.error(f"❌ Error al procesar: {status}")
            errores = resultado.get("errores", [])
            if errores:
                logger.error(f"\nErrores ({len(errores)}):")
                for i, error in enumerate(errores[:5], 1):
                    logger.error(f"   {i}. {error}")
                if len(errores) > 5:
                    logger.error(f"   ... y {len(errores) - 5} más")
        
        # Guardar resultado en JSON si se solicita
        if output_json:
            output_path = Path(output_json)
            try:
                # Serializar resultado (convertir tipos no JSON)
                resultado_json = _serializar_para_json(resultado)
                output_path.write_text(json.dumps(resultado_json, indent=2, ensure_ascii=False))
                logger.info(f"\n📄 Resultado guardado en: {output_path}")
            except Exception as e:
                logger.error(f"❌ Error guardando JSON: {e}")
        
        logger.info("=" * 80)
        
        # Retornar código de salida
        return 0 if status == "success" else 1
        
    except Exception as e:
        logger.error(f"❌ Error durante procesamiento: {e}", exc_info=verbose)
        return 1


def _serializar_para_json(obj):
    """Convierte objetos no serializables a JSON."""
    from datetime import datetime, date
    from uuid import UUID
    from decimal import Decimal
    
    if isinstance(obj, dict):
        return {k: _serializar_para_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_serializar_para_json(item) for item in obj]
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, Decimal):
        return float(obj)
    elif obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    else:
        return str(obj)


def main():
    """Función principal."""
    parser = argparse.ArgumentParser(
        description="Procesa un archivo Excel de plantilla de pedido v1.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  # Procesamiento básico
  python procesar_plantilla_pedido.py Template_Pedido_Inicial_v1.0.xlsx
  
  # Con validación SAP
  python procesar_plantilla_pedido.py pedido.xlsx --validar-sap --usuario-id "usuario@empresa.com"
  
  # Verbose y guardar resultado en JSON
  python procesar_plantilla_pedido.py pedido.xlsx --verbose --output-json resultado.json
        """
    )
    
    parser.add_argument(
        "archivo",
        help="Ruta al archivo Excel (.xlsx o .xls)"
    )
    
    parser.add_argument(
        "--usuario-id",
        default=None,
        help="ID del usuario que procesa el archivo (default: USUARIO_DESCONOCIDO)"
    )
    
    parser.add_argument(
        "--validar-sap",
        action="store_true",
        help="Validar códigos de producto contra SAP"
    )
    
    parser.add_argument(
        "--sap-obligatorio",
        action="store_true",
        help="Si se usa --validar-sap, hace que errores de SAP bloqueen el procesamiento"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Mostrar logs más detallados (DEBUG)"
    )
    
    parser.add_argument(
        "--output-json",
        "-o",
        default=None,
        help="Guardar resultado en archivo JSON"
    )
    
    args = parser.parse_args()
    
    # Ejecutar procesamiento
    exit_code = procesar_plantilla(
        ruta_archivo=args.archivo,
        usuario_id=args.usuario_id,
        validar_sap=args.validar_sap,
        sap_obligatorio=args.sap_obligatorio,
        verbose=args.verbose,
        output_json=args.output_json
    )
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
