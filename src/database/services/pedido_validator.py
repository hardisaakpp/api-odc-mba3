"""
Motor de validación para pedidos desde Excel.
Valida datos pre-negocio antes de enviar al ERP.

REFACTORIZADO: Las validaciones contra SAP fueron movidas a pedido_sap_validator.py
para mejorar separación de responsabilidades. Este módulo mantiene solo validaciones
básicas de estructura, formato y coherencia.

CHANGELOG:
- 2026-01-08: Extraídos tipos comunes a pedido_validation_types.py
- 2026-01-08: Extraída validación de cabecera a pedido_cabecera_validator.py
- 2026-01-08: Extraída validación de precios a pedido_precio_validator.py
- 2026-01-08: Refactorizado como facade que delega a validadores especializados
"""

import logging
import re
from typing import Dict, Any, List, Optional

# Importar tipos comunes
from .pedido_validation_types import ValidationIssue, ValidationSeverity

# Importar validadores especializados
from .pedido_cabecera_validator import PedidoCabeceraValidator
from .pedido_precio_validator import PedidoPrecioValidator

# Re-exportar para compatibilidad hacia atrás
__all__ = ['PedidoValidator', 'ValidationIssue', 'ValidationSeverity']

logger = logging.getLogger(__name__)



class PedidoValidator:
    """
    Motor de validación para pedidos.
    
    REFACTORIZADO: Ahora delega a validadores especializados:
    - PedidoCabeceraValidator: Validación de cabecera
    - PedidoPrecioValidator: Validación de precios e impuestos

    Valida:
    - Catálogo (códigos de producto no vacíos, caracteres válidos)
    - Tiendas (IdTienda corresponde a sucursal/almacén permitido)
    - Unidades (enteros, máximos razonables por tienda en relación a total)
    - Fechas (no pasadas si se usa fecha de entrega, formato correcto)
    - Precios e impuestos (formato regional, coherencia)
    """
    
    def __init__(
        self,
        tiendas_permitidas: Optional[List[str]] = None,
        max_cantidad_por_tienda: Optional[int] = None,
        max_cantidad_total: Optional[int] = None,
        permitir_fechas_pasadas: bool = False,
        validar_precios: bool = True,
        iva_porcentaje: float = 15.0,  # IVA por defecto en Ecuador (15%)
        usar_comas_decimales: bool = False  # True para formato europeo (ej: 10,50)
    ):
        """
        Args:
            tiendas_permitidas: Lista de códigos de tiendas permitidas (None = todas)
            max_cantidad_por_tienda: Cantidad máxima por tienda (None = sin límite)
            max_cantidad_total: Cantidad total máxima por producto (None = sin límite)
            permitir_fechas_pasadas: Si False, valida que fecha_entrega no sea pasada
            validar_precios: Si True, valida reglas regionales de precio/impuestos
            iva_porcentaje: Porcentaje de IVA para validaciones (default: 15.0 para Ecuador)
            usar_comas_decimales: Si True, acepta comas como separador decimal (formato europeo)
        """
        self.tiendas_permitidas = set(t.upper() if t else None for t in (tiendas_permitidas or []))
        self.max_cantidad_por_tienda = max_cantidad_por_tienda
        self.max_cantidad_total = max_cantidad_total
        self.validar_precios = validar_precios

        # Inicializar validadores especializados
        self.cabecera_validator = PedidoCabeceraValidator(
            permitir_fechas_pasadas=permitir_fechas_pasadas
        )
        self.precio_validator = PedidoPrecioValidator(
            iva_porcentaje=iva_porcentaje,
            usar_comas_decimales=usar_comas_decimales
        )

        # Patrón para códigos de producto válidos (ajustar según necesidades)
        # Permite letras, números, puntos, guiones y espacios
        self.codigo_producto_pattern = re.compile(r'^[A-Za-z0-9.\-\s]{1,50}$')
    
    def validar_cabecera(
        self,
        cabecera: Dict[str, Any],
        row_number: int = 1
    ) -> List[ValidationIssue]:
        """
        Valida la cabecera del pedido.
        
        DELEGA a PedidoCabeceraValidator.

        Args:
            cabecera: Diccionario con datos de cabecera
            row_number: Número de fila (para reporte)
            
        Returns:
            Lista de issues de validación
        """
        return self.cabecera_validator.validar(cabecera, row_number)

    def validar_detalle(
        self,
        detalle: Dict[str, Any],
        distribuciones: List[Dict[str, Any]],
        row_number: int
    ) -> List[ValidationIssue]:
        """
        Valida un detalle (producto) con sus distribuciones por tienda.

        Args:
            detalle: Diccionario con datos del detalle
            distribuciones: Lista de distribuciones por tienda
            row_number: Número de fila en el Excel (para reporte)

        Returns:
            Lista de issues de validación
        """
        issues = []

        # Validar código interno (catálogo)
        codigo_interno = detalle.get("codigo_interno")
        if not codigo_interno or not str(codigo_interno).strip():
            issues.append(ValidationIssue(
                row_number=row_number,
                field="codigo_interno",
                severity=ValidationSeverity.ERROR,
                message="El código interno del producto es obligatorio",
                value=codigo_interno
            ))
        else:
            codigo_str = str(codigo_interno).strip()
            # Validar caracteres válidos
            if not self.codigo_producto_pattern.match(codigo_str):
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="codigo_interno",
                    severity=ValidationSeverity.ERROR,
                    message="El código interno contiene caracteres no permitidos. Solo se permiten letras, números, guiones, puntos y espacios",
                    value=codigo_str
                ))

        # Validar distribuciones por tienda
        if not distribuciones:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="distribuciones",
                severity=ValidationSeverity.ERROR,
                message="El producto debe tener al menos una distribución por tienda",
                value=None
            ))
        else:
            # Calcular cantidad total
            cantidad_total = 0
            tiendas_usadas = set()

            for dist in distribuciones:
                tienda_codigo = dist.get("tienda_codigo")
                cantidad = dist.get("cantidad")
                validacion_tienda = dist.get("validacion", {})

                # Validar tienda
                if not tienda_codigo or not str(tienda_codigo).strip():
                    issues.append(ValidationIssue(
                        row_number=row_number,
                        field="tienda_codigo",
                        severity=ValidationSeverity.ERROR,
                        message="El código de tienda es obligatorio en la distribución",
                        value=tienda_codigo
                    ))
                else:
                    tienda_codigo_str = str(tienda_codigo).strip().upper()

                    # Procesar validaciones del parser (hoja Tiendas)
                    if validacion_tienda:
                        # Agregar errores de validación del parser
                        for error_msg in validacion_tienda.get("errores", []):
                            issues.append(ValidationIssue(
                                row_number=row_number,
                                field="tienda_codigo",
                                severity=ValidationSeverity.ERROR,
                                message=error_msg,
                                value=tienda_codigo_str
                            ))

                        # Agregar warnings de validación del parser
                        for warning_msg in validacion_tienda.get("warnings", []):
                            issues.append(ValidationIssue(
                                row_number=row_number,
                                field="tienda_codigo",
                                severity=ValidationSeverity.WARNING,
                                message=warning_msg,
                                value=tienda_codigo_str
                            ))

                    # Validar que la tienda esté en la lista permitida (si se especifica)
                    if self.tiendas_permitidas and tienda_codigo_str not in self.tiendas_permitidas:
                        issues.append(ValidationIssue(
                            row_number=row_number,
                            field="tienda_codigo",
                            severity=ValidationSeverity.ERROR,
                            message=f"La tienda '{tienda_codigo_str}' no está en la lista de tiendas permitidas",
                            value=tienda_codigo_str
                        ))

                    # Detectar duplicados (misma tienda repetida)
                    if tienda_codigo_str in tiendas_usadas:
                        issues.append(ValidationIssue(
                            row_number=row_number,
                            field="tienda_codigo",
                            severity=ValidationSeverity.ERROR,
                            message=f"La tienda '{tienda_codigo_str}' está duplicada para este producto. Use una sola distribución por tienda",
                            value=tienda_codigo_str
                        ))
                    tiendas_usadas.add(tienda_codigo_str)

                # Validar cantidad (acepta enteros y decimales)
                if cantidad is None:
                    issues.append(ValidationIssue(
                        row_number=row_number,
                        field="cantidad",
                        severity=ValidationSeverity.ERROR,
                        message="La cantidad es obligatoria",
                        value=None
                    ))
                else:
                    try:
                        cantidad_val = float(cantidad)
                        if cantidad_val < 0:
                            issues.append(ValidationIssue(
                                row_number=row_number,
                                field="cantidad",
                                severity=ValidationSeverity.ERROR,
                                message=f"La cantidad no puede ser negativa. Valor recibido: {cantidad}",
                                value=cantidad
                            ))
                        else:
                            cantidad_total += cantidad_val

                            # Validar límite por tienda
                            if self.max_cantidad_por_tienda and cantidad_val > self.max_cantidad_por_tienda:
                                issues.append(ValidationIssue(
                                    row_number=row_number,
                                    field="cantidad",
                                    severity=ValidationSeverity.WARNING,
                                    message=f"La cantidad para la tienda '{tienda_codigo}' ({cantidad_val}) excede el límite razonable por tienda ({self.max_cantidad_por_tienda})",
                                    value=cantidad_val
                                ))
                    except (ValueError, TypeError):
                        issues.append(ValidationIssue(
                            row_number=row_number,
                            field="cantidad",
                            severity=ValidationSeverity.ERROR,
                            message=f"La cantidad debe ser un número válido. Valor recibido: {cantidad}",
                            value=cantidad
                        ))

            # Validar cantidad total
            if cantidad_total > 0:
                if self.max_cantidad_total and cantidad_total > self.max_cantidad_total:
                    issues.append(ValidationIssue(
                        row_number=row_number,
                        field="cantidad_total",
                        severity=ValidationSeverity.WARNING,
                        message=f"La cantidad total ({cantidad_total}) excede el límite razonable ({self.max_cantidad_total})",
                        value=cantidad_total
                    ))

        # Validar precios e impuestos (reglas regionales)
        if self.validar_precios:
            precio_issues = self._validar_precios_impuestos(detalle, row_number)
            issues.extend(precio_issues)
        
        return issues
    
    def _validar_precios_impuestos(
        self,
        detalle: Dict[str, Any],
        row_number: int
    ) -> List[ValidationIssue]:
        """
        Valida reglas regionales de precio e impuestos.
        
        DELEGA a PedidoPrecioValidator.

        Args:
            detalle: Diccionario con datos del detalle
            row_number: Número de fila en el Excel
            
        Returns:
            Lista de issues de validación
        """
        return self.precio_validator.validar(detalle, row_number)

    def validar_detalle_formato_simple(
        self,
        detalle: Dict[str, Any],
        distribuciones: List[Dict[str, Any]],
        filas_origen: List[int]
    ) -> List[ValidationIssue]:
        """
        Valida un detalle con sus distribuciones (formato simple).
        
        Args:
            detalle: Diccionario con datos del detalle
            distribuciones: Lista de distribuciones por tienda
            filas_origen: Lista de números de fila que originaron este detalle
            
        Returns:
            Lista de issues de validación
        """
        # Usar la primera fila como referencia para reportes
        row_number = filas_origen[0] if filas_origen else 2
        
        # Reutilizar validación estándar
        return self.validar_detalle(detalle, distribuciones, row_number)
    
    def validar_pedido_completo(
        self,
        cabecera: Dict[str, Any],
        detalles: List[Dict[str, Any]],
        es_formato_simple: bool = False
    ) -> Dict[str, Any]:
        """
        Valida un pedido completo (cabecera + todos los detalles).
        
        Args:
            cabecera: Datos de cabecera
            detalles: Lista de detalles (cada uno con 'detalle' y 'distribuciones')
            es_formato_simple: Si True, usa validación específica para formato simple
            
        Returns:
            Diccionario con resultado de validación:
            {
                "valid": bool,
                "total_issues": int,
                "errors": int,
                "warnings": int,
                "issues_by_row": Dict[int, List[ValidationIssue]],
                "all_issues": List[ValidationIssue]
            }
        """
        all_issues = []
        issues_by_row = {}
        
        # Validar cabecera
        cabecera_issues = self.validar_cabecera(cabecera, row_number=1)
        all_issues.extend(cabecera_issues)
        if cabecera_issues:
            issues_by_row[1] = cabecera_issues
        
        # Validar cada detalle (empezar desde fila 2, asumiendo fila 1 es cabecera o header)
        for idx, detalle_data in enumerate(detalles, start=2):
            detalle = detalle_data.get("detalle", {})
            distribuciones = detalle_data.get("distribuciones", [])
            filas_origen = detalle_data.get("filas_origen", [idx])
            
            if es_formato_simple:
                detalle_issues = self.validar_detalle_formato_simple(
                    detalle, distribuciones, filas_origen
                )
            else:
                row_num = filas_origen[0] if filas_origen else idx
                detalle_issues = self.validar_detalle(detalle, distribuciones, row_num)
            
            all_issues.extend(detalle_issues)
            
            # Agrupar issues por fila de origen
            for fila_origen in filas_origen:
                if detalle_issues:
                    if fila_origen not in issues_by_row:
                        issues_by_row[fila_origen] = []
                    issues_by_row[fila_origen].extend(detalle_issues)
        
        # Contar errores y advertencias
        errors = sum(1 for issue in all_issues if issue.severity == ValidationSeverity.ERROR)
        warnings = sum(1 for issue in all_issues if issue.severity == ValidationSeverity.WARNING)
        
        return {
            "valid": errors == 0,  # Válido solo si no hay errores
            "total_issues": len(all_issues),
            "errors": errors,
            "warnings": warnings,
            "issues_by_row": issues_by_row,
            "all_issues": all_issues
        }
    
    def validar_productos_existen(
        self,
        codigos_productos: List[str],
        conn
    ) -> Dict[str, Any]:
        """
        Valida que los productos existan en el catálogo.
        
        Busca en producto_mba3_staging (y opcionalmente producto_sap_staging).
        
        Args:
            codigos_productos: Lista de códigos de productos a validar
            conn: Conexión a la base de datos
            
        Returns:
            {
                "validos": List[str],
                "no_encontrados": List[str],
                "todos_validos": bool,
                "detalle": Dict[str, bool]  # {codigo: existe}
            }
        """
        from ..repositories.producto_mba3_staging_repository import ProductoMBA3StagingRepository
        
        if not codigos_productos:
            return {
                "validos": [],
                "no_encontrados": [],
                "todos_validos": True,
                "detalle": {}
            }
        
        try:
            repo = ProductoMBA3StagingRepository(conn)
            detalle = repo.validar_codigos_existen(codigos_productos, usar_normalizado=True)
            
            validos = [codigo for codigo, existe in detalle.items() if existe]
            no_encontrados = [codigo for codigo, existe in detalle.items() if not existe]
            
            return {
                "validos": validos,
                "no_encontrados": no_encontrados,
                "todos_validos": len(no_encontrados) == 0,
                "detalle": detalle
            }
        except Exception as e:
            logger.error(f"❌ Error al validar productos: {e}", exc_info=True)
            # En caso de error, retornar que no se encontraron (más seguro)
            return {
                "validos": [],
                "no_encontrados": codigos_productos,
                "todos_validos": False,
                "detalle": {codigo: False for codigo in codigos_productos}
            }
    
    def validar_tiendas_existen(
        self,
        codigos_tiendas: List[str],
        conn
    ) -> Dict[str, Any]:
        """
        Valida que las tiendas existan y estén activas.
        
        Args:
            codigos_tiendas: Lista de códigos de tiendas a validar
            conn: Conexión a la base de datos
            
        Returns:
            {
                "validas": List[str],
                "no_encontradas": List[str],
                "inactivas": List[str],
                "todas_validas": bool,
                "detalle": Dict[str, Dict[str, Any]]  # {codigo: {"existe": bool, "activa": bool}}
            }
        """
        from ..repositories.pedido_repository import PedidoRepository
        
        if not codigos_tiendas:
            return {
                "validas": [],
                "no_encontradas": [],
                "inactivas": [],
                "todas_validas": True,
                "detalle": {}
            }
        
        try:
            repo = PedidoRepository(conn)
            detalle = repo.validar_tiendas_existen(codigos_tiendas)
            
            validas = [
                codigo for codigo, info in detalle.items() 
                if info.get("existe") and info.get("activa")
            ]
            no_encontradas = [
                codigo for codigo, info in detalle.items() 
                if not info.get("existe")
            ]
            inactivas = [
                codigo for codigo, info in detalle.items() 
                if info.get("existe") and not info.get("activa")
            ]
            
            return {
                "validas": validas,
                "no_encontradas": no_encontradas,
                "inactivas": inactivas,
                "todas_validas": len(no_encontradas) == 0 and len(inactivas) == 0,
                "detalle": detalle
            }
        except Exception as e:
            logger.error(f"❌ Error al validar tiendas: {e}", exc_info=True)
            # En caso de error, retornar que no se encontraron
            return {
                "validas": [],
                "no_encontradas": codigos_tiendas,
                "inactivas": [],
                "todas_validas": False,
                "detalle": {codigo: {"existe": False, "activa": False} for codigo in codigos_tiendas}
            }
    
    def validar_productos_existen_en_sap(
        self,
        codigos_productos: List[str],
        usar_cache: bool = True,
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de producto existan directamente en SAP.
        
        REFACTORIZADO: Delega a PedidoSAPValidator para mantener compatibilidad.
        
        Args:
            codigos_productos: Lista de códigos de productos a validar (deben ser únicos)
            usar_cache: Si True, usa SAPService que tiene cache. Si False, consulta directamente SAPClient
            sap_obligatorio: Si True, errores de SAP bloquean. Si False, solo WARNING
            
        Returns:
            {
                "validos": List[str],  # Códigos que existen en SAP con ItemCode exacto
                "no_encontrados": List[str],  # Códigos que NO existen en SAP
                "errores": List[str],  # Códigos con error al consultar SAP
                "warnings": List[str],  # Códigos con warnings (SAP no respondió pero no es obligatorio)
                "todos_validos": bool,
                "detalle": Dict[str, Dict[str, Any]]  # {codigo: {"existe": bool, "info": {...}, "error": str, "severity": str}}
            }
        """
        from .pedido_sap_validator import PedidoSAPValidator
        sap_validator = PedidoSAPValidator()
        return sap_validator.validar_productos_existen_en_sap(
            codigos_productos=codigos_productos,
            usar_cache=usar_cache,
            sap_obligatorio=sap_obligatorio
        )
    
    def validar_productos_existen_en_sap_con_sugerencias(
        self,
        codigos_productos: List[str],
        usar_cache: bool = True,
        sap_obligatorio: bool = True,
        incluir_sugerencias: bool = True,
        limite_sugerencias: int = 20
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de producto existan en SAP, y si no se encuentran,
        busca en MBA3 y genera sugerencias similares en SAP.
        
        Similar a la funcionalidad de "Buscar SKU" en homologaciones.
        
        Args:
            codigos_productos: Lista de códigos de productos a validar (deben ser únicos)
            usar_cache: Si True, usa SAPService que tiene cache. Si False, consulta directamente SAPClient
            sap_obligatorio: Si True, errores de SAP bloquean. Si False, solo WARNING
            incluir_sugerencias: Si True, busca sugerencias similares cuando no encuentra exacto
            limite_sugerencias: Límite máximo de sugerencias a retornar por código (default: 20)
            
        Returns:
            {
                "validos": List[str],  # Códigos que existen en SAP con ItemCode exacto
                "no_encontrados": List[str],  # Códigos que NO existen en SAP
                "errores": List[str],  # Códigos con error al consultar SAP
                "warnings": List[str],  # Códigos con warnings (SAP no respondió pero no es obligatorio)
                "todos_validos": bool,
                "detalle": Dict[str, Dict[str, Any]]  # {codigo: {
                    #   "existe": bool,
                    #   "info": {...},
                    #   "error": str,
                    #   "severity": str,
                    #   "mba3": {...},  # Información de MBA3 si existe
                    #   "sugerencias_sap": [...]  # Sugerencias similares en SAP
                    # }}
            }
        """
        from .pedido_sap_validator import PedidoSAPValidator
        sap_validator = PedidoSAPValidator()
        return sap_validator.validar_productos_existen_en_sap_con_sugerencias(
            codigos_productos=codigos_productos,
            usar_cache=usar_cache,
            sap_obligatorio=sap_obligatorio,
            incluir_sugerencias=incluir_sugerencias,
            limite_sugerencias=limite_sugerencias
        )
    
    def validar_bodegas_existen_en_sap(
        self,
        codigos_bodegas: List[str],
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de bodega existan en SAP OWHS.
        Obtiene TODAS las bodegas de SAP y valida contra ese catálogo completo.
        
        REFACTORIZADO: Delega a PedidoSAPValidator para mantener compatibilidad.
        
        Args:
            codigos_bodegas: Lista de códigos de bodegas a validar
            sap_obligatorio: Si True, errores de SAP bloquean
            
        Returns:
            {
                "validas": List[str],  # Códigos que existen en SAP
                "no_encontradas": List[str],  # Códigos que NO existen
                "errores": List[str],  # Códigos con error al consultar
                "warnings": List[str],  # Warnings
                "todas_validas": bool,
                "detalle": Dict[str, Dict[str, Any]]
            }
        """
        from .pedido_sap_validator import PedidoSAPValidator
        sap_validator = PedidoSAPValidator()
        return sap_validator.validar_bodegas_existen_en_sap(
            codigos_bodegas=codigos_bodegas,
            sap_obligatorio=sap_obligatorio
        )
    
    def validar_tiendas_existen_en_sap(
        self,
        codigos_tiendas: List[str],
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de tienda existan directamente en SAP OWHS.
        
        NUEVO: Valida ID TIENDA contra SAP sin depender de catálogo Excel.
        Obtiene TODAS las tiendas de SAP y valida contra ese catálogo completo.
        
        REFACTORIZADO: Delega a PedidoSAPValidator para mantener compatibilidad.
        
        Args:
            codigos_tiendas: Lista de códigos de tiendas a validar (ej: ["ROL01", "ROL02"])
            sap_obligatorio: Si True, errores de SAP bloquean
            
        Returns:
            {
                "validas": List[str],  # Códigos que existen en SAP
                "no_encontradas": List[str],  # Códigos que NO existen
                "errores": List[str],  # Códigos con error al consultar
                "warnings": List[str],  # Warnings
                "todas_validas": bool,
                "detalle": Dict[str, Dict[str, Any]]
            }
        """
        from .pedido_sap_validator import PedidoSAPValidator
        sap_validator = PedidoSAPValidator()
        return sap_validator.validar_tiendas_existen_en_sap(
            codigos_tiendas=codigos_tiendas,
            sap_obligatorio=sap_obligatorio
        )
    
    def validar_coherencia_articulos(
        self,
        codigos_detalle: set,
        codigos_movimiento: set,
        mapear_a_filas: Optional[dict] = None
    ) -> dict:
        """
        Valida que TODOS los códigos en Movimiento estén en Detalle Articulos.
        
        REGLA ARQUITECTÓNICA: Movimiento depende de Detalle Articulos, no al revés.
        
        Esta es una validación de COHERENCIA INTERNA del pedido, no de existencia
        en SAP. Los códigos validados aquí ya fueron normalizados.
        
        Args:
            codigos_detalle: Códigos únicos de "Detalle Articulos"
            codigos_movimiento: Códigos únicos de "Movimiento"
            mapear_a_filas: Dict opcional {codigo: [filas]} para trazabilidad
            
        Returns:
            {
                "coherente": bool,
                "codigos_invalidos": List[str],
                "errores": List[Dict],
                "resumen": str
            }
        """
        resultado = {
            "coherente": True,
            "codigos_invalidos": [],
            "errores": [],
            "resumen": "Coherencia de artículos: OK"
        }
        
        # ✅ Normalizar inputs (robustez: no depender del caller)
        codigos_detalle_norm = {str(c).strip().upper() for c in (codigos_detalle or set()) if c}
        codigos_movimiento_norm = {str(c).strip().upper() for c in (codigos_movimiento or set()) if c}
        
        # ✅ Normalizar mapeo de filas si existe
        mapa_norm = {}
        if mapear_a_filas:
            mapa_norm = {
                str(k).strip().upper(): v
                for k, v in mapear_a_filas.items()
            }
        
        # ✅ Detectar códigos en Movimiento que NO están en Detalle
        diferencia = codigos_movimiento_norm - codigos_detalle_norm
        
        if diferencia:
            resultado["coherente"] = False
            resultado["codigos_invalidos"] = sorted(list(diferencia))
            resultado["resumen"] = (
                f"❌ {len(diferencia)} código(s) en 'Movimiento' no declarado(s) en 'Detalle Articulos'"
            )
            
            # ✅ Crear error por código (NO por fila dentro del validador)
            for codigo in sorted(diferencia):
                error_dict = {
                    "codigo": codigo,
                    "campo": "CODIGO PRODUCTO",
                    "tipo": "ERROR",
                    "severity": "CRITICO",
                    "mensaje": (
                        f"El código '{codigo}' está en 'Movimiento' "
                        f"pero NO está declarado en 'Detalle Articulos'. "
                        f"Todos los códigos de movimiento deben estar primero en Detalle Articulos."
                    ),
                    "accion_recomendada": (
                        f"Opción 1: Agregar '{codigo}' a 'Detalle Articulos'\n"
                        f"Opción 2: Eliminar '{codigo}' de 'Movimiento'"
                    ),
                    "ubicacion": "Hoja: Movimiento"
                }
                
                # Si existe mapeo, incluir filas (pero no explotar por fila aquí)
                if codigo in mapa_norm:
                    error_dict["filas"] = mapa_norm[codigo]
                
                resultado["errores"].append(error_dict)
        
        else:
            resultado["resumen"] = (
                f"✅ Coherencia OK: {len(codigos_movimiento_norm)} código(s) validado(s)"
            )
        
        logger.info(resultado["resumen"])
        return resultado
    
    def validar_tiendas_contra_catalogo(
        self,
        tiendas_movimiento: list,
        catalogo_tiendas: dict,
        mapear_a_filas: Optional[dict] = None
    ) -> dict:
        """
        Valida tiendas de Movimiento contra catálogo normalizado.
        
        REGLA: TODAS las tiendas en Movimiento deben estar en el catálogo y activas.
        
        Args:
            tiendas_movimiento: Códigos de tienda (pueden estar sin normalizar)
            catalogo_tiendas: Catálogo ya normalizado por leer_hoja_tiendas()
            mapear_a_filas: Dict {codigo: [filas]} para reportar por fila
            
        Returns:
            {
                "valido": bool,
                "tiendas_validas": List[str],
                "tiendas_no_encontradas": List[str],
                "tiendas_inactivas": List[str],
                "errores": List[Dict]
            }
        """
        resultado = {
            "valido": True,
            "tiendas_validas": [],
            "tiendas_no_encontradas": [],
            "tiendas_inactivas": [],
            "errores": []
        }
        
        # ✅ Normalizar tiendas de movimiento para comparación
        tiendas_normalizar = set()
        for tienda in tiendas_movimiento:
            if tienda:
                tienda_norm = str(tienda).strip().upper()
                tiendas_normalizar.add(tienda_norm)
        
        # Validar cada tienda
        for tienda_codigo in tiendas_normalizar:
            if tienda_codigo not in catalogo_tiendas:
                resultado["tiendas_no_encontradas"].append(tienda_codigo)
                resultado["valido"] = False
                
                error_dict = {
                    "campo": "IdTienda",
                    "tipo": "ERROR",
                    "mensaje": f"La tienda '{tienda_codigo}' no está declarada en la hoja 'Tiendas'",
                    "valor": tienda_codigo,
                    "accion_recomendada": f"Agregar '{tienda_codigo}' a la hoja 'Tiendas' con sus datos completos"
                }
                
                # Mapear a filas si se proporciona
                if mapear_a_filas and tienda_codigo in mapear_a_filas:
                    for fila in mapear_a_filas[tienda_codigo]:
                        error_dict_fila = error_dict.copy()
                        error_dict_fila["fila"] = fila
                        resultado["errores"].append(error_dict_fila)
                else:
                    resultado["errores"].append(error_dict)
            
            else:
                info_tienda = catalogo_tiendas[tienda_codigo]
                
                if not info_tienda.get("activa", True):
                    resultado["tiendas_inactivas"].append(tienda_codigo)
                    resultado["valido"] = False
                    
                    error_dict = {
                        "campo": "IdTienda",
                        "tipo": "ERROR",
                        "mensaje": f"La tienda '{tienda_codigo}' está marcada como INACTIVA",
                        "valor": tienda_codigo,
                        "accion_recomendada": f"Marcar '{tienda_codigo}' como activa en la hoja 'Tiendas' o usar otra tienda"
                    }
                    
                    # Mapear a filas
                    if mapear_a_filas and tienda_codigo in mapear_a_filas:
                        for fila in mapear_a_filas[tienda_codigo]:
                            error_dict_fila = error_dict.copy()
                            error_dict_fila["fila"] = fila
                            resultado["errores"].append(error_dict_fila)
                    else:
                        resultado["errores"].append(error_dict)
                
                else:
                    resultado["tiendas_validas"].append(tienda_codigo)
        
        return resultado
