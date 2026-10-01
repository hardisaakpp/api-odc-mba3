#!/usr/bin/env python3
"""Genera docs/REFERENCIA_API.md a partir del OpenAPI del servicio en ejecución.

Uso:
    python scripts/generar_referencia_api.py                         # lee http://localhost:8000/openapi.json
    python scripts/generar_referencia_api.py --url http://host:8000/openapi.json
    python scripts/generar_referencia_api.py --archivo openapi.json  # desde un archivo ya descargado

Rutas, parámetros, respuestas y descripciones salen del OpenAPI (las descripciones son las docstrings de cada
endpoint). El permiso exigido no está en el OpenAPI: se lee del código (`require_permission(...)`,
`require_any_permission([...])`, `require_admin()`) analizando `src/` con `ast`, resolviendo constantes como
`_PERM_MABEL = 'mabel.view'`. Si un endpoint no tiene ninguna de esas dependencias se indica "No exige permiso
específico" — es lo que dice el código, no una suposición.

El archivo generado NO se edita a mano: se vuelve a generar tras cambiar endpoints.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUNCIONES_PERMISO = {"require_permission", "require_any_permission", "require_admin"}
METODOS = ("get", "post", "put", "patch", "delete")


# ── Permisos: análisis estático del código ──────────────────────────────────────────────────────────────────────
def _constantes_texto(arbol: ast.AST) -> dict[str, str | list[str]]:
    """Constantes de módulo `NOMBRE = 'texto'` y listas/tuplas de ellas (`PERMS = [A, B]`; las listas se resuelven después)."""
    out: dict[str, str | list[str]] = {}
    for nodo in getattr(arbol, "body", []):
        if not isinstance(nodo, ast.Assign):
            continue
        for t in nodo.targets:
            if not isinstance(t, ast.Name):
                continue
            if isinstance(nodo.value, ast.Constant) and isinstance(nodo.value.value, str):
                out[t.id] = nodo.value.value
            elif isinstance(nodo.value, (ast.List, ast.Tuple)):
                out[t.id] = [e.id if isinstance(e, ast.Name) else e.value for e in nodo.value.elts
                             if isinstance(e, ast.Name) or (isinstance(e, ast.Constant) and isinstance(e.value, str))]
    return out


def _resolver(nombre: str, consts: dict, vistos: frozenset = frozenset()) -> list[str]:
    if nombre in vistos or nombre not in consts:
        return [f"<{nombre}>"]
    valor = consts[nombre]
    if isinstance(valor, str):
        return [valor]
    return [v for n in valor for v in (_resolver(n, consts, vistos | {nombre}) if n in consts else [n])]


def _valores(nodo: ast.AST, consts: dict) -> list[str]:
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return [nodo.value]
    if isinstance(nodo, ast.Name):
        return _resolver(nodo.id, consts)
    if isinstance(nodo, (ast.List, ast.Tuple)):
        return [v for e in nodo.elts for v in _valores(e, consts)]
    return []


def _permisos_en(nodo: ast.AST, consts: dict) -> list[tuple[str, list[str]]]:
    """[(tipo, permisos)] de cada llamada a require_* dentro del nodo."""
    hallados = []
    for sub in ast.walk(nodo):
        # `Depends(verify_jwt_token)`: exige un token válido, pero ningún permiso concreto.
        if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "Depends"
                and sub.args and isinstance(sub.args[0], ast.Name) and sub.args[0].id == "verify_jwt_token"):
            hallados.append(("verify_jwt_token", []))
        if isinstance(sub, ast.Call):
            nombre = sub.func.id if isinstance(sub.func, ast.Name) else getattr(sub.func, "attr", "")
            if nombre in FUNCIONES_PERMISO:
                valores = [v for a in sub.args for v in _valores(a, consts)]
                hallados.append((nombre, valores))
    return hallados


def permisos_por_funcion() -> dict[str, list[tuple[str, list[str]]]]:
    """nombre de función -> permisos que exige (de la propia función y de los `dependencies` de su decorador)."""
    arboles = {}
    consts_globales: dict = {}
    for f in (RAIZ / "src").rglob("*.py"):
        try:
            arboles[f] = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        consts_globales.update(_constantes_texto(arboles[f]))
    out: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for f, arbol in arboles.items():
        consts = {**consts_globales, **_constantes_texto(arbol)}
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Se recorren decoradores y argumentos (los `Depends(...)` van en los defaults), no el cuerpo.
                partes = [*nodo.decorator_list, *nodo.args.defaults, *[d for d in nodo.args.kw_defaults if d]]
                for p in partes:
                    out[nodo.name].extend(_permisos_en(p, consts))
    return out


def permiso_de(operation_id: str, metodo: str, funciones: dict[str, list]) -> list[tuple[str, list[str]]] | None:
    """El operationId es `<funcion>_<ruta>_<metodo>`: se busca la función de nombre más largo que sea prefijo."""
    candidatos = [n for n in funciones if operation_id.startswith(n + "_") and operation_id.endswith("_" + metodo)]
    if not candidatos:
        return None
    return funciones[max(candidatos, key=len)]


def texto_permiso(perms: list[tuple[str, list[str]]] | None) -> str:
    if perms is None:
        return "_No determinado_"
    con_permiso = [(t, v) for t, v in perms if t != "verify_jwt_token"]
    if not con_permiso:
        if any(t == "verify_jwt_token" for t, _ in perms):
            return "Solo un token JWT válido (el endpoint no exige un permiso específico)"
        return "Sin autenticación declarada en el endpoint (público, o validada por otro mecanismo)"
    partes = []
    for tipo, valores in dict.fromkeys((t, tuple(v)) for t, v in con_permiso):
        if tipo == "require_admin":
            partes.append("rol **Admin**")
        elif tipo == "require_any_permission":
            partes.append(" o ".join(f"`{v}`" for v in valores) + " (cualquiera de ellos)")
        else:
            partes.append(" y ".join(f"`{v}`" for v in valores))
    return "; ".join(partes)


# ── Render ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _tipo(esquema: dict) -> str:
    if "$ref" in esquema:
        return esquema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in esquema:
        return " | ".join(sorted({_tipo(s) for s in esquema["anyOf"] if s.get("type") != "null"})) or "any"
    if esquema.get("type") == "array":
        return f"lista de {_tipo(esquema.get('items', {}))}"
    return esquema.get("format") or esquema.get("type", "any")


def _descripcion(texto: str) -> str:
    """Respeta el markdown de la docstring pero baja los encabezados (#) a negritas para no romper la jerarquía."""
    salida, en_codigo = [], False
    for linea in texto.strip().splitlines():
        if linea.lstrip().startswith("```"):
            en_codigo = not en_codigo
        if not en_codigo and re.match(r"^\s*#{1,6}\s+", linea):
            linea = "**" + re.sub(r"^\s*#{1,6}\s+", "", linea).strip() + "**"
        salida.append(linea.rstrip())
    return "\n".join(salida)


def renderizar(openapi: dict) -> str:
    funciones = permisos_por_funcion()
    por_tag: dict[str, list] = defaultdict(list)
    for ruta, ops in openapi["paths"].items():
        for metodo in METODOS:
            if metodo in ops:
                op = ops[metodo]
                por_tag[(op.get("tags") or ["Sin etiqueta"])[0]].append((ruta, metodo, op))

    total = sum(len(v) for v in por_tag.values())
    sin_permiso_det = 0
    lineas = [
        "# Referencia de la API (generada)",
        "",
        f"> Generado el {date.today().isoformat()} desde el OpenAPI del servicio (`{openapi['info'].get('title', '')}` "
        f"v{openapi['info'].get('version', '')}): **{total} operaciones**. No editar a mano: ejecutar "
        "`python scripts/generar_referencia_api.py` tras cambiar endpoints.",
        "> El permiso de cada endpoint se lee del código fuente (`require_permission`, `require_any_permission`, "
        "`require_admin`); si no hay ninguno se indica si basta un token JWT válido o si el endpoint no declara autenticación.",
        "",
        "## Índice por grupo",
        "",
        *[f"- **{tag}** — {len(v)} operaciones" for tag, v in sorted(por_tag.items())],
        "",
    ]
    for tag in sorted(por_tag):
        lineas += [f"## {tag}", ""]
        for ruta, metodo, op in sorted(por_tag[tag], key=lambda x: (x[0], METODOS.index(x[1]))):
            perms = permiso_de(op.get("operationId", ""), metodo, funciones)
            sin_permiso_det += perms is None
            lineas += [f"### `{metodo.upper()} {ruta}`", ""]
            if op.get("deprecated"):
                lineas += ["**Obsoleto.**", ""]
            lineas += [f"**Permiso requerido:** {texto_permiso(perms)}", ""]
            if op.get("description"):
                lineas += [_descripcion(op["description"]), ""]
            params = op.get("parameters", [])
            if params:
                lineas += ["**Parámetros:**", ""]
                for p in params:
                    obligatorio = "obligatorio" if p.get("required") else "opcional"
                    extra = f" — {p['description']}" if p.get("description") else ""
                    lineas.append(f"- `{p['name']}` ({p['in']}, {_tipo(p.get('schema', {}))}, {obligatorio}){extra}")
                lineas.append("")
            cuerpo = op.get("requestBody", {}).get("content", {})
            if cuerpo:
                tipos = ", ".join(f"`{ct}` → {_tipo(c.get('schema', {}))}" for ct, c in cuerpo.items())
                lineas += [f"**Cuerpo de la petición:** {tipos}", ""]
            codigos = ", ".join(f"`{c}`" for c in op.get("responses", {}))
            if codigos:
                lineas += [f"**Respuestas:** {codigos}", ""]
    print(f"{total} operaciones; permiso no determinado en {sin_permiso_det}", file=sys.stderr)
    return "\n".join(lineas).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000/openapi.json")
    ap.add_argument("--archivo", help="OpenAPI ya descargado (en lugar de --url)")
    ap.add_argument("--salida", default=str(RAIZ / "docs" / "REFERENCIA_API.md"))
    args = ap.parse_args()
    if args.archivo:
        openapi = json.loads(Path(args.archivo).read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(args.url, timeout=30) as r:  # noqa: S310 - URL de administración, no de usuario
            openapi = json.load(r)
    Path(args.salida).write_text(renderizar(openapi), encoding="utf-8")
    print(f"Escrito {args.salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
