"""
Extrae todas las sub-texturas de los archivos .pack de Project Zomboid.

Adaptado del script extract_packs.py del repositorio pz-item-browser
(GitHub: KevinLinTW1021/pz-item-browser).

Formato (verificado a partir de GameWindow.java:805 + TexturePackPage.java:158):
    Archivo = num_paginas(i32) | pagina x num_paginas
    pagina = nombre(string) | num_subtexturas(i32) | tiene_alpha(i32)
            | info_subtextura x num_subtexturas
            | atlas (bytes PNG en crudo)
            | terminador 0xDEADBEEF (i32)
    info_subtextura = nombre(string) | x y w h ox oy fx fy (8 x i32)
    string = longitud(i32) | bytes[longitud] (ASCII)

Todos los enteros son little-endian.
"""

import io
import json
import os
import struct
import sys
from pathlib import Path

from PIL import Image

TERMINADOR_PACK = 0xDEADBEEF
FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
COLA_PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def leer_i32(stream):
    """Lee 4 bytes y los interpreta como un entero de 32 bits con signo."""
    raw = stream.read(4)
    if len(raw) < 4:
        return None
    return struct.unpack("<i", raw)[0]


def leer_string(stream):
    """Lee una cadena con formato: longitud (i32) + bytes en ASCII."""
    n = leer_i32(stream)
    if n is None or n < 0 or n > 4096:
        raise ValueError(f"longitud de string inválida: {n}")
    return stream.read(n).decode("ascii", errors="replace")


def leer_png_hasta_iend(stream):
    """Lee un PNG completo buscando la marca de fin IEND, ya que no sabemos
    de antemano cuántos bytes ocupa (formato antiguo de .pack)."""
    firma = stream.read(8)
    if firma != FIRMA_PNG:
        raise ValueError(f"se esperaba firma PNG, se obtuvo {firma.hex()}")
    out = bytearray(firma)
    while True:
        trozo = stream.read(8192)
        if not trozo:
            raise ValueError("fin de archivo antes de encontrar IEND")
        out.extend(trozo)
        idx = out.rfind(COLA_PNG_IEND)
        if idx >= 0:
            fin_png = idx + len(COLA_PNG_IEND)
            extra = bytes(out[fin_png:])
            return bytes(out[:fin_png]), extra


