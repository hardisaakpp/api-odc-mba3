#!/usr/bin/env python3
"""Genera la referencia del esquema de la base de datos (tablas, columnas, claves) leyéndola de la BD real.

Solo hace SELECT sobre las vistas de catálogo `sys.*`: no modifica nada. Usa la conexión de la propia aplicación
(`src.database.connection`), así que corre donde la app tenga acceso a la BD:

    # Desde el contenedor de la API (recomendado: ya tiene la conexión configurada)
    docker exec -i mba3-api python - < scripts/generar_esquema_bd.py > docs/ESQUEMA_BD.md

    # O en el host, con el .env del proyecto y las dependencias instaladas
    python scripts/generar_esquema_bd.py > docs/ESQUEMA_BD.md

El resultado va a la salida estándar; los mensajes de error, a la de errores.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.getcwd())

from src.database.connection import get_db_connection_context  # noqa: E402

SQL_COLUMNAS = """
SELECT s.name, t.name, c.column_id, c.name, ty.name, c.max_length, c.precision, c.scale,
       c.is_nullable, c.is_identity, dc.definition
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.default_constraints dc ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
WHERE t.is_ms_shipped = 0
ORDER BY s.name, t.name, c.column_id
"""
SQL_PK = """
SELECT s.name, t.name, c.name
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.is_primary_key = 1
ORDER BY s.name, t.name, ic.key_ordinal
"""
SQL_FK = """
SELECT sp.name, tp.name, cp.name, sr.name, tr.name, cr.name
FROM sys.foreign_key_columns fkc
JOIN sys.tables tp ON tp.object_id = fkc.parent_object_id
JOIN sys.schemas sp ON sp.schema_id = tp.schema_id
JOIN sys.columns cp ON cp.object_id = fkc.parent_object_id AND cp.column_id = fkc.parent_column_id
JOIN sys.tables tr ON tr.object_id = fkc.referenced_object_id
JOIN sys.schemas sr ON sr.schema_id = tr.schema_id
JOIN sys.columns cr ON cr.object_id = fkc.referenced_object_id AND cr.column_id = fkc.referenced_column_id
ORDER BY sp.name, tp.name, fkc.constraint_object_id, fkc.constraint_column_id
"""


def _tipo(nombre: str, longitud: int, precision: int, escala: int) -> str:
    if nombre in ("nvarchar", "nchar"):
        return f"{nombre}({'MAX' if longitud == -1 else longitud // 2})"
    if nombre in ("varchar", "char", "varbinary", "binary"):
        return f"{nombre}({'MAX' if longitud == -1 else longitud})"
    if nombre in ("decimal", "numeric"):
        return f"{nombre}({precision},{escala})"
    if nombre in ("datetime2", "time", "datetimeoffset"):
        return f"{nombre}({escala})"
    return nombre


def _defecto(definicion: str | None) -> str:
    """El motor guarda los defaults entre paréntesis dobles (`((1))`, `(newid())`); se quitan solo los que envuelven todo."""
    d = (definicion or "").strip()
    while d.startswith("(") and d.endswith(")"):
        nivel = 0
        for i, ch in enumerate(d):
            nivel += ch == "("
            nivel -= ch == ")"
            if nivel == 0 and i < len(d) - 1:
                return d  # el primer paréntesis se cierra antes del final: no envuelve todo
        d = d[1:-1].strip()
    return d


def _completo(esquema: str, tabla: str) -> str:
    return tabla if esquema == "dbo" else f"{esquema}.{tabla}"


def main() -> None:
    with get_db_connection_context() as conn:
        cur = conn.cursor()
        columnas = cur.execute(SQL_COLUMNAS).fetchall()
        pks = cur.execute(SQL_PK).fetchall()
        fks = cur.execute(SQL_FK).fetchall()
        base = cur.execute("SELECT DB_NAME()").fetchone()[0]

    tablas: dict[str, list] = defaultdict(list)
    for esq, tab, _, col, tipo, ln, pr, sc, nulo, ident, defecto in columnas:
        tablas[_completo(esq, tab)].append((col, _tipo(tipo, ln, pr, sc), bool(nulo), bool(ident), defecto))
    pk_de: dict[str, list[str]] = defaultdict(list)
    for esq, tab, col in pks:
        pk_de[_completo(esq, tab)].append(col)
    fk_de: dict[str, list[str]] = defaultdict(list)
    for esp, tp, cp, esr, tr, cr in fks:
        fk_de[_completo(esp, tp)].append(f"`{cp}` → `{_completo(esr, tr)}.{cr}`")

    out = [
        "# Esquema de la base de datos (generado)",
        "",
        f"> Generado el {date.today().isoformat()} leyendo la base `{base}` ({len(tablas)} tablas). No editar a mano: "
        "ver `scripts/generar_esquema_bd.py` para regenerarlo. Los tipos, nulabilidad, valores por defecto y claves "
        "vienen del catálogo del motor, no de los scripts de migración.",
        "> Qué hace cada migración y en qué orden se aplican: [CATALOGO_MIGRACIONES.md](CATALOGO_MIGRACIONES.md). "
        "Descripción funcional de las tablas de pedidos y sus campos Excel: [ESTRUCTURA_BD_PEDIDOS.md](ESTRUCTURA_BD_PEDIDOS.md).",
        "",
        "## Índice de tablas",
        "",
        *[f"- `{t}` — {len(c)} columnas" for t, c in sorted(tablas.items())],
        "",
        "## Tablas",
        "",
    ]
    for tabla in sorted(tablas):
        out += [f"### `{tabla}`", ""]
        if pk_de.get(tabla):
            out += [f"**Clave primaria:** {', '.join(f'`{c}`' for c in pk_de[tabla])}", ""]
        out += ["| Columna | Tipo | Nulo | Por defecto |", "|---|---|:--:|---|"]
        for col, tipo, nulo, ident, defecto in tablas[tabla]:
            extra = " (identity)" if ident else ""
            d = f"`{_defecto(defecto)}`" if defecto else ""
            out.append(f"| `{col}` | {tipo}{extra} | {'sí' if nulo else 'no'} | {d} |")
        out.append("")
        if fk_de.get(tabla):
            out += ["**Claves foráneas:** " + "; ".join(fk_de[tabla]), ""]
    sys.stdout.write("\n".join(out).rstrip() + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - se informa y se sale con error, sin trazas de credenciales
        print(f"Error al leer el esquema: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
