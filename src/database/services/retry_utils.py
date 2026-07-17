"""
Utilidades de reintento técnico para integraciones externas.

Este módulo centraliza la mecánica de retry (backoff + jitter) para evitar
duplicidad entre flujos de ODC e ITR.
"""

from __future__ import annotations

import random
import time
from typing import Any, Callable, Dict, FrozenSet, Optional


# Códigos numéricos DI / SAP Business One (Service Layer suele devolverlos en error.code).
# Fuentes: SDK GetLastError, notas SAP/KBA sobre bloqueos e “internal error”, y práctica común
# de reintento ante -2038 / -5002.
SAP_B1_ERROR_CODES_FORCE_RETRY: FrozenSet[int] = frozenset(
    {
        # Bloqueos / contención (suelen resolverse esperando)
        -2038,
        -5002,
        # Conectividad / capa de datos / timeouts (GetLastError / operación)
        -103,
        -104,
        -111,
        -8004,
        -8005,
        -8021,
        # Capacidad de licencias / sesiones (a veces se libera solo)
        -118,
        -8009,
    }
)

SAP_B1_ERROR_CODES_FORCE_NO_RETRY: FrozenSet[int] = frozenset(
    {
        # Sesión / credenciales / entorno: no tiene sentido backoff ciego
        -106,
        -107,
        -108,
        -8023,
        -8010,
        -8012,
        -8013,
        # Validación de datos / permisos de negocio
        -1001,
        -1002,
        -1106,
        -1107,
        -2052,
        -2053,
        -2055,
        -3000,
        -3001,
        # Periodo contable cerrado / bloqueado para nuevos datos (requiere apertura en B1)
        -4013,
    }
)


