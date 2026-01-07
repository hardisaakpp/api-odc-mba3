"""
Motor de validación para pedidos desde Excel.
Valida datos pre-negocio antes de enviar al ERP.
"""

import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from dataclasses import dataclass
from enum import Enum
import pandas as pd

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severidad de la validación."""
    ERROR = "ERROR"      # Crítico - bloquea el proceso
    WARNING = "WARNING"  # Advertencia - no bloquea


@dataclass
class ValidationIssue:
    """Representa un problema de validación."""
    row_number: int  # Número de fila en el Excel (1-based)
    field: str       # Campo con el problema
    severity: ValidationSeverity
    message: str
    value: Any = None  # Valor que causó el problema


class PedidoValidator:
    """
    Motor de validación para pedidos.
    
    Valida:
    - Catálogo (códigos de producto no vacíos, caracteres válidos)
    - Tiendas (IdTienda corresponde a sucursal/almacén permitido)
    - Unidades (enteros, máximos razonables por tienda en relación a total)
    - Fechas (no pasadas si se usa fecha de entrega, formato correcto)
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
            iva_porcentaje: Porcentaje de IVA para validaciones (default: 12.0 para Ecuador)
            usar_comas_decimales: Si True, acepta comas como separador decimal (formato europeo)
        """
        self.tiendas_permitidas = set(t.upper() if t else None for t in (tiendas_permitidas or []))
        self.max_cantidad_por_tienda = max_cantidad_por_tienda
        self.max_cantidad_total = max_cantidad_total
        self.permitir_fechas_pasadas = permitir_fechas_pasadas
        self.validar_precios = validar_precios
        self.iva_porcentaje = iva_porcentaje
        self.usar_comas_decimales = usar_comas_decimales
        
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
        
        Args:
            cabecera: Diccionario con datos de cabecera
            row_number: Número de fila (para reporte)
            
        Returns:
            Lista de issues de validación
        """
        issues = []
        
        # Validar numero_pedido (obligatorio)
        numero_pedido = cabecera.get("numero_pedido")
        if not numero_pedido or not str(numero_pedido).strip():
            issues.append(ValidationIssue(
                row_number=row_number,
                field="numero_pedido",
                severity=ValidationSeverity.ERROR,
                message="El número de pedido es obligatorio",
                value=numero_pedido
            ))
        
        # Validar fecha_pedido
        fecha_pedido = cabecera.get("fecha_pedido")
        if fecha_pedido:
            fecha_parsed = None
            if isinstance(fecha_pedido, str):
                try:
                    fecha_parsed = datetime.strptime(fecha_pedido, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        fecha_parsed = datetime.strptime(fecha_pedido, "%d/%m/%Y").date()
                    except ValueError:
                        issues.append(ValidationIssue(
                            row_number=row_number,
                            field="fecha_pedido",
                            severity=ValidationSeverity.ERROR,
                            message="Formato de fecha inválido. Use YYYY-MM-DD o DD/MM/YYYY",
                            value=cabecera.get("fecha_pedido")
                        ))
            elif isinstance(fecha_pedido, date):
                fecha_parsed = fecha_pedido
            
            # Validar que fecha_pedido no sea muy antigua (ej: > 1 año)
            if fecha_parsed:
                hoy = date.today()
                if fecha_parsed < date(hoy.year - 1, hoy.month, hoy.day):
                    issues.append(ValidationIssue(
                        row_number=row_number,
                        field="fecha_pedido",
                        severity=ValidationSeverity.WARNING,
                        message=f"La fecha de pedido es muy antigua: {fecha_parsed}",
                        value=fecha_parsed
                    ))
        
        # Validar fecha_entrega
        fecha_entrega = cabecera.get("fecha_entrega")
        if fecha_entrega and str(fecha_entrega).upper() != "INMEDIATO":
            # Intentar parsear como fecha
            if isinstance(fecha_entrega, str):
                try:
                    fecha_entrega_dt = datetime.strptime(fecha_entrega, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        fecha_entrega_dt = datetime.strptime(fecha_entrega, "%d/%m/%Y").date()
                    except ValueError:
                        issues.append(ValidationIssue(
                            row_number=row_number,
                            field="fecha_entrega",
                            severity=ValidationSeverity.ERROR,
                            message="Formato de fecha de entrega inválido. Use YYYY-MM-DD, DD/MM/YYYY o 'INMEDIATO'",
                            value=fecha_entrega
                        ))
                        fecha_entrega_dt = None
                else:
                    # Validar que fecha_entrega no sea pasada (si no se permite)
                    if not self.permitir_fechas_pasadas and fecha_entrega_dt:
                        hoy = date.today()
                        if fecha_entrega_dt < hoy:
                            issues.append(ValidationIssue(
                                row_number=row_number,
                                field="fecha_entrega",
                                severity=ValidationSeverity.ERROR,
                                message=f"La fecha de entrega no puede ser pasada: {fecha_entrega_dt}",
                                value=fecha_entrega_dt
                            ))
        
        return issues
    
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
                
                # Validar cantidad
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
                        cantidad_int = int(cantidad)
                        if cantidad_int <= 0:
                            issues.append(ValidationIssue(
                                row_number=row_number,
                                field="cantidad",
                                severity=ValidationSeverity.ERROR,
                                message=f"La cantidad debe ser mayor a 0. Valor recibido: {cantidad}",
                                value=cantidad
                            ))
                        elif cantidad_int != cantidad:  # Verificar que sea entero
                            issues.append(ValidationIssue(
                                row_number=row_number,
                                field="cantidad",
                                severity=ValidationSeverity.WARNING,
                                message=f"La cantidad debería ser un número entero. Se recibió: {cantidad}, se usará: {cantidad_int}",
                                value=cantidad
                            ))
                        else:
                            cantidad_total += cantidad_int
                            
                            # Validar límite por tienda
                            if self.max_cantidad_por_tienda and cantidad_int > self.max_cantidad_por_tienda:
                                issues.append(ValidationIssue(
                                    row_number=row_number,
                                    field="cantidad",
                                    severity=ValidationSeverity.WARNING,
                                    message=f"La cantidad para la tienda '{tienda_codigo}' ({cantidad_int}) excede el límite razonable por tienda ({self.max_cantidad_por_tienda})",
                                    value=cantidad_int
                                ))
                    except (ValueError, TypeError):
                        issues.append(ValidationIssue(
                            row_number=row_number,
                            field="cantidad",
                            severity=ValidationSeverity.ERROR,
                            message=f"La cantidad debe ser un número entero válido. Valor recibido: {cantidad}",
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
        
        Valida:
        - Formato numérico (puntos vs comas como separador decimal)
        - Precios positivos
        - Descuentos en rango válido (0-100%)
        - Coherencia entre costo, descuento y PVP
        - Coherencia entre subtotal y total
        
        Args:
            detalle: Diccionario con datos del detalle
            row_number: Número de fila en el Excel
            
        Returns:
            Lista de issues de validación
        """
        issues = []
        
        def parse_numeric_value(value: Any, field_name: str) -> Optional[float]:
            """Parsea un valor numérico, manejando formato regional."""
            if value is None or pd.isna(value):
                return None
            
            # Convertir a string y limpiar
            str_value = str(value).strip()
            if not str_value:
                return None
            
            # Remover símbolos de moneda comunes
            str_value = str_value.replace('$', '').replace('€', '').replace('USD', '').strip()
            
            # Manejar formato regional (comas vs puntos)
            if self.usar_comas_decimales:
                # Formato europeo: 10,50 (coma como decimal)
                # Reemplazar punto de miles por nada y coma por punto
                if '.' in str_value and ',' in str_value:
                    # Tiene ambos: asumir punto=miles, coma=decimal
                    str_value = str_value.replace('.', '').replace(',', '.')
                elif ',' in str_value:
                    # Solo coma: es decimal
                    str_value = str_value.replace(',', '.')
            else:
                # Formato estándar: 10.50 (punto como decimal)
                # Reemplazar coma por punto (si hay coma, asumir que es decimal mal formateado)
                if ',' in str_value and '.' not in str_value:
                    # Solo coma: intentar como decimal
                    str_value = str_value.replace(',', '.')
                elif ',' in str_value and '.' in str_value:
                    # Tiene ambos: asumir coma=miles, punto=decimal
                    str_value = str_value.replace(',', '')
            
            try:
                return float(str_value)
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field=field_name,
                    severity=ValidationSeverity.ERROR,
                    message=f"El valor de {field_name} no es un número válido. Valor recibido: {value}",
                    value=value
                ))
                return None
        
        # Validar costo sin IVA
        costo_sin_iva = parse_numeric_value(detalle.get("costo_doc_sin_iva"), "costo_doc_sin_iva")
        if costo_sin_iva is not None:
            if costo_sin_iva < 0:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="costo_doc_sin_iva",
                    severity=ValidationSeverity.ERROR,
                    message="El costo sin IVA no puede ser negativo",
                    value=costo_sin_iva
                ))
            elif costo_sin_iva == 0:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="costo_doc_sin_iva",
                    severity=ValidationSeverity.WARNING,
                    message="El costo sin IVA es cero. Verifique que sea correcto",
                    value=costo_sin_iva
                ))
        
        # Validar descuento
        descuento = parse_numeric_value(detalle.get("descuento_1"), "descuento_1")
        descuento_porcentaje = None
        
        if descuento is not None:
            # El descuento puede venir como porcentaje (0-100) o como decimal (0-1)
            if descuento > 1 and descuento <= 100:
                # Está como porcentaje (ej: 20 para 20%)
                descuento_porcentaje = descuento
            elif descuento >= 0 and descuento <= 1:
                # Está como decimal (ej: 0.20 para 20%)
                descuento_porcentaje = descuento * 100
            else:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="descuento_1",
                    severity=ValidationSeverity.ERROR,
                    message=f"El descuento debe estar entre 0 y 100% (o 0 y 1 si es decimal). Valor recibido: {descuento}",
                    value=descuento
                ))
            
            if descuento_porcentaje is not None:
                if descuento_porcentaje < 0 or descuento_porcentaje > 100:
                    issues.append(ValidationIssue(
                        row_number=row_number,
                        field="descuento_1",
                        severity=ValidationSeverity.ERROR,
                        message=f"El descuento debe estar entre 0 y 100%. Valor recibido: {descuento_porcentaje}%",
                        value=descuento
                    ))
                elif descuento_porcentaje > 50:
                    issues.append(ValidationIssue(
                        row_number=row_number,
                        field="descuento_1",
                        severity=ValidationSeverity.WARNING,
                        message=f"El descuento es muy alto ({descuento_porcentaje}%). Verifique que sea correcto",
                        value=descuento
                    ))
        
        # Validar PVP (Precio de Venta al Público)
        pvp = parse_numeric_value(detalle.get("pvp"), "pvp")
        if pvp is not None:
            if pvp < 0:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="pvp",
                    severity=ValidationSeverity.ERROR,
                    message="El PVP no puede ser negativo",
                    value=pvp
                ))
            elif pvp == 0:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="pvp",
                    severity=ValidationSeverity.WARNING,
                    message="El PVP es cero. Verifique que sea correcto",
                    value=pvp
                ))
            
            # Validar coherencia: PVP debería ser >= costo (después de aplicar descuento)
            if costo_sin_iva is not None and pvp > 0:
                costo_con_iva = costo_sin_iva * (1 + self.iva_porcentaje / 100)
                if descuento is not None and descuento_porcentaje is not None:
                    costo_con_descuento = costo_con_iva * (1 - descuento_porcentaje / 100)
                else:
                    costo_con_descuento = costo_con_iva
                
                # PVP debería ser razonablemente mayor o igual al costo con descuento
                # Permitir hasta 10% de diferencia por redondeo
                if pvp < costo_con_descuento * 0.9:
                    issues.append(ValidationIssue(
                        row_number=row_number,
                        field="pvp",
                        severity=ValidationSeverity.WARNING,
                        message=f"El PVP ({pvp:.2f}) es menor que el costo con IVA y descuento ({costo_con_descuento:.2f}). Verifique los cálculos",
                        value=pvp
                    ))
        
        # Validar subtotal y total
        subtotal = parse_numeric_value(detalle.get("subtotal"), "subtotal")
        total = parse_numeric_value(detalle.get("total"), "total")
        
        if subtotal is not None and subtotal < 0:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="subtotal",
                severity=ValidationSeverity.ERROR,
                message="El subtotal no puede ser negativo",
                value=subtotal
            ))
        
        if total is not None and total < 0:
            issues.append(ValidationIssue(
                row_number=row_number,
                field="total",
                severity=ValidationSeverity.ERROR,
                message="El total no puede ser negativo",
                value=total
            ))
        
        # Validar coherencia: total debería ser >= subtotal
        if subtotal is not None and total is not None:
            if total < subtotal:
                issues.append(ValidationIssue(
                    row_number=row_number,
                    field="total",
                    severity=ValidationSeverity.WARNING,
                    message=f"El total ({total:.2f}) es menor que el subtotal ({subtotal:.2f}). Verifique los cálculos",
                    value=total
                ))
        
        return issues
    
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
        
        REGLAS DE VALIDACIÓN:
        - ItemCode debe coincidir EXACTO con el código del Excel
        - Si SAP no responde y sap_obligatorio=True → ERROR
        - Si SAP no responde y sap_obligatorio=False → WARNING
        - Código no encontrado → ERROR (siempre)
        
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
        from ..services.sap_service import SAPService
        from src.config import ENABLE_SAP_QUERIES
        
        if not codigos_productos:
            return {
                "validos": [],
                "no_encontrados": [],
                "errores": [],
                "warnings": [],
                "todos_validos": True,
                "detalle": {}
            }
        
        # Verificar si SAP está habilitado
        if not ENABLE_SAP_QUERIES:
            logger.warning("⚠️ Consultas SAP deshabilitadas (ENABLE_SAP_QUERIES=False)")
            if sap_obligatorio:
                # Si SAP es obligatorio pero está deshabilitado, todo es error
                detalle = {
                    codigo: {
                        "existe": False,
                        "info": None,
                        "error": "SAP deshabilitado",
                        "severity": "ERROR"
                    }
                    for codigo in codigos_productos
                }
                return {
                    "validos": [],
                    "no_encontrados": [],
                    "errores": list(codigos_productos),
                    "warnings": [],
                    "todos_validos": False,
                    "detalle": detalle
                }
            else:
                # Si no es obligatorio, retornar warnings
                detalle = {
                    codigo: {
                        "existe": False,
                        "info": None,
                        "error": "SAP deshabilitado",
                        "severity": "WARNING"
                    }
                    for codigo in codigos_productos
                }
                return {
                    "validos": [],
                    "no_encontrados": [],
                    "errores": [],
                    "warnings": list(codigos_productos),
                    "todos_validos": False,
                    "detalle": detalle
                }
        
        detalle = {}
        validos = []
        no_encontrados = []
        errores = []
        warnings = []
        
        # Usar SAPService que tiene cache
        sap_service = SAPService()
        
        for codigo in codigos_productos:
            try:
                # Normalizar código (quitar espacios)
                codigo_clean = codigo.strip() if codigo else ""
                
                if not codigo_clean:
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "Código vacío",
                        "severity": "ERROR"
                    }
                    no_encontrados.append(codigo)
                    continue
                
                # Consultar SAP (usa cache si está disponible)
                producto_info = sap_service.get_or_fetch_producto_info(codigo_clean)
                
                # Verificar si hay error
                if producto_info and producto_info.get("_error"):
                    error_type = producto_info.get("_error_type")
                    
                    if error_type == "no_existe":
                        # Código no existe en SAP → ERROR siempre
                        detalle[codigo] = {
                            "existe": False,
                            "info": None,
                            "error": "no_existe",
                            "severity": "ERROR",
                            "mensaje": f"El código '{codigo_clean}' no existe en SAP"
                        }
                        no_encontrados.append(codigo)
                        
                    elif error_type == "mismatch":
                        # SAP retornó un ItemCode diferente → ERROR (no coincide exacto)
                        item_code_sap = producto_info.get("_item_code_sap", "N/A")
                        detalle[codigo] = {
                            "existe": False,
                            "info": None,
                            "error": "mismatch",
                            "severity": "ERROR",
                            "mensaje": f"El código '{codigo_clean}' no coincide exacto con ItemCode SAP '{item_code_sap}'",
                            "item_code_sap": item_code_sap
                        }
                        no_encontrados.append(codigo)
                        
                    elif error_type == "error":
                        # Error de conexión o consulta a SAP
                        error_msg = producto_info.get("_error_message", "Error desconocido")
                        severity = "ERROR" if sap_obligatorio else "WARNING"
                        
                        detalle[codigo] = {
                            "existe": False,
                            "info": None,
                            "error": error_type,
                            "severity": severity,
                            "mensaje": f"Error al consultar SAP para '{codigo_clean}': {error_msg}"
                        }
                        
                        if sap_obligatorio:
                            errores.append(codigo)
                        else:
                            warnings.append(codigo)
                    else:
                        # Error desconocido
                        severity = "ERROR" if sap_obligatorio else "WARNING"
                        detalle[codigo] = {
                            "existe": False,
                            "info": None,
                            "error": error_type or "error_desconocido",
                            "severity": severity
                        }
                        if sap_obligatorio:
                            errores.append(codigo)
                        else:
                            warnings.append(codigo)
                            
                elif producto_info:
                    # ✅ Producto encontrado correctamente - ItemCode coincide exacto
                    detalle[codigo] = {
                        "existe": True,
                        "info": {
                            "item_code": producto_info.get("item_code"),
                            "item_name": producto_info.get("item_name"),
                            "pack_sap": producto_info.get("pack_sap"),
                            "grupo_articulos": producto_info.get("grupo_articulos"),
                            "unidad_conversion": producto_info.get("unidad_conversion")
                        },
                        "severity": None
                    }
                    validos.append(codigo)
                    logger.debug(f"✅ Código validado en SAP: {codigo_clean}")
                    
                else:
                    # None retornado sin error (caso edge, tratarlo como no existe)
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "no_existe",
                        "severity": "ERROR",
                        "mensaje": f"No se encontró información en SAP para '{codigo_clean}'"
                    }
                    no_encontrados.append(codigo)
                    
            except Exception as e:
                logger.error(f"❌ Error inesperado al validar código {codigo} en SAP: {e}", exc_info=True)
                severity = "ERROR" if sap_obligatorio else "WARNING"
                detalle[codigo] = {
                    "existe": False,
                    "info": None,
                    "error": str(e),
                    "severity": severity
                }
                if sap_obligatorio:
                    errores.append(codigo)
                else:
                    warnings.append(codigo)
        
        todos_validos = len(no_encontrados) == 0 and len(errores) == 0
        
        logger.info(
            f"📊 Validación SAP completada: {len(validos)} válidos, "
            f"{len(no_encontrados)} no encontrados, {len(errores)} errores, {len(warnings)} warnings"
        )
        
        return {
            "validos": validos,
            "no_encontrados": no_encontrados,
            "errores": errores,
            "warnings": warnings,
            "todos_validos": todos_validos,
            "detalle": detalle
        }
    
    def validar_bodegas_existen_en_sap(
        self,
        codigos_bodegas: List[str],
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de bodega existan en SAP OWHS.
        Obtiene TODAS las bodegas de SAP y valida contra ese catálogo completo.
        
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
        from ..clients.sap_client import SAPClient
        from src.config import ENABLE_SAP_QUERIES
        
        if not codigos_bodegas:
            return {
                "validas": [],
                "no_encontradas": [],
                "errores": [],
                "warnings": [],
                "todas_validas": True,
                "detalle": {}
            }
        
        if not ENABLE_SAP_QUERIES:
            logger.warning("⚠️ Consultas SAP deshabilitadas (ENABLE_SAP_QUERIES=False)")
            if sap_obligatorio:
                detalle = {
                    codigo: {
                        "existe": False,
                        "info": None,
                        "error": "SAP deshabilitado",
                        "severity": "ERROR"
                    }
                    for codigo in codigos_bodegas
                }
                return {
                    "validas": [],
                    "no_encontradas": [],
                    "errores": list(codigos_bodegas),
                    "warnings": [],
                    "todas_validas": False,
                    "detalle": detalle
                }
            else:
                detalle = {
                    codigo: {
                        "existe": False,
                        "info": None,
                        "error": "SAP deshabilitado",
                        "severity": "WARNING"
                    }
                    for codigo in codigos_bodegas
                }
                return {
                    "validas": [],
                    "no_encontradas": [],
                    "errores": [],
                    "warnings": list(codigos_bodegas),
                    "todas_validas": False,
                    "detalle": detalle
                }
        
        detalle = {}
        validas = []
        no_encontradas = []
        errores = []
        warnings = []
        
        sap_client = SAPClient()
        
        try:
            # Obtener TODAS las bodegas de SAP de una sola vez
            logger.info("🔍 Obteniendo catálogo completo de bodegas desde SAP OWHS")
            todas_bodegas_sap = sap_client.get_todas_bodegas()
            
            if not todas_bodegas_sap:
                logger.error("❌ No se pudo obtener el catálogo de bodegas desde SAP")
                if sap_obligatorio:
                    detalle = {
                        codigo: {
                            "existe": False,
                            "info": None,
                            "error": "No se pudo obtener catálogo SAP",
                            "severity": "ERROR"
                        }
                        for codigo in codigos_bodegas
                    }
                    return {
                        "validas": [],
                        "no_encontradas": [],
                        "errores": list(codigos_bodegas),
                        "warnings": [],
                        "todas_validas": False,
                        "detalle": detalle
                    }
            
            # Crear diccionario de bodegas SAP para búsqueda rápida
            bodegas_sap_dict = {
                bodega["WhsCode"]: bodega 
                for bodega in todas_bodegas_sap 
                if bodega.get("WhsCode")
            }
            
            logger.info(f"📋 Catálogo SAP: {len(bodegas_sap_dict)} bodegas disponibles")
            
            # Validar cada código contra el catálogo
            for codigo in codigos_bodegas:
                codigo_clean = codigo.strip() if codigo else ""
                
                if not codigo_clean:
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "Código vacío",
                        "severity": "ERROR"
                    }
                    no_encontradas.append(codigo)
                    continue
                
                # Buscar en el catálogo SAP
                if codigo_clean in bodegas_sap_dict:
                    bodega_info = bodegas_sap_dict[codigo_clean]
                    detalle[codigo] = {
                        "existe": True,
                        "info": bodega_info,
                        "error": None,
                        "severity": None
                    }
                    validas.append(codigo)
                    logger.debug(f"✅ Bodega validada en SAP: {codigo_clean}")
                else:
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "no_existe",
                        "severity": "ERROR",
                        "mensaje": f"La bodega '{codigo_clean}' no existe en SAP OWHS"
                    }
                    no_encontradas.append(codigo)
                    
        except Exception as e:
            logger.error(f"❌ Error al validar bodegas en SAP: {e}", exc_info=True)
            severity = "ERROR" if sap_obligatorio else "WARNING"
            for codigo in codigos_bodegas:
                detalle[codigo] = {
                    "existe": False,
                    "info": None,
                    "error": str(e),
                    "severity": severity
                }
                if sap_obligatorio:
                    errores.append(codigo)
                else:
                    warnings.append(codigo)
        
        todas_validas = len(no_encontradas) == 0 and len(errores) == 0
        
        logger.info(
            f"📊 Validación bodegas SAP: {len(validas)} válidas, "
            f"{len(no_encontradas)} no encontradas, {len(errores)} errores"
        )
        
        return {
            "validas": validas,
            "no_encontradas": no_encontradas,
            "errores": errores,
            "warnings": warnings,
            "todas_validas": todas_validas,
            "detalle": detalle
        }
    
    def validar_tiendas_existen_en_sap(
        self,
        codigos_tiendas: List[str],
        sap_obligatorio: bool = True
    ) -> Dict[str, Any]:
        """
        Valida que los códigos de tienda existan directamente en SAP OWHS.
        
        NUEVO: Valida ID TIENDA contra SAP sin depender de catálogo Excel.
        Obtiene TODAS las tiendas de SAP y valida contra ese catálogo completo.
        
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
        validas = []
        no_encontradas = []
        errores = []
        warnings = []
        detalle = {}
        
        from ..clients.sap_client import SAPClient
        
        sap_client = SAPClient()
        
        try:
            # Obtener TODAS las tiendas de SAP de una sola vez
            logger.info("🔍 Obteniendo catálogo completo de tiendas desde SAP OWHS")
            todas_tiendas_sap = sap_client.get_todas_bodegas()
            
            if not todas_tiendas_sap:
                logger.error("❌ No se pudo obtener el catálogo de tiendas desde SAP")
                if sap_obligatorio:
                    detalle = {
                        codigo: {
                            "existe": False,
                            "info": None,
                            "error": "No se pudo obtener catálogo SAP",
                            "severity": "ERROR"
                        }
                        for codigo in codigos_tiendas
                    }
                    return {
                        "validas": [],
                        "no_encontradas": [],
                        "errores": list(codigos_tiendas),
                        "warnings": [],
                        "todas_validas": False,
                        "detalle": detalle
                    }
            
            # Crear diccionario de tiendas SAP para búsqueda rápida por código
            # SAP usa WhsCode (ej: "ROL01", "ROL02") como clave
            tiendas_sap_dict = {}
            for tienda in todas_tiendas_sap:
                whscode = tienda.get("WhsCode")
                if whscode:
                    # Normalizar: SAP usa mayúsculas
                    tiendas_sap_dict[whscode.upper()] = tienda
            
            logger.info(f"📋 Catálogo SAP: {len(tiendas_sap_dict)} tiendas disponibles")
            
            # Validar cada código contra el catálogo
            for codigo in codigos_tiendas:
                codigo_clean = codigo.strip() if codigo else ""
                
                if not codigo_clean:
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "Código vacío",
                        "severity": "ERROR"
                    }
                    no_encontradas.append(codigo)
                    continue
                
                # Normalizar para búsqueda
                codigo_upper = codigo_clean.upper()
                
                # Buscar en el catálogo SAP
                if codigo_upper in tiendas_sap_dict:
                    tienda_info = tiendas_sap_dict[codigo_upper]
                    detalle[codigo] = {
                        "existe": True,
                        "info": {
                            "codigo": tienda_info.get("WhsCode"),
                            "nombre": tienda_info.get("WhsName"),
                            "ubicacion": tienda_info.get("Location"),
                            "activa": tienda_info.get("Inactive", "N") != "Y"
                        },
                        "error": None,
                        "severity": None
                    }
                    validas.append(codigo)
                    logger.debug(f"✅ Tienda validada en SAP: {codigo_clean}")
                else:
                    detalle[codigo] = {
                        "existe": False,
                        "info": None,
                        "error": "no_existe",
                        "severity": "ERROR",
                        "mensaje": f"La tienda '{codigo_clean}' no existe en SAP OWHS"
                    }
                    no_encontradas.append(codigo)
                    logger.warning(f"⚠️ Tienda {codigo_clean} no encontrada en SAP")
                    
        except Exception as e:
            logger.error(f"❌ Error al validar tiendas en SAP: {e}", exc_info=True)
            severity = "ERROR" if sap_obligatorio else "WARNING"
            for codigo in codigos_tiendas:
                detalle[codigo] = {
                    "existe": False,
                    "info": None,
                    "error": str(e),
                    "severity": severity
                }
                if sap_obligatorio:
                    errores.append(codigo)
                else:
                    warnings.append(codigo)
        
        todas_validas = len(no_encontradas) == 0 and len(errores) == 0
        
        logger.info(
            f"📊 Validación tiendas SAP: {len(validas)} válidas, "
            f"{len(no_encontradas)} no encontradas, {len(errores)} errores"
        )
        
        return {
            "validas": validas,
            "no_encontradas": no_encontradas,
            "errores": errores,
            "warnings": warnings,
            "todas_validas": todas_validas,
            "detalle": detalle
        }
    
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
