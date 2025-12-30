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


