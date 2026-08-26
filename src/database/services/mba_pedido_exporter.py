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
from ..repositories.orden_compra_repository import OrdenCompraRepository
from ..pedido_estados import ESTADO_REDISTRIBUCION

logger = logging.getLogger(__name__)

_FECHA_VACIA = "00/00/0000"

# Bodega MBA fija para el TXT de pedidos de El Rayo (col. H, siempre "BPT")
_BODEGA_FIJA = "BPT"

# Sucursal MBA fija para el TXT de pedidos de El Rayo (col. 20, siempre "PRI")
_SUCURSAL_FIJA = "PRI"

# Vendedor MBA derivado de la bodega/marca de origen del traslado (req. 1.7):
# RL-CD (ROLAND) y RG-CD (REGIONS) -> "mrz"; OUT-CD (DESCUENTON) -> "descu".
_VENDEDOR_POR_ORIGEN = {
    "RL-CD": "mrz",
    "RG-CD": "mrz",
    "OUT-CD": "descu",
}


@dataclass
class MBAExportConfig:
    """Configuración para exportación a formato MBA.
    
    Valores por defecto para El Rayo: código cliente CLI1795, moneda US (dólar).
    Otros campos vienen del pedido: numero_pedido como Pedido Manual (col. 10),
    DocNum de la OC en SAP como Orden Compra Cliente (col. 12), codigo_interno,
    costo_doc_sin_iva como Precio Final.

    Columnas fijas en el TXT: A=secuencial, B=número pedido (agrupa líneas), C=CLI1795,
    G=moneda (US), H=bodega (BPT), 20=sucursal (PRI), AI/35=secuencial.
    """
    # Datos del cliente/empresa (por defecto El Rayo)
    codigo_cliente: str = "CLI1795"  # Código cliente MBA - fijo para esta implementación
    codigo_subcliente: str = ""  # Dejar vacío si no aplica

    # Configuración de moneda (moneda local = dólar US)
    moneda: str = "US"  # Divisa local

    # Vendedor (si vacío, se deriva de origen_traslado: RL-CD/RG-CD -> "mrz", OUT-CD -> "descu")
    vendedor: str = ""  # Código de vendedor MBA
    
    # Configuraciones booleanas
    registro_editable: bool = True
    confirmado: bool = False
    aplica_impuesto_1: bool = True
    aplica_impuesto_2: bool = False
    
    # Número de pedido temporal (col B: agrupa todas las líneas del mismo pedido)
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
            return _FECHA_VACIA
        
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
                return _FECHA_VACIA
        except (ValueError, TypeError):
            return _FECHA_VACIA
    
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
    def _mapear_tiendas_a_bodega(detalles: list) -> dict:
        """Resuelve la bodega de cada código de tienda distinto del pedido, UNA sola vez.

        StockTransferService.obtener_bodega_de_tienda hace una consulta a BD (remota)
        por llamada -- sin este cache, un pedido de N líneas con las mismas pocas
        tiendas repetidas dispara N consultas redundantes (medido: pedido de 12 líneas
        -> 36 conexiones nuevas -> ~31s de respuesta). Se calcula solo cuando se va a
        filtrar por bodega (ver exportar_pedido_formato_mba*)."""
        from .stock_transfer_service import StockTransferService

        codigos = {
            tienda.get("codigo")
            for detalle in detalles
            for tienda in detalle.get("tiendas", [])
            if tienda.get("codigo")
        }
        return {codigo: StockTransferService.obtener_bodega_de_tienda(codigo) for codigo in codigos}

    @staticmethod
    def _filtrar_tiendas_por_bodega(tiendas: list, codigo_bodega: Optional[str], bodega_por_codigo: dict) -> list:
        """Filtra las tiendas de un detalle a las que pertenecen a `codigo_bodega`
        (mismo criterio de StockTransferService.obtener_bodega_de_tienda usado para
        crear las ODCs por bodega, ver PedidoOCService.crear_ocs_desde_pedido_confirmado).
        Sin filtro (codigo_bodega=None) devuelve todas las tiendas, igual que antes."""
        if not codigo_bodega:
            return tiendas
        return [t for t in tiendas if bodega_por_codigo.get(t.get("codigo")) == codigo_bodega]

    @staticmethod
    def _resolver_vendedor(cabecera: dict, config: "MBAExportConfig") -> str:
        """Resuelve el código de vendedor: valor manual de config si existe,
        sino se deriva de la bodega/marca de origen del traslado (RL-CD/RG-CD -> mrz,
        OUT-CD -> descu)."""
        if config.vendedor:
            return config.vendedor
        origen_traslado = (cabecera.get("origen_traslado") or "").strip().upper()
        return _VENDEDOR_POR_ORIGEN.get(origen_traslado, "")

    @staticmethod
    def _extraer_datos_exportacion(
        cabecera: dict,
        config: "MBAExportConfig",
        fecha_confirmacion: Optional[datetime],
        doc_num: Optional[str],
    ) -> dict:
        """Extrae y normaliza los datos de cabecera y config para la exportación MBA.

        fecha_pedido y fecha_entrega (cols. 5 y 6) usan la fecha en que el pedido
        transicionó a CONFIRMADO POR EL RAYO (clic en "Confirmar"), no las fechas
        capturadas originalmente en el Excel/creación del pedido.

        Excepción -- pedido "hijo" (cabecera.pedido_padre_id no nulo, ver
        PedidoService.crear_pedido_hijo_diferencia): el hijo nunca transiciona por
        ESTADO_REDISTRIBUCION (pasa de PRODUCCION_POSPUESTA a LISTO_PARA_REDISTRIBUCION
        directo, ver pedido_estados.py), así que `fecha_confirmacion` siempre sería None
        para él. El hijo ya guarda sus propias fecha_pedido (instante del clic en
        "Confirmar pedido y generar nuevo pedido con la diferencia") y fecha_entrega
        (la que el admin elige para esa porción) como columnas propias de su cabecera
        -- se usan directo, sin ir a la bitácora.

        pedido_manual (col. 10) es el número de pedido interno; orden_compra_cliente
        (col. 12) es el DocNum de la Orden de Compra ya enviada a SAP.
        """
        fd = MBAPedidoExporter._format_date
        if cabecera.get("pedido_padre_id"):
            fecha_pedido_fmt = fd(cabecera.get("fecha_pedido"))
            fecha_entrega_fmt = fd(cabecera.get("fecha_entrega"))
        else:
            fecha_pedido_fmt = fecha_entrega_fmt = fd(fecha_confirmacion)
        return {
            "fecha_pedido": fecha_pedido_fmt,
            "fecha_entrega": fecha_entrega_fmt,
            "pedido_manual": (cabecera.get("numero_pedido") or "").strip(),
            "orden_compra_cliente": (doc_num or "").strip(),
            "bodega": _BODEGA_FIJA,
            "vendedor": MBAPedidoExporter._resolver_vendedor(cabecera, config),
            "codigo_cliente": (config.codigo_cliente or "CLI1795").strip(),
            "moneda": (config.moneda or "US").strip(),
        }

    @staticmethod
    def _resolver_precio_unitario(detalle: dict) -> float:
        """Resuelve el precio unitario: costo_doc_sin_iva con fallback a pvp."""
        precio = detalle.get("costo_doc_sin_iva")
        if precio is None:
            precio = detalle.get("pvp") or 0
        try:
            return float(precio)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _excluido_por_total_manual_cero(detalle: dict) -> bool:
        """True si el usuario editó manualmente el Total del producto a 0 en el
        Detalle del Pedido (total_modificado_manual=1 y total=0/None): ese
        producto no debe exportarse al TXT MBA3."""
        return bool(detalle.get("total_modificado_manual")) and not detalle.get("total")

    def exportar_pedido_formato_mba(
        self,
        pedido_id: str,
        config: Optional[MBAExportConfig] = None,
        incluir_encabezado: bool = True,
        codigo_bodega: Optional[str] = None,
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
            codigo_bodega: Si se indica (pedido con más de una ODC, una por bodega -- ver
                StockTransferService.detectar_origenes_traslado), limita la exportación a
                las tiendas de esa bodega y usa el DocNum de la ODC de esa bodega en vez
                de una ODC arbitraria del pedido. None exporta todas las tiendas con el
                DocNum de la ODC más reciente (comportamiento histórico, pedido con 1 ODC).

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

            fecha_confirmacion = repo.get_fecha_confirmacion_estado(pedido_id, ESTADO_REDISTRIBUCION)
            oc_repo = OrdenCompraRepository(conn)
            doc_num = (
                oc_repo.get_doc_num_by_pedido_id_y_bodega(pedido_id, codigo_bodega)
                if codigo_bodega else oc_repo.get_doc_num_by_pedido_id(pedido_id)
            )
            datos = self._extraer_datos_exportacion(cabecera, config, fecha_confirmacion, doc_num)
            fecha_pedido = datos["fecha_pedido"]
            fecha_entrega = datos["fecha_entrega"]
            pedido_manual = datos["pedido_manual"]
            orden_compra_cliente = datos["orden_compra_cliente"]
            bodega = datos["bodega"]
            vendedor = datos["vendedor"]
            codigo_cliente = datos["codigo_cliente"]
            moneda = datos["moneda"]
            bodega_por_codigo = self._mapear_tiendas_a_bodega(detalles) if codigo_bodega else {}

            # Construir líneas del archivo
            lines = []

            # Agregar encabezado si se requiere
            if incluir_encabezado:
                lines.append(self.MBA_HEADER)

            # Contador secuencial de registros
            numero_secuencial = 1

            # Generar una línea por cada combinación producto-tienda
            for detalle in detalles:
                # Producto excluido: Total editado manualmente a 0 en el Detalle del Pedido
                if self._excluido_por_total_manual_cero(detalle):
                    continue

                codigo_producto = (detalle.get("codigo_interno") or "").strip()  # Col 21 Código Producto
                precio_unitario = self._resolver_precio_unitario(detalle)

                tiendas = self._filtrar_tiendas_por_bodega(detalle.get("tiendas", []), codigo_bodega, bodega_por_codigo)
                for tienda in tiendas:
                    cantidad = tienda.get("cantidad", 0)

                    # Omitir solo si la cantidad es negativa (0 y decimales como 0.5 se exportan)
                    if cantidad < 0:
                        continue

                    # Construir las 35 columnas (TXTN SUBIR PEDIDOS CON PRECIO)
                    columnas = [
                        self._format_number(numero_secuencial, 0),  # 1. Numero (col A - secuencial)
                        self._format_number(config.numero_pedido_temporal, 0),  # 2. Número Pedido (col B - agrupa líneas)
                        codigo_cliente,  # 3. Código Cliente (col C - CLI1795)
                        config.codigo_subcliente,  # 4. Código SubCliente
                        fecha_pedido,  # 5. Fecha Pedido
                        fecha_entrega,  # 6. Fecha Entrega
                        moneda,  # 7. Moneda (col G - divisa local US)
                        bodega,  # 8. Bodega
                        vendedor,  # 9. Vendedor
                        pedido_manual,  # 10. Pedido Manual (numero_pedido interno)
                        "",  # 11. Contrato
                        orden_compra_cliente,  # 12. Orden Compra Cliente (DocNum de la OC enviada a SAP)
                        "",  # 13. Cotización Original
                        "",  # 14. Medio Captura
                        "",  # 15. Transporte
                        "",  # 16. Nombre Solicitante
                        "",  # 17. Memo
                        self._format_boolean(config.registro_editable),  # 18. Registro Editable
                        self._format_boolean(config.confirmado),  # 19. Confirmado
                        _SUCURSAL_FIJA,  # 20. Sucursal
                        codigo_producto,  # 21. Código Producto
                        self._format_number(cantidad, 4),  # 22. Cantidad Pedido (acepta decimales)
                        "FALSE",  # 23. BackOrder (siempre FALSE)
                        self._format_number(precio_unitario, 3),  # 24. Precio Final (del sistema)
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
                        self._format_number(numero_secuencial, 0),  # 35. Numero (col AI - secuencial)
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
        incluir_encabezado: bool = True,
        codigo_bodega: Optional[str] = None,
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
            codigo_bodega: Ver exportar_pedido_formato_mba -- limita la exportación y el
                DocNum a la ODC de esa bodega cuando el pedido tiene más de una.

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

            fecha_confirmacion = repo.get_fecha_confirmacion_estado(pedido_id, ESTADO_REDISTRIBUCION)
            oc_repo = OrdenCompraRepository(conn)
            doc_num = (
                oc_repo.get_doc_num_by_pedido_id_y_bodega(pedido_id, codigo_bodega)
                if codigo_bodega else oc_repo.get_doc_num_by_pedido_id(pedido_id)
            )
            datos = self._extraer_datos_exportacion(cabecera, config, fecha_confirmacion, doc_num)
            fecha_pedido = datos["fecha_pedido"]
            fecha_entrega = datos["fecha_entrega"]
            pedido_manual = datos["pedido_manual"]
            orden_compra_cliente = datos["orden_compra_cliente"]
            bodega = datos["bodega"]
            vendedor = datos["vendedor"]
            codigo_cliente = datos["codigo_cliente"]
            moneda = datos["moneda"]
            bodega_por_codigo = self._mapear_tiendas_a_bodega(detalles) if codigo_bodega else {}

            lines = []

            if incluir_encabezado:
                lines.append(self.MBA_HEADER)
            
            numero_secuencial = 1

            for detalle in detalles:
                # Producto excluido: Total editado manualmente a 0 en el Detalle del Pedido
                if self._excluido_por_total_manual_cero(detalle):
                    continue

                codigo_producto = (detalle.get("codigo_interno") or "").strip()
                precio_unitario = self._resolver_precio_unitario(detalle)

                tiendas = self._filtrar_tiendas_por_bodega(detalle.get("tiendas", []), codigo_bodega, bodega_por_codigo)
                # Producto sin tiendas en esta bodega: no pertenece a esta ODC, se omite
                # por completo (distinto de cantidad_total == 0 con tiendas sí asignadas,
                # que sí se exporta, ver comentario más abajo).
                if codigo_bodega and not tiendas:
                    continue

                # Consolidar cantidad total de las tiendas (de esta bodega, si aplica)
                cantidad_total = sum(t.get("cantidad", 0) for t in tiendas)

                if cantidad_total < 0:
                    continue
                
                columnas = [
                    self._format_number(numero_secuencial, 0),
                    self._format_number(config.numero_pedido_temporal, 0),
                    codigo_cliente,
                    config.codigo_subcliente,
                    fecha_pedido,
                    fecha_entrega,
                    moneda,
                    bodega,
                    vendedor,
                    pedido_manual,  # Pedido Manual (numero_pedido interno)
                    "",  # Contrato
                    orden_compra_cliente,  # DocNum de la OC enviada a SAP
                    "",  # Cotización Original
                    "",  # Medio Captura
                    "",  # Transporte
                    "",  # Nombre Solicitante
                    "",  # Memo
                    self._format_boolean(config.registro_editable),
                    self._format_boolean(config.confirmado),
                    _SUCURSAL_FIJA,
                    codigo_producto,
                    self._format_number(cantidad_total, 4),  # Cantidad total (acepta decimales)
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
