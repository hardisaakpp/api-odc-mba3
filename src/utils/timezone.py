"""
Utilidad centralizada de zona horaria para el proyecto.

Todas las fechas del sistema deben registrarse en la zona horaria
de Colombia (America/Bogota, UTC-5).

Uso:
    from src.utils.timezone import ahora, ahora_naive, TZ_COLOMBIA

    # Timezone-aware (para logging, contextos que soporten tz)
    fecha = ahora()

    # Naive (para SQL Server, que no maneja bien datetime con tzinfo)
    fecha = ahora_naive()
"""

from datetime import datetime
from zoneinfo import ZoneInfo

# Zona horaria de Colombia (UTC-5)
TZ_COLOMBIA = ZoneInfo("America/Bogota")


def ahora() -> datetime:
    """
    Retorna la fecha/hora actual en zona horaria de Colombia (timezone-aware).

    Returns:
        datetime con tzinfo=America/Bogota
    """
    return datetime.now(TZ_COLOMBIA)


def ahora_naive() -> datetime:
    """
    Retorna la fecha/hora actual en zona horaria de Colombia SIN tzinfo.

    Útil para compatibilidad con SQL Server, que no maneja bien
    datetime con información de zona horaria.

    Returns:
        datetime naive en hora de Colombia
    """
    return datetime.now(TZ_COLOMBIA).replace(tzinfo=None)
