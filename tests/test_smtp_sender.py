"""
Tests de comportamiento para send_smtp_message (src/utils/smtp_sender.py): reintentos
por perfil, clasificación de errores reintentables vs no reintentables, fallback entre
perfiles (auth -> relay) y restauración del header From tras agotar todos los perfiles.

Escritos como red de seguridad ANTES de refactorizar send_smtp_message para bajar su
complejidad cognitiva (python:S3776) -- la función no tenía tests dedicados pese a ser
el único punto de envío real de correo de toda la app.
"""

from email.message import Message
from unittest.mock import patch

from src.utils import smtp_sender


def _msg(from_addr: str = "orig@example.com") -> Message:
    msg = Message()
    msg["From"] = from_addr
    return msg


def _perfil(nombre: str, server: str = "smtp.example.com", port: int = 587) -> dict:
    return {
        "name": nombre,
        "server": server,
        "port": port,
        "starttls": nombre != "smtp_relay",
        "user": "u" if nombre != "smtp_relay" else None,
        "password": "p" if nombre != "smtp_relay" else None,
    }


class TestSinDestinatarios:
    def test_sin_destinatarios_no_intenta_enviar(self):
        with patch.object(smtp_sender, "_smtp_profiles") as mock_profiles, patch.object(
            smtp_sender, "_enviar_via_perfil"
        ) as mock_enviar:
            resultado = smtp_sender.send_smtp_message(_msg(), [])

        assert resultado is False
        mock_profiles.assert_not_called()
        mock_enviar.assert_not_called()

    def test_destinatarios_vacios_se_filtran(self):
        """Recipients con strings vacías/None no cuentan como destinatarios válidos."""
        with patch.object(smtp_sender, "_smtp_profiles") as mock_profiles:
            resultado = smtp_sender.send_smtp_message(_msg(), ["", None, ""])

        assert resultado is False
        mock_profiles.assert_not_called()


class TestExitoPrimerIntento:
    def test_exito_en_primer_perfil_primer_intento(self):
        with patch.object(
            smtp_sender, "_smtp_profiles", return_value=[_perfil("smtp_auth")]
        ), patch.object(smtp_sender, "_enviar_via_perfil") as mock_enviar, patch.object(
            smtp_sender.time, "sleep"
        ) as mock_sleep:
            resultado = smtp_sender.send_smtp_message(_msg(), ["a@b.com"])

        assert resultado is True
        assert mock_enviar.call_count == 1
        mock_sleep.assert_not_called()


class TestReintentosPorPerfil:
    def test_error_reintentable_reintenta_y_luego_tiene_exito(self):
        """SMTPServerDisconnected es reintentable: debe reintentar el MISMO perfil."""
        with patch.object(
            smtp_sender, "_smtp_profiles", return_value=[_perfil("smtp_auth")]
        ), patch.object(
            smtp_sender,
            "_enviar_via_perfil",
            side_effect=[ConnectionError("hipo de red"), None],
        ) as mock_enviar, patch.object(smtp_sender.time, "sleep") as mock_sleep:
            resultado = smtp_sender.send_smtp_message(_msg(), ["a@b.com"])

        assert resultado is True
        assert mock_enviar.call_count == 2
        mock_sleep.assert_called_once_with(smtp_sender._SMTP_RETRY_DELAY_SECONDS)

    def test_error_reintentable_agota_intentos_del_perfil_y_pasa_al_siguiente(self):
        with patch.object(
            smtp_sender,
            "_smtp_profiles",
            return_value=[_perfil("smtp_auth"), _perfil("smtp_relay")],
        ), patch.object(
            smtp_sender,
            "_enviar_via_perfil",
            side_effect=[ConnectionError("a"), ConnectionError("b"), None],
        ) as mock_enviar, patch.object(smtp_sender.time, "sleep"):
            resultado = smtp_sender.send_smtp_message(_msg(), ["a@b.com"])

        assert resultado is True
        # 2 intentos agotados en smtp_auth (_SMTP_MAX_INTENTOS_POR_PERFIL) + 1 en smtp_relay
        assert mock_enviar.call_count == 3

    def test_error_no_reintentable_no_reintenta_el_mismo_perfil(self):
        """Un error de autenticación no debe reintentarse dentro del mismo perfil,
        debe pasar directo al siguiente perfil disponible."""
        with patch.object(
            smtp_sender,
            "_smtp_profiles",
            return_value=[_perfil("smtp_auth"), _perfil("smtp_relay")],
        ), patch.object(
            smtp_sender,
            "_enviar_via_perfil",
            side_effect=[ValueError("credenciales inválidas"), None],
        ) as mock_enviar, patch.object(smtp_sender.time, "sleep") as mock_sleep:
            resultado = smtp_sender.send_smtp_message(_msg(), ["a@b.com"])

        assert resultado is True
        assert mock_enviar.call_count == 2  # 1 en smtp_auth (sin reintento) + 1 en smtp_relay
        mock_sleep.assert_not_called()


class TestTodosLosPerfilesFallan:
    def test_todos_los_perfiles_fallan_restaura_from_y_retorna_false(self):
        original = "orig@example.com"
        msg = _msg(original)

        with patch.object(
            smtp_sender,
            "_smtp_profiles",
            return_value=[_perfil("smtp_auth"), _perfil("smtp_relay")],
        ), patch.object(
            smtp_sender,
            "_enviar_via_perfil",
            side_effect=ValueError("siempre falla"),
        ) as mock_enviar, patch.object(smtp_sender.time, "sleep"):
            resultado = smtp_sender.send_smtp_message(msg, ["a@b.com"])

        assert resultado is False
        assert mock_enviar.call_count == 2  # 1 por perfil (error no reintentable)
        assert msg.get("From") == original

    def test_sin_perfiles_configurados_retorna_false(self):
        with patch.object(smtp_sender, "_smtp_profiles", return_value=[]):
            resultado = smtp_sender.send_smtp_message(_msg(), ["a@b.com"])

        assert resultado is False
