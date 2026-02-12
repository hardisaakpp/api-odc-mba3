"""
Servicio de exportación de pedidos en formato MBA (archivo plano .txt).

HU-08: Permite a usuarios de El Rayo descargar el pedido en archivo plano
para subirlo en el sistema MBA.

Formato MBA para importación de PEDIDOS DE CLIENTES:
- Archivo de texto con 35 columnas separadas por TAB
- Las primeras 19 filas son encabezado/instrucciones (se eliminan en importación)
- Cada línea de detalle corresponde a un producto-tienda (sucursal)
"""

import logging
from typing import Any, Optional
from datetime import datetime, date
from dataclasses import dataclass

from ..connection import get_db_connection_context
from ..repositories.pedido_repository import PedidoRepository

logger = logging.getLogger(__name__)


@dataclass
class MBAExportConfig:
    """Configuración para exportación a formato MBA.
    
    Estos valores deben ser configurados según los requerimientos del cliente.
    Algunos pueden venir del pedido, otros son constantes o configurables.
    """
    # Datos del cliente/empresa
    codigo_cliente: str = ""  # Ej: CLI0495
    codigo_subcliente: str = ""  # Ej: GO05 (dejar vacío si no aplica)
    
    # Configuración de moneda y bodega
    moneda: str = "US"  # Moneda por defecto
    bodega: str = ""  # Código de bodega MBA
    
    # Vendedor
    vendedor: str = ""  # Código de vendedor MBA
    
    # Configuraciones booleanas
    registro_editable: bool = True
    confirmado: bool = False
    aplica_impuesto_1: bool = True
    aplica_impuesto_2: bool = False
    
    # Número de pedido temporal (para agrupar líneas del mismo pedido)
    numero_pedido_temporal: int = 1