def parsear_pack(ruta_pack):
    """Generador que va produciendo (nombre_pagina, imagen_atlas, subtexturas)
    por cada página encontrada dentro del archivo .pack."""
    with open(ruta_pack, "rb") as f:
        data = f.read()
    stream = io.BytesIO(data)

    # Los packs nuevos (UI2.pack, Tiles*.pack) empiezan con la marca 'PZPK'
    # + versión(i32), y luego num_paginas + páginas como el formato normal.
    # El formato nuevo también antepone la longitud al PNG del atlas, mientras
    # que el formato antiguo simplemente escribe los bytes del PNG en línea.
    cabecera = stream.read(4)
    if cabecera == b"PZPK":
        _version = leer_i32(stream)  # en la práctica siempre vale 1
        num_paginas = leer_i32(stream)
        formato_nuevo = True
    else:
        # Formato antiguo: el primer entero de 32 bits ES el num_paginas.
        stream.seek(0)
        num_paginas = leer_i32(stream)
        formato_nuevo = False
    if num_paginas is None or num_paginas < 0 or num_paginas > 100000:
        raise ValueError(f"num_paginas inválido: {num_paginas}")

    for indice_pagina in range(num_paginas):
        nombre_pagina = leer_string(stream)
        num_subtexturas = leer_i32(stream)
        _tiene_alpha = leer_i32(stream)
        if num_subtexturas is None or num_subtexturas < 0 or num_subtexturas > 1_000_000:
            raise ValueError(f"num_subtexturas inválido {num_subtexturas} en página {nombre_pagina!r}")

        subs = []
        for _ in range(num_subtexturas):
            nombre = leer_string(stream)
            enteros = struct.unpack("<8i", stream.read(32))
            x, y, w, h, ox, oy, fx, fy = enteros
            subs.append({"name": nombre, "x": x, "y": y, "w": w, "h": h,
                         "ox": ox, "oy": oy, "fx": fx, "fy": fy})

        if formato_nuevo:
            longitud_png = leer_i32(stream)
            if longitud_png is None or longitud_png <= 0 or longitud_png > 200_000_000:
                raise ValueError(f"longitud_png inválida {longitud_png} en página {nombre_pagina!r}")
            datos_png = stream.read(longitud_png)
            if not datos_png.startswith(FIRMA_PNG):
                raise ValueError(f"el atlas con longitud indicada no es PNG en {nombre_pagina!r}")
            # El formato nuevo no tiene terminador: las páginas van seguidas
            # una detrás de otra, y la última simplemente llega al final del archivo.
        else:
            datos_png, extra = leer_png_hasta_iend(stream)
            # Consume el terminador (puede que ya esté parcialmente en `extra`)
            buffer_term = bytearray(extra)
            while len(buffer_term) < 4:
                buffer_term.extend(stream.read(4 - len(buffer_term)))
            term = struct.unpack("<I", bytes(buffer_term[:4]))[0]
            sobrante = bytes(buffer_term[4:])
            if term != TERMINADOR_PACK:
                escaneo = sobrante + stream.read(64)
                idx = escaneo.find(struct.pack("<I", TERMINADOR_PACK))
                if idx < 0:
                    raise ValueError(
                        f"no se encontró DEADBEEF en página {indice_pagina} {nombre_pagina!r} (se obtuvo {term:08x})"
                    )
                consumido = len(escaneo) - (idx + 4)
                stream.seek(-consumido, os.SEEK_CUR)
            elif sobrante:
                stream.seek(-len(sobrante), os.SEEK_CUR)

        atlas = Image.open(io.BytesIO(datos_png))
        atlas.load()
        yield nombre_pagina, atlas, subs


def extraer_pack_a_carpeta(ruta_pack, carpeta_salida, indice):
    """Recorta cada subtextura de un .pack y la guarda como PNG individual,
    registrando su posición/offsets en el diccionario `indice`."""
    guardadas = 0
    for nombre_pagina, atlas, subs in parsear_pack(ruta_pack):
        for s in subs:
            if s["w"] <= 0 or s["h"] <= 0:
                continue
            recorte = atlas.crop((s["x"], s["y"], s["x"] + s["w"], s["y"] + s["h"]))
            nombre_seguro = s["name"].replace("/", "_").replace("\\", "_")
            ruta_salida = carpeta_salida / f"{nombre_seguro}.png"
            recorte.save(ruta_salida, "PNG")
            guardadas += 1
            indice[s["name"]] = {
                "file": ruta_salida.name,
                "page": nombre_pagina,
                "pack": ruta_pack.stem,
                "ox": s["ox"], "oy": s["oy"],
                "fx": s["fx"], "fy": s["fy"],
            }
    return guardadas


def main():
    if len(sys.argv) < 3:
        print(f"Uso: {sys.argv[0]} <carpeta_packs> <carpeta_salida>")
        sys.exit(1)
    carpeta_packs = Path(sys.argv[1])
    carpeta_salida = Path(sys.argv[2])
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    indice = {}
    total = 0
    archivos_pack = sorted(carpeta_packs.glob("*.pack"))
    print(f"Encontrados {len(archivos_pack)} archivos .pack")
    for pack in archivos_pack:
        try:
            n = extraer_pack_a_carpeta(pack, carpeta_salida, indice)
            print(f"  {pack.name}: {n} extraídas")
            total += n
        except Exception as e:
            print(f"  {pack.name}: FALLÓ -- {e!s}".encode("ascii", "replace").decode("ascii"))

    ruta_indice = carpeta_salida.parent / "icon_index.json"
    with open(ruta_indice, "w", encoding="utf-8") as f:
        json.dump(indice, f, indent=2, ensure_ascii=False)
    print(f"\nTotal extraídas: {total}")
    print(f"Índice: {ruta_indice} ({len(indice)} entradas)")


if __name__ == "__main__":
    main()