"""
Extrae traducciones de nombres de items de todos los mods de Workshop
instalados, pero SOLO para los idiomas que ya soportamos en vanilla
(ES, ES_CL, ES_MX, FR, DE, IT, PT, RU, PL, NL). Cualquier otro idioma
que traiga un mod (PTBR, JP, CN, etc.) se ignora deliberadamente.

La estructura real varía bastante entre mods (mayúsculas/minúsculas
distintas, con o sin el segmento 'lua', repetida en varias carpetas de
versión a la vez), así que en vez de asumir una ruta fija, se busca
cualquier carpeta llamada "Translate" (case-insensitive) dentro de cada
mod, y dentro de ella cualquier subcarpeta de idioma soportado con un
archivo ItemName.json (también case-insensitive).

Salida: data/translations_mods.json con la forma:
    { "Base.Hammer": {"ES": "Martillo", ...}, ... }
"""

import json
import re
import sys
from pathlib import Path

IDIOMAS_SOPORTADOS = {"ES", "ES_CL", "ES_MX", "FR", "DE", "IT", "PT", "RU", "PL", "NL"}
VERSION_DIR_RE = re.compile(r"^\d+(\.\d+)*$")


def elegir_carpeta_version(carpeta_mod):
    candidatas = [d for d in carpeta_mod.iterdir() if d.is_dir() and VERSION_DIR_RE.match(d.name)]
    if not candidatas:
        return None
    return max(candidatas, key=lambda d: tuple(int(p) for p in d.name.split(".")))


def encontrar_carpetas_translate(raiz):
    """Busca cualquier carpeta llamada 'Translate' (sin importar mayúsculas)
    en cualquier nivel de profundidad bajo raiz."""
    if not raiz.exists():
        return []
    return [p for p in raiz.rglob("*") if p.is_dir() and p.name.lower() == "translate"]


def buscar_archivo_itemname(carpeta_idioma):
    """Busca itemname.json dentro de una carpeta de idioma, sin importar
    las mayúsculas del nombre de archivo."""
    for f in carpeta_idioma.iterdir():
        if f.is_file() and f.name.lower() == "itemname.json":
            return f
    return None


def procesar_mod(carpeta_mod):
    """Devuelve un dict {full_id: {idioma: nombre}} con las traducciones
    encontradas para este mod, recorriendo tanto su carpeta de versión
    más reciente como su carpeta common/, si existen."""
    raices = []
    carpeta_version = elegir_carpeta_version(carpeta_mod)
    if carpeta_version:
        raices.append(carpeta_version)
    carpeta_common = carpeta_mod / "common"
    if carpeta_common.exists():
        raices.append(carpeta_common)
    if not raices:
        raices = [carpeta_mod]

    resultado = {}
    for raiz in raices:
        for carpeta_translate in encontrar_carpetas_translate(raiz):
            for carpeta_idioma in carpeta_translate.iterdir():
                if not carpeta_idioma.is_dir():
                    continue
                codigo = carpeta_idioma.name.upper()
                if codigo not in IDIOMAS_SOPORTADOS:
                    continue  # idioma no soportado, se ignora a propósito

                archivo = buscar_archivo_itemname(carpeta_idioma)
                if not archivo:
                    continue
                try:
                    datos = json.loads(archivo.read_text(encoding="utf-8", errors="replace"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                for full_id, nombre in datos.items():
                    resultado.setdefault(full_id, {})[codigo] = nombre

    return resultado


def main():
    if len(sys.argv) < 3:
        print(f"Uso: {sys.argv[0]} <carpeta_content_108600> <salida_json>")
        sys.exit(1)

    carpeta_content = Path(sys.argv[1])
    ruta_salida = Path(sys.argv[2])

    traducciones = {}
    mods_con_traducciones = 0
    mods_sin_traducciones = 0

    carpetas_workshop = sorted(p for p in carpeta_content.iterdir() if p.is_dir())
    print(f"Explorando {len(carpetas_workshop)} IDs de Workshop...")

    for carpeta_workshop_id in carpetas_workshop:
        carpeta_mods = carpeta_workshop_id / "mods"
        if not carpeta_mods.exists():
            continue
        for carpeta_mod in carpeta_mods.iterdir():
            if not carpeta_mod.is_dir():
                continue
            resultado_mod = procesar_mod(carpeta_mod)
            if resultado_mod:
                mods_con_traducciones += 1
                for full_id, idiomas in resultado_mod.items():
                    traducciones.setdefault(full_id, {}).update(idiomas)
            else:
                mods_sin_traducciones += 1

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(traducciones, f, indent=2, ensure_ascii=False)

    print(f"\nMods con traducciones en idiomas soportados: {mods_con_traducciones}")
    print(f"Mods sin traducciones en esos idiomas: {mods_sin_traducciones}")
    print(f"Total de items de mods con al menos una traducción: {len(traducciones)}")
    print(f"Guardado: {ruta_salida}")


if __name__ == "__main__":
    main()