class MBAPedidoExporter:
    """Exportador de pedidos al formato MBA para importación."""
    
    # Encabezado del formato MBA (19 líneas que se eliminan al importar)
    MBA_HEADER = """ENTERPRISE SOFTWARE SOLUTIONS\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
FORMATO PARA IMPORTACIÓN :\tPEDIDOS DE CLIENTES\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
Las columnas que son tipo fecha, deben ingresarse según la configuración regional del computador\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
Las columnas de tipo numérico entero son sin decimales\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
Las primeras 19 FILAS incluida la linea azul se eliminaran automaticamente en el proceso de Importación\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
Campo Obligatorio\tDebe ingresar un valor en forma obligatoria\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
Campo Relacionado\tImplica que el código y descripción deben estar previamente creados\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
Campo Opcional\tPuede tener o no un valor para el proceso de importación\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
1\t2\t3\t4\t5\t6\t7\t8\t9\t10\t11\t12\t13\t14\t15\t16\t17\t18\t19\t20\t21\t22\t23\t24\t25\t26\t27\t28\t29\t30\t31\t32\t33\t34\t35
Numero\tNúmero Pedido \tCódigo Cliente\tCódigo SubCliente\tFecha Pedido\tFecha Entrega\tMoneda\tBodega\tVendedor\tPedido Manual\tContrato\tOrden Compra Cliente\tCotización Original\tMedio Captura\tTransporte\tNombre Solicitante\tMemo\tRegistro Editable por otro Usuario\tConfirmado\tSucursal\tCódigo Producto\t Cantidad Pedido \tBackOrder\t    Precio Final    \tAplica Impuesto 1\tDepartamento\tCentro Costo\tProyecto\tSubproyecto\tAnálisis 1\tAnálisis 2\tAnálisis 3\tPrecio Solicitado\tAplica Impuesto 2\tNumero
Integer\tNumérico Entero\tAlfa-numérico\tAlfa-numérico\tFecha\tFecha\tAlfa-numérico\tAlfa-numérico\tAlfa-numérico\tAlfa-numérico\tAlfa-numérico\tAlfa-numérico\tEntero Largo\tAlfa-numérico\tAlfa-numérico\tAlfa-numérico\tTexto\tBooleano\tBooleano\tTexto\tAlfa-numérico\t Real \tBooleano\t    Real    \tBooleano\tNumérico Entero\tNumérico Entero\tAlfa-numérico\tAlfa-numérico\tAlfa-numérico\tAlfa-numérico\tAlfa-numérico\tReal\tBooleano\tInteger
\t\t8\t8\tIMPORTANTE\tIMPORTANTE\t5\t5\t5\t20\t10\t20\t\t5\t5\t20\t\t\t\t3\t20\t\t\t\t\t5\t5\t15\t15\t15\t\t\t\t\t
Número secuencial de registro\tValor temporal de pedido, marca el bloque que corresponde a cada, este campo NO se almacenara en la Base de Datos\t\tSi no dispone de Subclientes se debera dejar en Blanco este Campo\tFORMATO DE FECHA DD/MM/YYYY, si el Campo NO lleva Datos llenarlo con 00/00/0000\tFORMATO DE FECHA DD/MM/YYYY, si el Campo NO lleva Datos llenarlo con 00/00/0000\t\t\t\t\t\t\tCampo relacionado con informacion de Medios de Captura, verifica la existencia del código respectivo\tCampo relacionado con informacion de Transporte, verifica la existencia del código respectivo\t\t\tVALORES POSIBLES TRUE/FALSE\tVALORES POSIBLES TRUE/FALSE\tEn este campo se debe registrar hasta 3 caracteres siempre\t\t\tESTA COLUMNA SIEMPRE TOMARA EL VALOR FALSE\t\tVALORES POSIBLES TRUE/FALSE\t\t\t\t\t\t\t\t\t\t\t
"Se aplicará el Impuesto 1 si en la Ficha del Producto tiene marcado aplicar Impuesto y si en la Ficha del Cliente lo permite."\t\t\t\t\t\t\t\t\tVALORES POSIBLES TRUE/FALSE\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t
"Se aplicará el Impuesto 2 si en la Ficha del Producto tiene marcado aplicar Impuesto y si en la Ficha del Cliente lo permite."\tNúmero secuencial de registro\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t"""
    
    @staticmethod
    def _format_date(date_value: Any) -> str:
        """Formatea una fecha al formato DD/MM/YYYY requerido por MBA.
        
        Args:
            date_value: Valor de fecha (string ISO, date, datetime, o None)
            
        Returns:
            Fecha formateada como DD/MM/YYYY o 00/00/0000 si no hay fecha
        """
        if not date_value:
            return "00/00/0000"
        
        try:
            if isinstance(date_value, str):
                # Intentar parsear fecha ISO (YYYY-MM-DD)
                if "T" in date_value:
                    date_value = date_value.split("T")[0]
                parsed = datetime.strptime(date_value, "%Y-%m-%d")
                return parsed.strftime("%d/%m/%Y")
            elif isinstance(date_value, (date, datetime)):
                return date_value.strftime("%d/%m/%Y")
            else:
                return "00/00/0000"
        except (ValueError, TypeError):
            return "00/00/0000"
    
    @staticmethod
    def _format_boolean(value: bool) -> str:
        """Formatea un booleano al formato TRUE/FALSE de MBA."""
        return "TRUE" if value else "FALSE"
    
    @staticmethod
    def _format_number(value: Any, decimals: int = 2) -> str:
        """Formatea un número al formato requerido.
        
        Args:
            value: Valor numérico
            decimals: Cantidad de decimales (0 para enteros)
            
        Returns:
            Número formateado como string
        """
        if value is None:
            return "0"
        
        try:
            num = float(value)
            if decimals == 0:
                return str(int(num))
            return f"{num:.{decimals}f}"
        except (ValueError, TypeError):
            return "0"
    
    @staticmethod
    def _get_sucursal_from_tienda(tienda_codigo: str) -> str:
        """Extrae el código de sucursal (3 caracteres) desde el código de tienda.
        
        El formato MBA espera hasta 3 caracteres para la sucursal.
        Ejemplos de mapeo típico:
        - TRL-QSN → TRL o QSN
        - TOUT-001 → TOU
        - PRI → PRI
        
        Args:
            tienda_codigo: Código de tienda del sistema
            
        Returns:
            Código de sucursal de 3 caracteres
        """
        if not tienda_codigo:
            return ""
        
        codigo = tienda_codigo.strip().upper()
        
        # Si ya es de 3 caracteres o menos, usar directamente
        if len(codigo) <= 3:
            return codigo
        
        # Si tiene guión, tomar la parte después del guión (puede ser más específica)
        if "-" in codigo:
            parts = codigo.split("-")
            # Tomar la última parte si es de 3 caracteres o menos
            if len(parts[-1]) <= 3:
                return parts[-1][:3]
            # Sino, tomar los primeros 3 del primer segmento
            return parts[0][:3]
        
        # Por defecto, tomar los primeros 3 caracteres
        return codigo[:3]
    
    def exportar_pedido_formato_mba(
        self,
        pedido_id: str,
        config: Optional[MBAExportConfig] = None,
        incluir_encabezado: bool = True
    ) -> bytes:
        """
        Exporta un pedido en formato MBA para importación de Pedidos de Clientes.
        
        Genera un archivo .txt con:
        - 19 líneas de encabezado (opcional, se eliminan al importar en MBA)
        - Líneas de detalle: una por cada combinación producto-tienda
        - 35 columnas separadas por TAB
        
        Args:
            pedido_id: UUID del pedido a exportar
            config: Configuración de exportación (valores por defecto si None)
            incluir_encabezado: Si True, incluye las 19 líneas de encabezado
            
        Returns:
            Bytes del archivo .txt en formato MBA
            
        Raises:
            ValueError: Si el pedido no existe
        """
        if config is None:
            config = MBAExportConfig()
        
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = repo.get_pedido_completo(pedido_id)
            
            if not pedido:
                raise ValueError(f"Pedido no encontrado: {pedido_id}")
            
            cabecera = pedido["cabecera"]
            detalles = pedido["detalles"]
            
            logger.info(f"📄 Exportando pedido {pedido_id} a formato MBA ({len(detalles)} productos)")
            
            # Extraer datos del pedido para usar en la exportación
            fecha_pedido = self._format_date(cabecera.get("fecha_pedido"))
            fecha_entrega = self._format_date(cabecera.get("fecha_entrega"))
            orden_compra_cliente = cabecera.get("mensaje") or ""
            bodega = config.bodega or cabecera.get("origen_traslado") or ""
            
            # Construir líneas del archivo
            lines = []
            
            # Agregar encabezado si se requiere
            if incluir_encabezado:
                lines.append(self.MBA_HEADER)
            
            # Contador secuencial de registros
            numero_secuencial = 1
            
            # Generar una línea por cada combinación producto-tienda
            for detalle in detalles:
                codigo_producto = detalle.get("codigo_interno") or ""
                precio_unitario = detalle.get("costo_doc_sin_iva") or 0
                
                for tienda in detalle.get("tiendas", []):
                    cantidad = tienda.get("cantidad", 0)
                    
                    # Omitir si la cantidad es 0
                    if cantidad <= 0:
                        continue
                    
                    tienda_codigo = tienda.get("codigo") or ""
                    sucursal = self._get_sucursal_from_tienda(tienda_codigo)
                    
                    # Construir las 35 columnas
                    columnas = [
                        self._format_number(numero_secuencial, 0),  # 1. Numero
                        self._format_number(config.numero_pedido_temporal, 0),  # 2. Número Pedido
                        config.codigo_cliente,  # 3. Código Cliente
                        config.codigo_subcliente,  # 4. Código SubCliente
                        fecha_pedido,  # 5. Fecha Pedido
                        fecha_entrega,  # 6. Fecha Entrega
                        config.moneda,  # 7. Moneda
                        bodega,  # 8. Bodega
                        config.vendedor,  # 9. Vendedor
                        "",  # 10. Pedido Manual
                        "",  # 11. Contrato
                        orden_compra_cliente,  # 12. Orden Compra Cliente
                        "",  # 13. Cotización Original
                        "",  # 14. Medio Captura
                        "",  # 15. Transporte
                        "",  # 16. Nombre Solicitante
                        "",  # 17. Memo
                        self._format_boolean(config.registro_editable),  # 18. Registro Editable
                        self._format_boolean(config.confirmado),  # 19. Confirmado
                        sucursal,  # 20. Sucursal (3 caracteres)
                        codigo_producto,  # 21. Código Producto
                        self._format_number(cantidad, 0),  # 22. Cantidad Pedido
                        "FALSE",  # 23. BackOrder (siempre FALSE)
                        self._format_number(precio_unitario, 3),  # 24. Precio Final
                        self._format_boolean(config.aplica_impuesto_1),  # 25. Aplica Impuesto 1
                        "",  # 26. Departamento
                        "",  # 27. Centro Costo
                        "",  # 28. Proyecto
                        "",  # 29. Subproyecto
                        "",  # 30. Análisis 1
                        "",  # 31. Análisis 2
                        "",  # 32. Análisis 3
                        "0",  # 33. Precio Solicitado
                        self._format_boolean(config.aplica_impuesto_2),  # 34. Aplica Impuesto 2
                        self._format_number(numero_secuencial, 0),  # 35. Numero (repetido)
                    ]
                    
                    # Unir columnas con TAB
                    line = "\t".join(columnas)
                    lines.append(line)
                    
                    numero_secuencial += 1
            
            logger.info(f"✅ Exportación MBA completada: {numero_secuencial - 1} líneas generadas")
            
            # Unir todas las líneas con salto de línea
            content = "\n".join(lines)
            
            # Convertir a bytes (UTF-8 sin BOM para compatibilidad con MBA)
            return content.encode("utf-8")
    
    def exportar_pedido_formato_mba_consolidado(
        self,
        pedido_id: str,
        config: Optional[MBAExportConfig] = None,
        incluir_encabezado: bool = True
    ) -> bytes:
        """
        Exporta un pedido en formato MBA consolidando cantidades por producto.
        
        A diferencia de exportar_pedido_formato_mba que genera una línea por tienda,
        este método consolida las cantidades y genera UNA línea por producto.
        
        Útil cuando el pedido no necesita distinguir por tienda/sucursal.
        
        Args:
            pedido_id: UUID del pedido a exportar
            config: Configuración de exportación
            incluir_encabezado: Si True, incluye las 19 líneas de encabezado
            
        Returns:
            Bytes del archivo .txt en formato MBA
        """
        if config is None:
            config = MBAExportConfig()
        
        with get_db_connection_context() as conn:
            repo = PedidoRepository(conn)
            pedido = repo.get_pedido_completo(pedido_id)
            
            if not pedido:
                raise ValueError(f"Pedido no encontrado: {pedido_id}")
            
            cabecera = pedido["cabecera"]
            detalles = pedido["detalles"]
            
            logger.info(f"📄 Exportando pedido {pedido_id} a formato MBA consolidado ({len(detalles)} productos)")
            
            # Extraer datos del pedido
            fecha_pedido = self._format_date(cabecera.get("fecha_pedido"))
            fecha_entrega = self._format_date(cabecera.get("fecha_entrega"))
            orden_compra_cliente = cabecera.get("mensaje") or ""
            bodega = config.bodega or cabecera.get("origen_traslado") or ""
            
            # Usar la primera tienda para la sucursal (o el campo bodega del config)
            sucursal_default = ""
            if detalles and detalles[0].get("tiendas"):
                primera_tienda = detalles[0]["tiendas"][0].get("codigo", "")
                sucursal_default = self._get_sucursal_from_tienda(primera_tienda)
            
            lines = []
            
            if incluir_encabezado:
                lines.append(self.MBA_HEADER)
            
            numero_secuencial = 1
            
            for detalle in detalles:
                codigo_producto = detalle.get("codigo_interno") or ""
                precio_unitario = detalle.get("costo_doc_sin_iva") or 0
                
                # Consolidar cantidad total de todas las tiendas
                cantidad_total = sum(t.get("cantidad", 0) for t in detalle.get("tiendas", []))
                
                if cantidad_total <= 0:
                    continue
                
                columnas = [
                    self._format_number(numero_secuencial, 0),
                    self._format_number(config.numero_pedido_temporal, 0),
                    config.codigo_cliente,
                    config.codigo_subcliente,
                    fecha_pedido,
                    fecha_entrega,
                    config.moneda,
                    bodega,
                    config.vendedor,
                    "",  # Pedido Manual
                    "",  # Contrato
                    orden_compra_cliente,
                    "",  # Cotización Original
                    "",  # Medio Captura
                    "",  # Transporte
                    "",  # Nombre Solicitante
                    "",  # Memo
                    self._format_boolean(config.registro_editable),
                    self._format_boolean(config.confirmado),
                    sucursal_default,
                    codigo_producto,
                    self._format_number(cantidad_total, 0),
                    "FALSE",
                    self._format_number(precio_unitario, 3),
                    self._format_boolean(config.aplica_impuesto_1),
                    "",  # Departamento
                    "",  # Centro Costo
                    "",  # Proyecto
                    "",  # Subproyecto
                    "",  # Análisis 1
                    "",  # Análisis 2
                    "",  # Análisis 3
                    "0",
                    self._format_boolean(config.aplica_impuesto_2),
                    self._format_number(numero_secuencial, 0),
                ]
                
                lines.append("\t".join(columnas))
                numero_secuencial += 1
            
            logger.info(f"✅ Exportación MBA consolidada completada: {numero_secuencial - 1} líneas")
            
            content = "\n".join(lines)
            return content.encode("utf-8")
