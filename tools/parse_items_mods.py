"""
Parsea items y recopila iconos de todos los mods instalados vía Steam
Workshop en un servidor dedicado de Project Zomboid (gestionado con
LinuxGSM), a partir de los IDs declarados en WorkshopItems= del .ini
del servidor.

Estructura real observada (puede variar entre mods):
    <content_dir>/<WorkshopID>/mods/<id_interno_mod>/<carpeta_version>/
        mod.info
        media/scripts/...      (si el mod añade items)
        media/textures/...     (iconos sueltos, prefijo Item_, sin .pack)
    <content_dir>/<WorkshopID>/mods/<id_interno_mod>/common/media/textures/...
        (iconos adicionales, fuera de la carpeta de versión)

Un mismo mod puede tener varias carpetas de versión (ej. 42.0 y 42.13);
se usa solo la más reciente, para no duplicar items.

Salida:
    data/items_mods.json    (mismo formato que items.json, con _source =
                              id interno del mod en vez de "vanilla")
    data/icons_mods/*.png   (copia de los iconos sueltos de cada mod)
"""

import json
import re
import shutil
import sys
from pathlib import Path

# Reutilizamos las mismas funciones que parse_items.py (si están en el
# mismo paquete tools/, se podrían importar directamente; aquí las
# repetimos para que este script sea autocontenido).

ITEM_RE = re.compile(r"\bitem\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)
MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)
VERSION_DIR_RE = re.compile(r"^\d+(\.\d+)*$")


def strip_line_comments(text):
    return "\n".join(line.split("//")[0] for line in text.split("\n"))


def find_matching_brace(text, open_idx):
    depth = 0
    i = open_idx
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def parse_kv_block(block):
    out = {}
    for line in block.split("\n"):
        line = line.split("/*")[0].split("//")[0].strip()
        if not line or line.startswith("/"):
            continue
        line = line.rstrip(",").strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            continue
        if k in out:
            out[k] = out[k] + [v] if isinstance(out[k], list) else [out[k], v]
        else:
            out[k] = v
    return out


def parse_scripts_file(path):
    text = strip_line_comments(path.read_text(encoding="utf-8", errors="replace"))
    items = []
    for m_module in MODULE_RE.finditer(text):
        module_name = m_module.group(1)
        brace_open = text.find("{", m_module.end() - 1)
        if brace_open < 0:
            continue
        brace_close = find_matching_brace(text, brace_open)
        if brace_close < 0:
            continue
        module_body = text[brace_open + 1:brace_close]
        for m_item in ITEM_RE.finditer(module_body):
            item_name = m_item.group(1)
            i_open = module_body.find("{", m_item.end() - 1)
            if i_open < 0:
                continue
            i_close = find_matching_brace(module_body, i_open)
            if i_close < 0:
                continue
            kv = parse_kv_block(module_body[i_open + 1:i_close])
            kv["_name"] = item_name
            kv["_module"] = module_name
            kv["_full_id"] = f"{module_name}.{item_name}"
            kv["_source_file"] = path.name
            items.append(kv)
    return items


def leer_mod_info(ruta_mod_info):
    """Parsea mod.info (formato clave=valor simple, sin comillas de cierre
    fiables -- se ha visto 'name='70 Plymouth Barracuda sin comilla final)."""
    info = {}
    texto = ruta_mod_info.read_text(encoding="utf-8", errors="replace")
    for linea in texto.split("\n"):
        linea = linea.strip()
        if "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        info[clave.strip()] = valor.strip().strip("'").strip('"')
    return info


def elegir_carpeta_version(carpeta_mod):
    """De entre las subcarpetas tipo '42', '42.0', '42.13', elige la de
    versión más alta. Si no hay ninguna con ese patrón, devuelve None."""
    candidatas = [
        d for d in carpeta_mod.iterdir()
        if d.is_dir() and VERSION_DIR_RE.match(d.name)
    ]
    if not candidatas:
        return None

    def como_tupla(d):
        return tuple(int(p) for p in d.name.split("."))

    return max(candidatas, key=como_tupla)


def procesar_mod(carpeta_mod, carpeta_salida_iconos):
    """Procesa un único mod (una carpeta bajo mods/<id_interno>/).
    Devuelve (items_encontrados, nombre_mostrado_del_mod)."""
    carpeta_version = elegir_carpeta_version(carpeta_mod)
    if carpeta_version is None:
        return [], None

    ruta_mod_info = carpeta_version / "mod.info"
    if not ruta_mod_info.exists():
        ruta_mod_info = carpeta_mod / "mod.info"
    if not ruta_mod_info.exists():
        return [], None

    info = leer_mod_info(ruta_mod_info)
    nombre_mod = info.get("name", carpeta_mod.name)
    id_mod = info.get("id", carpeta_mod.name)

    items = []
    carpeta_scripts = carpeta_version / "media" / "scripts"
    if carpeta_scripts.exists():
        for archivo_txt in carpeta_scripts.rglob("*.txt"):
            encontrados = parse_scripts_file(archivo_txt)
            for it in encontrados:
                it["_source"] = id_mod
                it["_source_name"] = nombre_mod
            items.extend(encontrados)

    # Iconos sueltos: tanto en la carpeta de versión como en common/
    rutas_texturas = [
        carpeta_version / "media" / "textures",
        carpeta_mod / "common" / "media" / "textures",
    ]
    for ruta_texturas in rutas_texturas:
        if not ruta_texturas.exists():
            continue
        for png in ruta_texturas.glob("*.png"):
            destino = carpeta_salida_iconos / png.name
            if not destino.exists():
                shutil.copy2(png, destino)

    return items, nombre_mod


def main():
    if len(sys.argv) < 3:
        print(f"Uso: {sys.argv[0]} <carpeta_content_108600> <carpeta_salida_data>")
        sys.exit(1)

    carpeta_content = Path(sys.argv[1])
    carpeta_salida = Path(sys.argv[2])
    carpeta_salida_iconos = carpeta_salida / "icons_mods"
    carpeta_salida_iconos.mkdir(parents=True, exist_ok=True)

    todos_los_items = []
    mods_con_items = 0
    mods_sin_items = 0
    mods_sin_mod_info = 0

    carpetas_workshop = sorted(p for p in carpeta_content.iterdir() if p.is_dir())
    print(f"Explorando {len(carpetas_workshop)} IDs de Workshop...")

    for carpeta_workshop_id in carpetas_workshop:
        carpeta_mods = carpeta_workshop_id / "mods"
        if not carpeta_mods.exists():
            continue
        for carpeta_mod in carpeta_mods.iterdir():
            if not carpeta_mod.is_dir():
                continue
            items, nombre_mod = procesar_mod(carpeta_mod, carpeta_salida_iconos)
            if nombre_mod is None:
                mods_sin_mod_info += 1
                continue
            if items:
                mods_con_items += 1
                todos_los_items.extend(items)
            else:
                mods_sin_items += 1

    ruta_salida_json = carpeta_salida / "items_mods.json"
    with open(ruta_salida_json, "w", encoding="utf-8") as f:
        json.dump(todos_los_items, f, indent=2, ensure_ascii=False)

    print(f"\nMods con items nuevos: {mods_con_items}")
    print(f"Mods sin items (solo coches/ropa/lua, etc.): {mods_sin_items}")
    print(f"Mods sin mod.info legible: {mods_sin_mod_info}")
    print(f"Total de items de mods: {len(todos_los_items)}")
    print(f"Guardado: {ruta_salida_json}")
    print(f"Iconos de mods copiados a: {carpeta_salida_iconos}")


if __name__ == "__main__":
    main()