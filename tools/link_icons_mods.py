"""
Enlaza cada item de data/items_mods.json con su icono real.

Orden de búsqueda para cada item:
  1. En data/icons_mods/ (PNG sueltos de los mods), ignorando mayúsculas.
  2. Si no está, en el índice de iconos vanilla (icon_index.json), porque
     muchos mods reutilizan iconos del juego base sin incluirlos.

Valores de Icon= como "na" o "none" son marcadores de "sin icono" que
ponen algunos autores de mods, y se tratan como si no hubiera icono.

Es idempotente: recalcula _icon_file desde Icon/IconsForTexture, así que
se puede ejecutar varias veces sin problema.

Salida: sobrescribe data/items_mods.json con el campo _icon_file.
"""

import json
import sys
from pathlib import Path

VALORES_SIN_ICONO = {"", "na", "n/a", "none", "null"}


def cargar_json(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_json(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)


def primero(valor):
    return valor[0] if isinstance(valor, list) else valor


def obtener_nombre_icono(item):
    """Devuelve el nombre de icono a buscar, o None si no hay o es un
    marcador de 'sin icono' (na, none...)."""
    icono = item.get("Icon")
    if not icono:
        iconos_textura = item.get("IconsForTexture")
        if iconos_textura:
            icono = primero(iconos_textura).split(";")[0]
    if not icono:
        return None
    icono = primero(icono).strip()
    if icono.lower() in VALORES_SIN_ICONO:
        return None
    return icono


def buscar_en_mods(nombre_icono, archivos_por_minuscula):
    """archivos_por_minuscula: dict {nombre_en_minusculas: nombre_real}.
    Compara ignorando mayúsculas y devuelve el nombre real del archivo."""
    n = nombre_icono.lower()
    for candidato in (f"item_{n}.png", f"{n}.png"):
        if candidato in archivos_por_minuscula:
            return archivos_por_minuscula[candidato]

    prefijo = f"item_{n}_"
    variantes = sorted(k for k in archivos_por_minuscula if k.startswith(prefijo))
    if not variantes:
        return None
    genericas = [k for k in variantes if "generic" in k]
    elegida = genericas[0] if genericas else variantes[0]
    return archivos_por_minuscula[elegida]


def buscar_en_vanilla(nombre_icono, indice_vanilla):
    """Mismas reglas que link_icons.py, contra icon_index.json vanilla."""
    candidato = indice_vanilla.get(f"Item_{nombre_icono}") or indice_vanilla.get(nombre_icono)
    if candidato:
        return candidato["file"]

    prefijo = f"Item_{nombre_icono}_"
    variantes = [k for k in indice_vanilla if k.startswith(prefijo)]
    if not variantes:
        return None
    genericas = [k for k in variantes if "generic" in k.lower()]
    elegida = genericas[0] if genericas else sorted(variantes)[0]
    return indice_vanilla[elegida]["file"]


def main():
    if len(sys.argv) < 3:
        print(f"Uso: {sys.argv[0]} <items_mods.json> <carpeta_icons_mods> [icon_index_vanilla.json]")
        sys.exit(1)

    ruta_items = Path(sys.argv[1])
    carpeta_icons = Path(sys.argv[2])
    indice_vanilla = cargar_json(Path(sys.argv[3])) if len(sys.argv) > 3 else {}

    items = cargar_json(ruta_items)
    archivos_por_minuscula = {p.name.lower(): p.name for p in carpeta_icons.glob("*.png")}

    de_mod = 0
    de_vanilla = 0
    sin_icono = 0
    no_encontrados = 0

    for item in items:
        nombre_icono = obtener_nombre_icono(item)
        if not nombre_icono:
            item["_icon_file"] = None
            sin_icono += 1
            continue

        archivo = buscar_en_mods(nombre_icono, archivos_por_minuscula)
        if archivo:
            item["_icon_file"] = archivo
            de_mod += 1
            continue

        archivo = buscar_en_vanilla(nombre_icono, indice_vanilla)
        if archivo:
            item["_icon_file"] = archivo
            de_vanilla += 1
        else:
            item["_icon_file"] = None
            no_encontrados += 1

    guardar_json(ruta_items, items)

    print(f"Icono propio del mod: {de_mod}")
    print(f"Icono vanilla reutilizado por el mod: {de_vanilla}")
    print(f"Sin icono (campo ausente o 'na'): {sin_icono}")
    print(f"Con nombre de icono pero sin archivo encontrado: {no_encontrados}")
    print(f"Guardado: {ruta_items}")


if __name__ == "__main__":
    main()