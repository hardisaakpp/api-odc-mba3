"""Envio SMTP con perfil autenticado primario y relay secundario."""

import logging
import smtplib
import socket
import ssl
import time
from email.message import Message
from email.utils import formataddr
from typing import Iterable, Optional

from src.config import (
    EMAIL_FROM,
    EMAIL_FROM_NAME,
    EMAIL_SMTP_AUTH_PORT,
    EMAIL_SMTP_AUTH_SERVER,
    EMAIL_SMTP_PASSWORD,
    EMAIL_SMTP_RELAY_PORT,
    EMAIL_SMTP_RELAY_SERVER,
    EMAIL_SMTP_TIMEOUT,
    EMAIL_SMTP_USER,
)

logger = logging.getLogger(__name__)

# Errores de conexión/TLS transitorios (ej. un hipo de red justo tras reiniciar el
# contenedor) que vale la pena reintentar antes de descartar el perfil. Errores de
# autenticación/destinatarios rechazados no están aquí: reintentarlos no cambia el
# resultado y solo retrasa el fallback al siguiente perfil.
_SMTP_RETRYABLE_EXCEPTIONS = (
    ssl.SSLError,
    socket.timeout,
    ConnectionError,
    smtplib.SMTPConnectError,
    smtplib.SMTPServerDisconnected,
)
_SMTP_MAX_INTENTOS_POR_PERFIL = 2
_SMTP_RETRY_DELAY_SECONDS = 2


def _replace_from_header(msg: Message, value: str) -> None:
    if "From" in msg:
        msg.replace_header("From", value)
    else:
        msg["From"] = value


def _smtp_profiles() -> list[dict[str, Optional[str | int | bool]]]:
    profiles: list[dict[str, Optional[str | int | bool]]] = []

    if EMAIL_SMTP_USER and EMAIL_SMTP_PASSWORD:
        profiles.append({
            "name": "smtp_auth",
            "server": EMAIL_SMTP_AUTH_SERVER,
            "port": EMAIL_SMTP_AUTH_PORT,
            "starttls": True,
            "user": EMAIL_SMTP_USER,
            "password": EMAIL_SMTP_PASSWORD,
        })

    if EMAIL_SMTP_RELAY_SERVER:
        relay_profile = {
            "name": "smtp_relay",
            "server": EMAIL_SMTP_RELAY_SERVER,
            "port": EMAIL_SMTP_RELAY_PORT,
            "starttls": False,
            "user": None,
            "password": None,
        }
        if not any(
            p["server"] == relay_profile["server"] and p["port"] == relay_profile["port"]
            for p in profiles
        ):
            profiles.append(relay_profile)

    return profiles


def _enviar_via_perfil(
    profile: dict,
    msg: Message,
    to_addrs: list[str],
    original_from: Optional[str],
    relay_from: Optional[str],
) -> None:
    """Configura headers y envía el mensaje por el perfil dado. Lanza excepción si falla."""
    name = str(profile["name"])
    server_host = str(profile["server"])
    server_port = int(profile["port"] or 25)

    if name == "smtp_relay" and relay_from:
        _replace_from_header(msg, relay_from)
    elif original_from:
        _replace_from_header(msg, original_from)

    with smtplib.SMTP(server_host, server_port, timeout=EMAIL_SMTP_TIMEOUT) as server:
        server.ehlo()
        if profile["starttls"]:
            server.starttls()
            server.ehlo()
        if profile["user"] and profile["password"]:
            server.login(str(profile["user"]), str(profile["password"]))
        server.send_message(msg, to_addrs=to_addrs)

    logger.info("Email enviado via %s (%s:%s)", name, server_host, server_port)


def send_smtp_message(msg: Message, recipients: Iterable[str]) -> bool:
    """Envia un correo usando primero SMTP autenticado y luego relay sin login."""
    to_addrs = [r for r in recipients if r]
    if not to_addrs:
        logger.warning("No hay destinatarios SMTP para enviar el correo")
        return False

    original_from = msg.get("From")
    relay_from = formataddr((EMAIL_FROM_NAME, EMAIL_FROM)) if EMAIL_FROM else None
    last_error: Exception | None = None
    for profile in _smtp_profiles():
        name = str(profile["name"])
        server_host = str(profile["server"])
        server_port = int(profile["port"] or 25)
        for intento in range(1, _SMTP_MAX_INTENTOS_POR_PERFIL + 1):
            try:
                _enviar_via_perfil(profile, msg, to_addrs, original_from, relay_from)
                return True
            except Exception as e:
                last_error = e
                logger.warning(
                    "Fallo envio email via %s (%s:%s) intento %s/%s: %s",
                    name,
                    server_host,
                    server_port,
                    intento,
                    _SMTP_MAX_INTENTOS_POR_PERFIL,
                    e,
                    exc_info=True,
                )
                es_reintentable = isinstance(e, _SMTP_RETRYABLE_EXCEPTIONS)
                if es_reintentable and intento < _SMTP_MAX_INTENTOS_POR_PERFIL:
                    time.sleep(_SMTP_RETRY_DELAY_SECONDS)
                    continue
                break

    if original_from:
        _replace_from_header(msg, original_from)
    if last_error:
        logger.error("Error SMTP al enviar email tras intentar todos los perfiles: %s", last_error)
    return False
