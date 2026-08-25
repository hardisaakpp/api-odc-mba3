"""
Backfill puntual: puebla tienda.marca (ROLAND/REGIONS/DESCUENTON) para las
tiendas ya existentes en el catálogo local, consultando sc_maestros.dbo.almacenes_local
(servidor de producción 192.168.2.211, SOLO LECTURA) por u_bod_tra = tienda.codigo.

whs_code en esa tabla es el código del Centro de Distribución (RL-CD, RG-CD,
OUT-CD), NO el código de tienda del Excel — el código de tienda vive en
u_bod_tra (confirmado 20/08/2026 contra datos reales).

Las tiendas nuevas ya se resuelven automáticamente al crearse
(PedidoTiendaRepository.get_or_create_tienda). Este script es solo para las que
ya existían en la base antes de esa migración/enriquecimiento.

Uso:
    python scripts/backfill_marca_tienda.py
"""

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.database.connection import get_db_connection_context, get_maestros_db_connection_context  # noqa: E402
from src.database.services.marca_tienda_service import MARCA_A_BODEGA  # noqa: E402


def main():
    with get_db_connection_context() as conn_local:
        cursor_local = conn_local.cursor()
        cursor_local.execute(
            "SELECT tienda_id, codigo FROM tienda WHERE marca IS NULL AND activa = 1"
        )
        pendientes = cursor_local.fetchall()
        cursor_local.close()

    total = len(pendientes)
    print(f"📋 Tiendas sin marca a resolver: {total}")
    if total == 0:
        return

    resueltas = 0
    sin_match = []

    with get_maestros_db_connection_context() as conn_maestros:
        cursor_maestros = conn_maestros.cursor()

        with get_db_connection_context() as conn_local:
            cursor_local = conn_local.cursor()

            for tienda_id, codigo in pendientes:
                codigo_normalizado = (codigo or "").strip().upper()
                if not codigo_normalizado:
                    continue

                cursor_maestros.execute(
                    "SELECT u_marca FROM almacenes_local WHERE u_bod_tra = ?",
                    (codigo_normalizado,),
                )
                row = cursor_maestros.fetchone()
                marca = (row[0] or "").strip().upper() if row and row[0] else None

                if not marca or marca not in MARCA_A_BODEGA:
                    sin_match.append(codigo_normalizado)
                    continue

                cursor_local.execute(
                    "UPDATE tienda SET marca = ? WHERE tienda_id = ?",
                    (marca, tienda_id),
                )
                resueltas += 1
                print(f"  ✅ {codigo_normalizado} → {marca} ({MARCA_A_BODEGA[marca]})")

            conn_local.commit()
            cursor_local.close()

        cursor_maestros.close()

    print()
    print("=" * 60)
    print(f"✅ Resueltas: {resueltas}/{total}")
    print(f"⚠️ Sin match en sc_maestros: {len(sin_match)}")
    if sin_match:
        print(f"   Códigos sin match: {sin_match}")
    print("=" * 60)


if __name__ == "__main__":
    main()