def _parse_sap_b1_error_code(raw: Any) -> Optional[int]:
    """Normaliza error.code del Service Layer a int, o None si no es un código B1 numérico."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(s, 10)
    except ValueError:
        return None


def _sap_b1_error_code_retry_policy(code: Optional[int]) -> Optional[bool]:
    """
    None: no aplicar política por código (seguir heurística HTTP/mensaje).
    True/False: forzar reintento o no, incluso ante 4xx con cuerpo OData de SAP.
    """
    if code is None:
        return None
    if code in SAP_B1_ERROR_CODES_FORCE_NO_RETRY:
        return False
    if code in SAP_B1_ERROR_CODES_FORCE_RETRY:
        return True
    return None


def _es_error_transporte(err: str, err_l: str) -> bool:
    """True si el mensaje de error apunta a un problema de red/TLS/timeout (sin status HTTP)."""
    if err.startswith("Error de conexión:"):
        return True
    if "no se pudo establecer conexión" in err_l:
        return True
    if "timeout" in err_l:
        return True
    if "timed out" in err_l:
        return True
    if "connection" in err_l:
        return True
    if "ssl" in err_l:
        return True
    if "tls" in err_l:
        return True
    # Errores inesperados sin status (p.ej. bugs / parseo): evitar reintentos ciegos
    return False


def _http_status_should_retry(status_code: Any) -> bool:
    """Política de reintento basada en el código HTTP de respuesta de SAP Service Layer."""
    if status_code in (408, 425, 429) or 500 <= int(status_code) <= 599:
        return True
    # 401/403: requieren acción (credenciales/permisos), no backoff ciego
    if status_code in (401, 403):
        return False
    # 404: problema de endpoint/versionado; esperar no lo resuelve
    if status_code == 404:
        return False
    # Resto de 4xx: asumir validación/datos
    return False


def sap_service_layer_result_should_retry(response: Any) -> bool:
    """
    Heurística conservadora para decidir si un fallo de SAP Service Layer
    parece **transitorio** (red/SL caído/overload) vs **permanente** (validación).

    Nota: el cliente devuelve dicts con shape similar a:
      {"success": False, "error": "...", "error_code": str|int|None, "status_code": int|None, ...}
    o None cuando la integración está deshabilitada / no hay respuesta usable.

    Prioridad: mensaje "SAP desactivado" > ``error_code`` B1 mapeado >
    heurística HTTP / mensajes de conexión.
    """
    if response is None:
        # None suele significar "SAP deshabilitado" o fallo previo sin payload;
        # en ambos casos, reintentar no ayuda.
        return False

    if not isinstance(response, dict):
        return True

    if response.get("success") is True:
        return False

    err = str(response.get("error") or "")
    err_l = err.lower()

    # Casos explícitos "no reintentar" (configuración / feature off)
    if "desactivad" in err_l:
        return False
    if "deshabilitad" in err_l:
        return False

    b1_code = _parse_sap_b1_error_code(response.get("error_code"))
    code_policy = _sap_b1_error_code_retry_policy(b1_code)
    if code_policy is False:
        return False
    if code_policy is True:
        return True

    status_code = response.get("status_code")
    if status_code is None:
        return _es_error_transporte(err, err_l)

    return _http_status_should_retry(status_code)


def mensaje_sugiere_reintento_transitorio(mensaje: Optional[str]) -> bool:
    """
    True si el texto describe un fallo típicamente transitorio hacia SAP SL (red, SL caído).

    Clasificador basado en mensaje ya aplanado a texto (a diferencia de
    sap_service_layer_result_should_retry, que opera sobre la respuesta estructurada
    en el momento del envío). Se usa post-hoc, cuando solo queda el mensaje de error
    persistido (ej. decidir si mostrar el botón de reintento manual, o si la
    reconciliación automática debe escalar de inmediato en vez de esperar).
    """
    if not mensaje:
        return False
    m = mensaje.lower()
    needles = (
        "conexión",
        "conexion",
        "connection",
        "timeout",
        "remote",
        "disconnected",
        "sin respuesta",
        "no se pudo establecer conexión",
        "no se pudo establecer conexion",
        # Regla operativa: permitir reenvío manual en errores de presupuesto de RL.
        "presupuesto excedido rl",
        "código sap: -1116",
        "codigo sap: -1116",
    )
    return any(n in m for n in needles)


def retry_operation(
    *,
    execute: Callable[[], Any],
    is_success: Callable[[Any], bool],
    extract_error: Callable[[Any], str],
    max_attempts: int,
    should_retry: Optional[Callable[[Any], bool]] = None,
    base_delay_seconds: float,
    max_jitter_seconds: float,
    logger: Any,
    operation_label: str,
    success_message: Optional[str] = None,
    retry_message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ejecuta una operación con retry exponencial y jitter.

    Returns:
        {
            "success": bool,
            "response": Any,
            "attempts": int,
            "error": str | None
        }
    """
    should_retry_fn = should_retry or (lambda _response: True)

    last_response: Any = None
    last_error = "Error desconocido"

    for attempt in range(1, max_attempts + 1):
        last_response = execute()
        if is_success(last_response):
            if attempt > 1:
                logger.info(
                    success_message
                    or f"✅ Reenvío exitoso de {operation_label} en intento {attempt}/{max_attempts}"
                )
            return {
                "success": True,
                "response": last_response,
                "attempts": attempt,
                "error": None,
            }

        last_error = extract_error(last_response)
        if attempt < max_attempts and not should_retry_fn(last_response):
            logger.warning(
                f"⚠️ {operation_label} fallida en intento {attempt}/{max_attempts}: "
                f"{last_error}. Error no reintentable; se detiene."
            )
            return {
                "success": False,
                "response": last_response,
                "attempts": attempt,
                "error": last_error,
            }

        if attempt < max_attempts:
            wait_seconds = (
                base_delay_seconds * (2 ** (attempt - 1))
                + random.uniform(0, max_jitter_seconds)
            )
            logger.warning(
                retry_message
                or (
                    f"⚠️ {operation_label} fallida en intento {attempt}/{max_attempts}: "
                    f"{last_error}. Reintentando en {wait_seconds:.1f}s..."
                )
            )
            time.sleep(wait_seconds)

    return {
        "success": False,
        "response": last_response,
        "attempts": max_attempts,
        "error": last_error,
    }
