"""Tests de contrato para endpoints de redistribución."""

from typing import List, Optional, Set

from fastapi import FastAPI
from fastapi.routing import APIRoute

from src.endpoints.pedidos.pedidos_redistribucion import register_redistribucion_endpoints
from src.models import (
    DistribucionPedidoResponse,
    ConfirmarRedistribucionResponse,
    ReporteDiferenciasResponse,
    GuardarBorradorResponse,
    BorradorResponse,
    ConfirmarRedistribucionResponseFrontend,
)
from src.security.jwt_auth import verify_jwt_token


def _build_app() -> FastAPI:
    app = FastAPI()
    register_redistribucion_endpoints(app)
    return app


def _get_routes(app: FastAPI) -> List[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute)]


def _find_route(routes: List[APIRoute], path: str, method: str) -> Optional[APIRoute]:
    for route in routes:
        if route.path == path and method in route.methods:
            return route
    return None


def _body_param_names(route: APIRoute) -> Set[str]:
    return {p.name for p in route.dependant.body_params}


def _path_param_names(route: APIRoute) -> Set[str]:
    return {p.name for p in route.dependant.path_params}


def _query_param_names(route: APIRoute) -> Set[str]:
    return {p.name for p in route.dependant.query_params}


def _has_jwt_dependency(route: APIRoute) -> bool:
    return any(dep.call == verify_jwt_token for dep in route.dependant.dependencies)


def test_redistribucion_endpoints_registrados():
    app = _build_app()
    routes = _get_routes(app)

    expected_paths = {
        "/api/pedidos/{pedido_id}/distribucion",
        "/api/pedidos/{pedido_id}/redistribuir",
        "/api/pedidos/{pedido_id}/confirmar-redistribucion",
        "/api/pedidos/{pedido_id}/reporte-diferencias",
        "/api/pedidos/{pedido_id}/reporte-diferencias/excel",
        "/api/pedidos/{numero_pedido}/redistribucion/borrador",
        "/api/pedidos/{numero_pedido}/redistribucion/inicial",
        "/api/pedidos/{numero_pedido}/redistribucion/confirmar",
        "/api/pedidos/{numero_pedido}/redistribucion/ajustar-bodegas",
        "/api/pedidos/{pedido_id}/distribucion/descargar-excel",
        "/api/pedidos/{numero_pedido}/proceso-completo-sap",
        "/api/pedidos/tiendas/buscar",
    }

    assert expected_paths.issubset({r.path for r in routes})


def test_redistribucion_endpoints_contrato():
    app = _build_app()
    routes = _get_routes(app)

    expected_contract = {
        ("/api/pedidos/{pedido_id}/distribucion", "GET"): {
            "method": "GET",
            "response_model": DistribucionPedidoResponse,
            "path_params": {"pedido_id"},
            "query_params": {"version"},
            "body_params": set(),
        },
        ("/api/pedidos/{pedido_id}/redistribuir", "POST"): {
            "method": "POST",
            "response_model": None,
            "path_params": {"pedido_id"},
            "query_params": set(),
            "body_params": {"request_body"},
        },
        ("/api/pedidos/{pedido_id}/confirmar-redistribucion", "POST"): {
            "method": "POST",
            "response_model": ConfirmarRedistribucionResponse,
            "path_params": {"pedido_id"},
            "query_params": set(),
            "body_params": {"request_body"},
        },
        ("/api/pedidos/{pedido_id}/reporte-diferencias", "GET"): {
            "method": "GET",
            "response_model": ReporteDiferenciasResponse,
            "path_params": {"pedido_id"},
            "query_params": {"version"},
            "body_params": set(),
        },
        ("/api/pedidos/{pedido_id}/reporte-diferencias/excel", "GET"): {
            "method": "GET",
            "response_model": None,
            "path_params": {"pedido_id"},
            "query_params": {"version"},
            "body_params": set(),
        },
        ("/api/pedidos/{numero_pedido}/redistribucion/borrador", "POST"): {
            "method": "POST",
            "response_model": GuardarBorradorResponse,
            "path_params": {"numero_pedido"},
            "query_params": set(),
            "body_params": {"request_body"},
        },
        ("/api/pedidos/{numero_pedido}/redistribucion/borrador", "GET"): {
            "method": "GET",
            "response_model": BorradorResponse,
            "path_params": {"numero_pedido"},
            "query_params": set(),
            "body_params": set(),
        },
        ("/api/pedidos/{numero_pedido}/redistribucion/inicial", "GET"): {
            "method": "GET",
            "response_model": BorradorResponse,
            "path_params": {"numero_pedido"},
            "query_params": {"solo_lectura"},
            "body_params": set(),
        },
        ("/api/pedidos/{numero_pedido}/redistribucion/confirmar", "POST"): {
            "method": "POST",
            "response_model": ConfirmarRedistribucionResponseFrontend,
            "path_params": {"numero_pedido"},
            "query_params": set(),
            "body_params": {"request_body"},
        },
        ("/api/pedidos/{numero_pedido}/redistribucion/ajustar-bodegas", "POST"): {
            "method": "POST",
            "response_model": BorradorResponse,
            "path_params": {"numero_pedido"},
            "query_params": set(),
            "body_params": {"request_body"},
        },
        ("/api/pedidos/{pedido_id}/distribucion/descargar-excel", "GET"): {
            "method": "GET",
            "response_model": None,
            "path_params": {"pedido_id"},
            "query_params": {"version"},
            "body_params": set(),
        },
        ("/api/pedidos/{numero_pedido}/proceso-completo-sap", "POST"): {
            "method": "POST",
            "response_model": None,
            "path_params": {"numero_pedido"},
            "query_params": set(),
            "body_params": {"request_body"},
        },
    }

    for (path, method), expected in expected_contract.items():
        route = _find_route(routes, path, method)
        assert route is not None, f"No se encontró el endpoint {path} ({method})"
        assert expected["method"] in route.methods
        assert expected["response_model"] == route.response_model
        assert "Pedidos - Redistribución" in (route.tags or [])
        assert _path_param_names(route) == expected["path_params"]
        assert expected["query_params"].issubset(_query_param_names(route))
        assert _body_param_names(route) == expected["body_params"]
        assert _has_jwt_dependency(route)
