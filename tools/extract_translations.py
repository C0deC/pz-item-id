"""
Extrae las traducciones de nombres de items desde
media/lua/shared/Translate/<IDIOMA>/ItemName.json para cada idioma indicado.

Cada archivo ItemName.json tiene la forma:
    { "Base.Hammer": "Martillo", "Base.Acorn": "Bellota", ... }

Es decir, la clave ya coincide con el _full_id que genera parse_items.py,
así que no hace falta cruzar por nombre interno.

Salida: data/translations.json con la forma:
    { "Base.Hammer": {"ES": "Martillo", "FR": "Marteau", ...}, ... }
"""

import json
import sys
from pathlib import Path

# Códigos de carpeta tal como aparecen en Translate/, y el código corto
# que queremos usar como clave en la salida.
IDIOMAS = {
    "ES": "ES",
    "ES_CL": "ES_CL",
    "ES_MX": "ES_MX",
    "FR": "FR",
    "DE": "DE",
    "IT": "IT",
    "PT": "PT",
    "RU": "RU",
    "PL": "PL",
    "NL": "NL",
}


def main():
    if len(sys.argv) < 3:
        print(f"Uso: {sys.argv[0]} <carpeta_Translate> <salida_json>")
        sys.exit(1)

    carpeta_translate = Path(sys.argv[1])
    ruta_salida = Path(sys.argv[2])

    traducciones = {}  # full_id -> {idioma: nombre_traducido}

    for carpeta_idioma, codigo_salida in IDIOMAS.items():
        ruta_archivo = carpeta_translate / carpeta_idioma / "ItemName.json"

        if not ruta_archivo.exists():
            print(f"  {carpeta_idioma}: no encontrado en {ruta_archivo}, se omite")
            continue

        with open(ruta_archivo, "r", encoding="utf-8") as f:
            datos_idioma = json.load(f)

        for full_id, nombre_traducido in datos_idioma.items():
            traducciones.setdefault(full_id, {})[codigo_salida] = nombre_traducido

        print(f"  {carpeta_idioma}: {len(datos_idioma)} nombres cargados")

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(traducciones, f, indent=2, ensure_ascii=False)

    print(f"\nTotal de items con al menos una traducción: {len(traducciones)}")
    print(f"Guardado: {ruta_salida}")


if __name__ == "__main__":
    main()