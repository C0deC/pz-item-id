"""
Enlaza cada item de data/items.json con su archivo de icono real,
usando el mapa generado por extract_packs.py (data/icon_index.json).

El campo Icon= de los scripts guarda un nombre "limpio" (ej. Trousers),
mientras que el atlas de UI2.pack indexa sus entradas con el prefijo
Item_ (ej. Item_Trousers_BrownLeather). Además, algunos items con
variantes (ropa de distintos colores/materiales) no tienen un icono
genérico exacto, solo variantes concretas -- en ese caso cogemos la
primera variante disponible, priorizando la que contenga "Generic".

Las armas no usan el campo Icon=, sino IconsForTexture= (con posibles
varias variantes separadas por ';', ej. "Hammer;Hammer_Forged") -- se
prueba primero Icon y, si no existe, se cae a IconsForTexture.

Añade a cada item el campo _icon_file con el nombre del archivo dentro
de data/icons/, o None si no se encuentra ninguna coincidencia.

Salida: sobrescribe data/items.json con el campo añadido.
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
    """Algunos campos pueden venir como lista si la clave se repetía en el script."""
    return valor[0] if isinstance(valor, list) else valor


def obtener_nombre_icono(item):
    """Devuelve el nombre de icono a buscar, probando los campos que hemos
    visto usar según el tipo de item:
    - Icon: el campo normal para la mayoría de items.
    - IconsForTexture: usado por armas en su lugar; puede traer varios
      nombres separados por ';' (variantes), cogemos el primero."""
    icono = item.get("Icon")
    if icono:
        return primero(icono)

    iconos_textura = item.get("IconsForTexture")
    if iconos_textura:
        iconos_textura = primero(iconos_textura)
        return iconos_textura.split(";")[0].strip()

    return None


def buscar_icono(nombre_icono, indice_iconos):
    """Busca el icono de un item probando, en orden:
    1. Coincidencia exacta con prefijo Item_
    2. Coincidencia exacta sin prefijo (por si acaso)
    3. Cualquier variante que empiece por Item_{nombre}_ (ej. ropa con colores),
       priorizando la que contenga 'Generic' si existe.
    Devuelve el nombre de archivo (o None si no se encuentra nada)."""
    candidato = indice_iconos.get(f"Item_{nombre_icono}") or indice_iconos.get(nombre_icono)
    if candidato:
        return candidato["file"]

    prefijo = f"Item_{nombre_icono}_"
    variantes = [k for k in indice_iconos if k.startswith(prefijo)]
    if not variantes:
        return None

    genericas = [k for k in variantes if "generic" in k.lower()]
    elegida = genericas[0] if genericas else sorted(variantes)[0]
    return indice_iconos[elegida]["file"]


def main():
    if len(sys.argv) < 4:
        print(f"Uso: {sys.argv[0]} <items.json> <icon_index.json> <carpeta_icons>")
        sys.exit(1)

    ruta_items = Path(sys.argv[1])
    ruta_indice = Path(sys.argv[2])
    carpeta_icons = Path(sys.argv[3])  # no se usa directamente aquí, pero se
                                        # recibe para mantener la misma firma
                                        # que el resto de scripts del pipeline

    items = cargar_json(ruta_items)
    indice_iconos = cargar_json(ruta_indice)

    encontrados = 0
    sin_icono = 0
    no_encontrados = 0

    for item in items:
        nombre_icono = obtener_nombre_icono(item)
        if not nombre_icono:
            item["_icon_file"] = None
            sin_icono += 1
            continue

        archivo_icono = buscar_icono(nombre_icono, indice_iconos)

        if archivo_icono:
            item["_icon_file"] = archivo_icono
            encontrados += 1
        else:
            item["_icon_file"] = None
            no_encontrados += 1

    guardar_json(ruta_items, items)

    print(f"Items con icono enlazado: {encontrados}")
    print(f"Items sin campo Icon/IconsForTexture en el script: {sin_icono}")
    print(f"Items con Icon/IconsForTexture pero sin coincidencia en el índice: {no_encontrados}")
    print(f"Guardado: {ruta_items}")


if __name__ == "__main__":
    main()