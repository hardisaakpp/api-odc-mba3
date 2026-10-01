#!/usr/bin/env python3
"""Genera docs/CATALOGO_MIGRACIONES.md a partir de scripts/migrations_manifest.yaml.

Uso:
    python scripts/generar_catalogo_migraciones.py

El manifest es la fuente de verdad del orden de ejecución; este catálogo solo lo hace legible. No se edita a mano:
se vuelve a generar al agregar una migración.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
# Descripciones del manifest que hoy contradicen el comportamiento real. NO se corrige el manifest (versiones ya
# aplicadas, su contenido es metadato histórico); se anota aquí lo verificado en el código del frontend/backend, para
# que quien lea el catálogo no se quede con la versión incorrecta.
NOTAS_DE_REVISION = {
    "627": "La descripción dice que `fecha_facturacion` es editable solo por `produccion-elrayo.view` en Gestionar Pedido. "
           "Hoy es **exclusiva de `odcsap.view` (EL RAYO)** y solo se edita con el pedido en **Confirmado y Enviado**; habilita el "
           "botón \"Despachar y Facturar\" (verificado en `PedidoDetalleView.vue`, `puedeEditarFechaFacturacion`).",
    "639": "La descripción invierte los colores. En el Detalle del Pedido, lo que editó **EL RAYO (`odcsap.view`, rol ODCSAP) se "
           "resalta en púrpura** y lo que editó **Producción El Rayo (rol PRODUCCION_ELRAYO) en naranja** (verificado en "
           "`PedidoDetalleView.vue`, `claseResaltadoModificado`).",
}
CATEGORIAS = {
    "base": "Estructura base (tablas y objetos iniciales)",
    "alter": "Cambios de estructura (ALTER)",
    "data": "Datos (inserts/updates de catálogos)",
    "estado": "Estados del pedido",
    "index": "Índices",
    "config": "Configuración",
    "rollback": "Reversiones",
}


def main() -> None:
    manifest = yaml.safe_load((RAIZ / "scripts" / "migrations_manifest.yaml").read_text(encoding="utf-8"))["migrations"]
    por_categoria = Counter(m["category"] for m in manifest)
    ultima = next((m for m in reversed(manifest) if "manual" not in m), manifest[-1])

    lineas = [
        "# Catálogo de migraciones (generado)",
        "",
        f"> Generado el {date.today().isoformat()} desde `scripts/migrations_manifest.yaml`: **{len(manifest)} migraciones**, "
        f"la última es la **{ultima['version']}** (`{ultima['name']}`). No editar a mano: ejecutar "
        "`python scripts/generar_catalogo_migraciones.py` al agregar una migración.",
        "> Cómo se aplican, el orden y el manejo de errores: ver [DEPLOY_MIGRATIONS.md](DEPLOY_MIGRATIONS.md). La tabla va "
        "**en el orden de ejecución del manifest**, que no siempre coincide con el número de versión (por ejemplo, la "
        "008 se ejecuta antes que la 007 porque esta depende de aquella).",
        "",
        "## Resumen por categoría",
        "",
        *[f"- **{CATEGORIAS.get(c, c)}** (`{c}`): {n}" for c, n in sorted(por_categoria.items())],
        "",
        "## Migraciones en orden de ejecución",
        "",
    ]
    for m in manifest:
        extras = []
        if m.get("dependencies"):
            extras.append("depende de: " + ", ".join(f"`{d}`" for d in m["dependencies"]))
        if m.get("manual"):
            extras.append("**se ejecuta manualmente**, no en la corrida automática")
        lineas += [
            f"### Migración {m['version']} — `{m['name']}`",
            "",
            f"- **Categoría:** {CATEGORIAS.get(m['category'], m['category'])}",
            f"- **Archivo:** `scripts/{m['file']}`",
            f"- **Qué hace:** {m['description']}",
            *([f"- **Notas:** {'; '.join(extras)}"] if extras else []),
            *([f"- **Nota de revisión:** {NOTAS_DE_REVISION[str(m['version'])]}"] if str(m["version"]) in NOTAS_DE_REVISION else []),
            "",
        ]
    destino = RAIZ / "docs" / "CATALOGO_MIGRACIONES.md"
    destino.write_text("\n".join(lineas).rstrip() + "\n", encoding="utf-8")
    print(f"Escrito {destino} ({len(manifest)} migraciones)")


if __name__ == "__main__":
    main()
