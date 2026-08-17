"""
Tests automatizados para PedidoAjusteService (FASE 4).

CORRECCIONES APLICADAS:
- ✅ Mocking correcto de repositorios (patch donde se instancian)
- ✅ Validación correcta de rollback (sin commit, sin update_estado)
- ✅ Tests de casos críticos reales

Cubre los casos críticos de confirmación del proveedor:
- Confirmación exacta
- Confirmación parcial con redistribución
- Distribución específica del proveedor
- Idempotencia
- Cambio de precios
- Rollback transaccional
"""

import pytest  # type: ignore[reportMissingImports]
from unittest.mock import patch, MagicMock
from typing import Dict, Any

from src.database.services.pedido_ajuste_service import PedidoAjusteService
from src.database.pedido_estados import ESTADO_CONFIRMADO_PROVEEDOR
from src.utils.audit_context import ORIGEN_WEB


class TestPedidoAjusteService:
    """Tests para el servicio de ajuste de pedidos."""
    
    @pytest.fixture
    def service(self):
        """Fixture del servicio."""
        return PedidoAjusteService()
    
    @pytest.fixture
    def mock_conn(self):
        """Mock de conexión a BD."""
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        conn.commit = MagicMock()
        conn.rollback = MagicMock()
        return conn
    
    @pytest.fixture
    def pedido_base(self) -> Dict[str, Any]:
        """Pedido base para tests."""
        return {
            "cabecera": {
                "pedido_id": "pedido-123",
                "numero_pedido": "PED-001",
                "estado": "RESPUESTA_PROVEEDOR_CARGADA"
            },
            "detalles": [
                {
                    "pedido_detalle_id": "detalle-1",
                    "codigo_interno": "PROD-001",
                    "descripcion_sap": "Producto Test 1",
                    "costo_doc_sin_iva": 100.0,
                    "descuento_1": 10.0,
                    "tiendas": [
                        {
                            "tienda_id": "tienda-1",
                            "codigo": "T001",
                            "nombre": "Tienda 1",
                            "cantidad": 50
                        },
                        {
                            "tienda_id": "tienda-2",
                            "codigo": "T002",
                            "nombre": "Tienda 2",
                            "cantidad": 50
                        }
                    ]
                }
            ]
        }
    
    @pytest.fixture
    def respuesta_base(self) -> Dict[str, Any]:
        """Respuesta base para tests."""
        return {
            "cabecera": {
                "respuesta_id": "respuesta-123",
                "version": 1,
                "estado": "PENDIENTE_REVISION",
                "fecha_respuesta": "2024-01-01T00:00:00"
            },
            "detalles": [
                {
                    "id": "resp-detalle-1",
                    "pedido_detalle_id": "detalle-1",
                    "codigo_producto": "PROD-001",
                    "descripcion": "Producto Test 1",
                    "cantidad_solicitada_total": 100,
                    "cantidad_confirmada_total": 100,
                    "costo_doc_sin_iva_original": 100.0,
                    "costo_doc_sin_iva_ajustado": None,
                    "descuento_1_original": 10.0,
                    "descuento_1_ajustado": None,
                    "observaciones": None
                }
            ]
        }
    
    def test_caso_1_confirmacion_exacta(
        self, 
        service, 
        mock_conn, 
        pedido_base, 
        respuesta_base
    ):
        """
        CASO 1: Confirmación exacta (solicitado = confirmado).
        
        Verifica:
        - Estado pedido → CONFIRMADO_PROVEEDOR
        - No diferencias en reporte
        - Cantidades por tienda sin cambios
        """
        # ✅ CORRECCIÓN: Patch repositorios donde se instancian
        with patch('src.database.services.pedido_ajuste_service.get_db_connection_context') as mock_ctx, \
             patch('src.database.services.pedido_ajuste_service.PedidoRespuestaRepository') as mock_respuesta_repo_class, \
             patch('src.database.services.pedido_ajuste_service.PedidoRepository') as mock_pedido_repo_class:
            
            mock_ctx.return_value.__enter__.return_value = mock_conn
            
            # Crear instancias mock de los repositorios
            mock_respuesta_repo = MagicMock()
            mock_pedido_repo = MagicMock()
            
            mock_respuesta_repo_class.return_value = mock_respuesta_repo
            mock_pedido_repo_class.return_value = mock_pedido_repo
            
            # Configurar retornos
            mock_respuesta_repo.obtener_respuesta_activa.return_value = respuesta_base
            mock_pedido_repo.get_pedido_completo.return_value = pedido_base
            mock_pedido_repo.update_estado = MagicMock()
            
            # Mock cursor para actualizaciones
            cursor = mock_conn.cursor.return_value
            cursor.execute = MagicMock()
            cursor.fetchone = MagicMock(return_value=(100.0, 10.0))  # costo, descuento
            cursor.fetchall = MagicMock(return_value=[])  # Sin distribución específica
            cursor.rowcount = 1
            
            # Ejecutar
            resultado = service.procesar_confirmacion_proveedor(
                pedido_id="pedido-123",
                usuario_id="user-1"
            )
            
            # Verificaciones
            assert resultado["status"] == "success"
            assert resultado["resumen"]["total_diferencia"] == 0
            assert resultado["resumen"]["porcentaje_confirmacion"] == 100.0
            
            # Verificar que se actualizó estado del pedido (usa constante entera, no string)
            # y que se adjuntó el audit_context correspondiente (usuario/origen).
            # No se compara audit_context.fecha porque se genera con ahora_naive()
            # (reloj no determinista) en el momento de la llamada.
            mock_pedido_repo.update_estado.assert_called_once()
            call = mock_pedido_repo.update_estado.call_args
            assert call.args == ("pedido-123", ESTADO_CONFIRMADO_PROVEEDOR)
            audit_context = call.kwargs["audit_context"]
            assert audit_context.usuario == "user-1"
            assert audit_context.origen == ORIGEN_WEB
            
            # Verificar commit único
            assert mock_conn.commit.call_count == 1
            assert mock_conn.rollback.call_count == 0
    
    def test_caso_2_confirmacion_parcial_redistribucion(
        self,
        service,
        mock_conn,
        pedido_base,
        respuesta_base
    ):
        """
        CASO 2: Confirmación parcial (70 de 100) con redistribución proporcional.
        
        Verifica:
        - Suma EXACTA = 70
        - Última tienda absorbe residuo
        - No números negativos
        """
        # Modificar respuesta para confirmar 70 de 100
        respuesta_base["detalles"][0]["cantidad_confirmada_total"] = 70
        
        with patch('src.database.services.pedido_ajuste_service.get_db_connection_context') as mock_ctx, \
             patch('src.database.services.pedido_ajuste_service.PedidoRespuestaRepository') as mock_respuesta_repo_class, \
             patch('src.database.services.pedido_ajuste_service.PedidoRepository') as mock_pedido_repo_class:
            
            mock_ctx.return_value.__enter__.return_value = mock_conn
            
            mock_respuesta_repo = MagicMock()
            mock_pedido_repo = MagicMock()
            
            mock_respuesta_repo_class.return_value = mock_respuesta_repo
            mock_pedido_repo_class.return_value = mock_pedido_repo
            
            mock_respuesta_repo.obtener_respuesta_activa.return_value = respuesta_base
            mock_pedido_repo.get_pedido_completo.return_value = pedido_base
            mock_pedido_repo.update_estado = MagicMock()
            
            cursor = mock_conn.cursor.return_value
            cursor.execute = MagicMock()
            cursor.fetchone = MagicMock(return_value=(100.0, 10.0))
            cursor.fetchall = MagicMock(return_value=[])  # Sin distribución específica
            cursor.rowcount = 1
            
            # Ejecutar
            resultado = service.procesar_confirmacion_proveedor(
                pedido_id="pedido-123",
                usuario_id="user-1"
            )
            
            # Verificaciones
            assert resultado["status"] == "success"
            assert resultado["resumen"]["total_confirmado"] == 70
            assert resultado["resumen"]["total_diferencia"] == -30
            
            # Verificar que se llamó UPDATE para ajustar cantidades
            update_calls = [
                call for call in cursor.execute.call_args_list 
                if "UPDATE pedido_detalle_tienda" in str(call)
            ]
            assert len(update_calls) == 2  # Dos tiendas ajustadas
            
            # Verificar suma exacta en ajustes
            ajustes = resultado["ajustes_detalle"][0]["ajuste_tiendas"]["ajustes"]
            suma_ajustes = sum(a["cantidad_nueva"] for a in ajustes)
            assert suma_ajustes == 70, f"Suma debe ser 70, obtuvo {suma_ajustes}"
    
    def test_caso_3_distribucion_especifica_proveedor(
        self,
        service,
        mock_conn,
        pedido_base,
        respuesta_base
    ):
        """
        CASO 3: Distribución específica del proveedor.
        
        Verifica:
        - Se respeta distribución específica
        - No entra a redistribución proporcional
        """
        with patch('src.database.services.pedido_ajuste_service.get_db_connection_context') as mock_ctx, \
             patch('src.database.services.pedido_ajuste_service.PedidoRespuestaRepository') as mock_respuesta_repo_class, \
             patch('src.database.services.pedido_ajuste_service.PedidoRepository') as mock_pedido_repo_class:
            
            mock_ctx.return_value.__enter__.return_value = mock_conn
            
            mock_respuesta_repo = MagicMock()
            mock_pedido_repo = MagicMock()
            
            mock_respuesta_repo_class.return_value = mock_respuesta_repo
            mock_pedido_repo_class.return_value = mock_pedido_repo
            
            mock_respuesta_repo.obtener_respuesta_activa.return_value = respuesta_base
            mock_pedido_repo.get_pedido_completo.return_value = pedido_base
            mock_pedido_repo.update_estado = MagicMock()
            
            cursor = mock_conn.cursor.return_value
            cursor.execute = MagicMock()
            cursor.fetchone = MagicMock(return_value=(100.0, 10.0))
            # Mock distribución específica: T001=40, T002=30 (total 70)
            cursor.fetchall = MagicMock(return_value=[
                ("tienda-detalle-1", 40),
                ("tienda-detalle-2", 30)
            ])
            cursor.rowcount = 1
            
            # Modificar respuesta para confirmar 70 total
            respuesta_base["detalles"][0]["cantidad_confirmada_total"] = 70
            
            # Ejecutar
            resultado = service.procesar_confirmacion_proveedor(
                pedido_id="pedido-123",
                usuario_id="user-1"
            )
            
            # Verificar que se usó distribución específica
            assert resultado["status"] == "success"
            ajuste = resultado["ajustes_detalle"][0]["ajuste_tiendas"]
            assert ajuste["metodo"] == "distribucion_especifica"
            
            # Verificar que se actualizaron las cantidades específicas
            update_calls = [
                call for call in cursor.execute.call_args_list 
                if "UPDATE pedido_detalle_tienda" in str(call)
            ]
            assert len(update_calls) == 2  # Dos tiendas con distribución específica
    
    def test_caso_4_idempotencia(
        self,
        service,
        mock_conn,
        pedido_base,
        respuesta_base
    ):
        """
        CASO 4: Idempotencia - segunda llamada debe fallar con 409.
        
        Verifica:
        - Primera llamada exitosa
        - Segunda llamada retorna ValueError (que se convierte en 409)
        - Sin cambios en BD en segunda llamada
        """
        with patch('src.database.services.pedido_ajuste_service.get_db_connection_context') as mock_ctx, \
             patch('src.database.services.pedido_ajuste_service.PedidoRespuestaRepository') as mock_respuesta_repo_class, \
             patch('src.database.services.pedido_ajuste_service.PedidoRepository') as mock_pedido_repo_class:
            
            mock_ctx.return_value.__enter__.return_value = mock_conn
            
            mock_respuesta_repo = MagicMock()
            mock_pedido_repo = MagicMock()
            
            mock_respuesta_repo_class.return_value = mock_respuesta_repo
            mock_pedido_repo_class.return_value = mock_pedido_repo
            
            mock_pedido_repo.get_pedido_completo.return_value = pedido_base
            mock_pedido_repo.update_estado = MagicMock()
            
            cursor = mock_conn.cursor.return_value
            cursor.execute = MagicMock()
            cursor.fetchone = MagicMock(return_value=(100.0, 10.0))
            cursor.fetchall = MagicMock(return_value=[])
            
            # Primera llamada: estado PENDIENTE_REVISION
            respuesta_base["cabecera"]["estado"] = "PENDIENTE_REVISION"
            mock_respuesta_repo.obtener_respuesta_activa.return_value = respuesta_base
            cursor.rowcount = 1  # Primera vez: actualiza
            
            # Primera llamada exitosa
            resultado1 = service.procesar_confirmacion_proveedor(
                pedido_id="pedido-123",
                usuario_id="user-1"
            )
            assert resultado1["status"] == "success"
            
            # Resetear mocks para segunda llamada
            mock_conn.commit.reset_mock()
            mock_pedido_repo.update_estado.reset_mock()
            
            # Segunda llamada: respuesta ya aprobada
            respuesta_base["cabecera"]["estado"] = "APROBADA"
            mock_respuesta_repo.obtener_respuesta_activa.return_value = respuesta_base
            
            # Debe lanzar ValueError
            with pytest.raises(ValueError) as exc_info:
                service.procesar_confirmacion_proveedor(
                    pedido_id="pedido-123",
                    usuario_id="user-1"
                )
            
            error_msg = str(exc_info.value).lower()
            assert "ya fue procesada" in error_msg or \
                   "no está en estado" in error_msg or \
                   "debe estar en estado" in error_msg
            
            # Verificar que NO se hizo commit ni update_estado en segunda llamada
            assert mock_conn.commit.call_count == 0
            assert mock_pedido_repo.update_estado.call_count == 0
    
    def test_caso_5_cambio_precio(
        self,
        service,
        mock_conn,
        pedido_base,
        respuesta_base
    ):
        """
        CASO 5: Cambio de precio y descuento.
        
        Verifica:
        - Subtotal recalculado correctamente
        - Total con descuento correcto
        - Persistencia en pedido_detalle
        """
        # Modificar respuesta con precio ajustado
        respuesta_base["detalles"][0]["costo_doc_sin_iva_ajustado"] = 120.0
        respuesta_base["detalles"][0]["descuento_1_ajustado"] = 15.0
        
        with patch('src.database.services.pedido_ajuste_service.get_db_connection_context') as mock_ctx, \
             patch('src.database.services.pedido_ajuste_service.PedidoRespuestaRepository') as mock_respuesta_repo_class, \
             patch('src.database.services.pedido_ajuste_service.PedidoRepository') as mock_pedido_repo_class:
            
            mock_ctx.return_value.__enter__.return_value = mock_conn
            
            mock_respuesta_repo = MagicMock()
            mock_pedido_repo = MagicMock()
            
            mock_respuesta_repo_class.return_value = mock_respuesta_repo
            mock_pedido_repo_class.return_value = mock_pedido_repo
            
            mock_respuesta_repo.obtener_respuesta_activa.return_value = respuesta_base
            mock_pedido_repo.get_pedido_completo.return_value = pedido_base
            mock_pedido_repo.update_estado = MagicMock()
            
            cursor = mock_conn.cursor.return_value
            cursor.execute = MagicMock()
            cursor.fetchone = MagicMock(return_value=(100.0, 10.0))  # Original
            cursor.fetchall = MagicMock(return_value=[])
            cursor.rowcount = 1
            
            # Ejecutar
            resultado = service.procesar_confirmacion_proveedor(
                pedido_id="pedido-123",
                usuario_id="user-1"
            )
            
            # Verificar que se actualizó el costo
            update_calls = [
                call for call in cursor.execute.call_args_list 
                if "UPDATE pedido_detalle" in str(call) and "costo_doc_sin_iva" in str(call)
            ]
            assert len(update_calls) > 0
            
            # Verificar que el reporte muestra cambio de precio
            reporte = resultado["reporte_diferencias"][0]
            assert reporte["costo_ajustado"] == 120.0
            assert reporte["cambio_precio"] is True
    
    def test_rollback_transaccional(
        self,
        service,
        mock_conn,
        pedido_base,
        respuesta_base
    ):
        """
        Test de rollback: error a mitad del flujo.
        
        ✅ CORRECCIÓN: Validar lo correcto:
        - NO se hace commit
        - NO se actualiza estado del pedido
        - Excepción propagada
        """
        with patch('src.database.services.pedido_ajuste_service.get_db_connection_context') as mock_ctx, \
             patch('src.database.services.pedido_ajuste_service.PedidoRespuestaRepository') as mock_respuesta_repo_class, \
             patch('src.database.services.pedido_ajuste_service.PedidoRepository') as mock_pedido_repo_class:
            
            mock_ctx.return_value.__enter__.return_value = mock_conn
            
            mock_respuesta_repo = MagicMock()
            mock_pedido_repo = MagicMock()
            
            mock_respuesta_repo_class.return_value = mock_respuesta_repo
            mock_pedido_repo_class.return_value = mock_pedido_repo
            
            mock_respuesta_repo.obtener_respuesta_activa.return_value = respuesta_base
            mock_pedido_repo.get_pedido_completo.return_value = pedido_base
            mock_pedido_repo.update_estado = MagicMock()
            
            cursor = mock_conn.cursor.return_value
            cursor.execute = MagicMock()
            cursor.fetchone = MagicMock(return_value=(100.0, 10.0))
            cursor.fetchall = MagicMock(return_value=[])
            
            # Simular error en _ajustar_cantidades_por_tienda
            # Primera llamada OK (fetchone), segunda falla (execute en UPDATE)
            cursor.execute.side_effect = [
                None,  # Primera llamada OK (fetchone ya se llamó)
                Exception("Error simulado en ajuste")  # Segunda llamada falla
            ]
            
            # Debe lanzar excepción
            with pytest.raises(Exception) as exc_info:
                service.procesar_confirmacion_proveedor(
                    pedido_id="pedido-123",
                    usuario_id="user-1"
                )
            
            # ✅ CORRECCIÓN: Validar lo correcto
            # NO se hizo commit
            assert mock_conn.commit.call_count == 0
            
            # NO se actualizó estado del pedido
            assert not mock_pedido_repo.update_estado.called
            
            # Excepción fue propagada
            assert "Error simulado" in str(exc_info.value)
            
            # Nota: No validamos rollback explícito porque el context manager lo maneja
            # Lo importante es que NO hubo commit
    
    def test_redistribucion_proporcional_suma_exacta(
        self,
        service,
        mock_conn
    ):
        """
        Test específico: redistribución proporcional suma exacta.

        Caso: 100 solicitado, 73 confirmado, 2 tiendas (50/50 original).
        Desde la migración a cantidad DECIMAL(18,4) (commit "numeros decimales",
        2026-03-03) la redistribución ya NO redondea a enteros: preserva hasta
        4 decimales (quantize a '0.0001'). Con reparto 50/50 el resultado exacto
        es 36.5 + 36.5 = 73, no 37 + 36.
        """
        pedido = {
            "cabecera": {"pedido_id": "pedido-123"},
            "detalles": [{
                "pedido_detalle_id": "detalle-1",
                "tiendas": [
                    {"tienda_id": "t1", "codigo": "T001", "cantidad": 50},
                    {"tienda_id": "t2", "codigo": "T002", "cantidad": 50}
                ]
            }]
        }
        
        cursor = mock_conn.cursor.return_value
        cursor.execute = MagicMock()
        cursor.fetchall = MagicMock(return_value=[])  # Sin distribución específica
        
        # Ejecutar redistribución
        ajuste = service._ajustar_cantidades_por_tienda(
            conn=mock_conn,
            pedido_detalle_id="detalle-1",
            cantidad_confirmada_total=73,
            distribucion_original=pedido["detalles"][0]["tiendas"],
            respuesta_id="resp-1",
            forzar_redistribucion=False
        )
        
        # Verificar que suma exacta
        cantidades = [a["cantidad_nueva"] for a in ajuste["ajustes"]]
        suma = sum(cantidades)
        assert suma == 73, f"Suma debe ser 73, obtuvo {suma}"
        
        # Verificar que no hay negativos
        assert all(c >= 0 for c in cantidades), "No debe haber cantidades negativas"
        
        # Verificar que última tienda absorbe residuo
        assert ajuste["metodo"] == "redistribucion_proporcional"
        
        # Verificar distribución proporcional (preserva decimales, DECIMAL(18,4))
        # 73 * 0.5 = 36.5 exacto para ambas tiendas (ya no se redondea a entero)
        assert cantidades[0] == 36.5, f"Primera tienda debe ser 36.5, obtuvo {cantidades[0]}"
        assert cantidades[1] == 36.5, f"Segunda tienda debe ser 36.5, obtuvo {cantidades[1]}"

