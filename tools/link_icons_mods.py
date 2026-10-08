"""
Enlaza cada item de data/items_mods.json con su icono real en
data/icons_mods/ (PNG sueltos, no vienen de un .pack como los vanilla).

A diferencia de link_icons.py (que consulta un icon_index.json generado
por extract_packs.py), aquí se comprueba directamente la existencia del
archivo en disco, con las mismas reglas de nombre que ya conocemos:
prefijo Item_, y fallback a variantes Item_{nombre}_* si no hay coincidencia
exacta.

Salida: sobrescribe data/items_mods.json con el campo _icon_file añadido.
"""

import json
import sys
from pathlib import Path


def cargar_json(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_json(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)


def primero(valor):
    return valor[0] if isinstance(valor, list) else valor


def obtener_nombre_icono(item):
    icono = item.get("Icon")
    if icono:
        return primero(icono)
    iconos_textura = item.get("IconsForTexture")
    if iconos_textura:
        return primero(iconos_textura).split(";")[0].strip()
    return None


def buscar_icono_en_carpeta(nombre_icono, archivos_disponibles):
    """archivos_disponibles: set con los nombres de archivo (sin ruta) ya
    existentes en data/icons_mods/, para no golpear el disco por cada item."""
    candidato = f"Item_{nombre_icono}.png"
    if candidato in archivos_disponibles:
        return candidato
    if f"{nombre_icono}.png" in archivos_disponibles:
        return f"{nombre_icono}.png"

    prefijo = f"Item_{nombre_icono}_"
    variantes = sorted(a for a in archivos_disponibles if a.startswith(prefijo))
    if not variantes:
        return None
    genericas = [a for a in variantes if "generic" in a.lower()]
    return genericas[0] if genericas else variantes[0]


def main():
    if len(sys.argv) < 3:
        print(f"Uso: {sys.argv[0]} <items_mods.json> <carpeta_icons_mods>")
        sys.exit(1)

    ruta_items = Path(sys.argv[1])
    carpeta_icons = Path(sys.argv[2])

    items = cargar_json(ruta_items)
    archivos_disponibles = {p.name for p in carpeta_icons.glob("*.png")}

    encontrados = 0
    sin_icono = 0
    no_encontrados = 0

    for item in items:
        nombre_icono = obtener_nombre_icono(item)
        if not nombre_icono:
            item["_icon_file"] = None
            sin_icono += 1
            continue

        archivo = buscar_icono_en_carpeta(nombre_icono, archivos_disponibles)
        if archivo:
            item["_icon_file"] = archivo
            encontrados += 1
        else:
            item["_icon_file"] = None
            no_encontrados += 1

    guardar_json(ruta_items, items)

    print(f"Items de mods con icono enlazado: {encontrados}")
    print(f"Items sin campo Icon/IconsForTexture: {sin_icono}")
    print(f"Items con Icon/IconsForTexture pero sin archivo encontrado: {no_encontrados}")
    print(f"Guardado: {ruta_items}")


if __name__ == "__main__":
    main()