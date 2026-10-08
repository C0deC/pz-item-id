"""
Extrae los vehículos de Project Zomboid (vanilla y mods de Workshop) a un
único data/vehicles.json.

- ID: Módulo.NombreDelScript (ej. Base.70barracuda), a partir de los
  bloques `vehicle Nombre { ... }` de media/scripts. Los bloques
  `template vehicle ...` no empiezan la línea por "vehicle", así que se
  ignoran (son plantillas, no vehículos que se puedan generar).
- Nombre legible: no está en el script, sino en las traducciones, con la
  clave IGUI_VehicleName<NombreDelScript>. Se aceptan dos formatos:
      JSON:  "IGUI_VehicleNameCarLights": "Chevalier Nyala",
      TXT:   IGUI_VehicleNameCarLights = "Chevalier Nyala"
  Se leen todos los .json y .txt de cada carpeta de idioma, sin asumir el
  nombre del archivo.
- Idiomas: inglés (nombre principal) y los mismos 10 soportados para items.

Uso:
    python tools/parse_vehicles.py <media_vanilla> <workshop_content_108600> <salida.json>
"""

import json
import re
import sys
from pathlib import Path

VEHICLE_RE = re.compile(r"^[ \t]*vehicle[ \t]+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)
MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)
NOMBRE_RE = re.compile(r'^\s*"?IGUI_VehicleName([A-Za-z0-9_]+)"?\s*[=:]\s*"?(.*?)"?\s*,?\s*$')
VERSION_DIR_RE = re.compile(r"^\d+(\.\d+)*$")

IDIOMAS = {"EN", "ES", "ES_CL", "ES_MX", "FR", "DE", "IT", "PT", "RU", "PL", "NL"}


def quitar_comentarios(texto):
    return "\n".join(linea.split("//")[0] for linea in texto.split("\n"))


def buscar_cierre(texto, indice_apertura):
    """Devuelve el índice de la '}' que cierra la '{' dada, contando anidados."""
    profundidad = 0
    for i in range(indice_apertura, len(texto)):
        if texto[i] == "{":
            profundidad += 1
        elif texto[i] == "}":
            profundidad -= 1
            if profundidad == 0:
                return i
    return -1


def vehiculos_de_archivo(ruta):
    """Devuelve una lista de (modulo, nombre_script) de un archivo de script."""
    texto = quitar_comentarios(ruta.read_text(encoding="utf-8", errors="replace"))
    encontrados = []

    for m_modulo in MODULE_RE.finditer(texto):
        modulo = m_modulo.group(1)
        abre = m_modulo.end() - 1
        cierra = buscar_cierre(texto, abre)
        if cierra < 0:
            continue
        cuerpo = texto[abre + 1:cierra]

        pos = 0
        while True:
            m = VEHICLE_RE.search(cuerpo, pos)
            if not m:
                break
            cierra_v = buscar_cierre(cuerpo, m.end() - 1)
            if cierra_v < 0:
                break
            encontrados.append((modulo, m.group(1)))
            pos = cierra_v + 1  # salta el contenido del vehículo (partes, modelos...)

    return encontrados


def leer_nombres(raiz):
    """Busca cualquier carpeta 'Translate' (sin importar mayúsculas) bajo raiz
    y devuelve {nombre_script: {IDIOMA: nombre}} con los IGUI_VehicleName."""
    nombres = {}
    if not raiz.exists():
        return nombres

    carpetas = sorted(p for p in raiz.rglob("*") if p.is_dir() and p.name.lower() == "translate")
    for carpeta in carpetas:
        for carpeta_idioma in sorted(carpeta.iterdir()):
            if not carpeta_idioma.is_dir():
                continue
            idioma = carpeta_idioma.name.upper()
            if idioma not in IDIOMAS:
                continue
            for archivo in sorted(carpeta_idioma.iterdir()):
                if not archivo.is_file() or archivo.suffix.lower() not in (".json", ".txt"):
                    continue
                texto = archivo.read_text(encoding="utf-8-sig", errors="replace")
                for linea in texto.splitlines():
                    m = NOMBRE_RE.match(linea)
                    if m:
                        valor = m.group(2).replace('\\"', '"').strip()
                        if valor:
                            nombres.setdefault(m.group(1), {})[idioma] = valor
    return nombres


def elegir_carpeta_version(carpeta_mod):
    candidatas = [d for d in carpeta_mod.iterdir() if d.is_dir() and VERSION_DIR_RE.match(d.name)]
    if not candidatas:
        return None
    return max(candidatas, key=lambda d: tuple(int(p) for p in d.name.split(".")))


def leer_mod_info(ruta):
    info = {}
    for linea in ruta.read_text(encoding="utf-8", errors="replace").split("\n"):
        if "=" in linea:
            clave, _, valor = linea.partition("=")
            info[clave.strip()] = valor.strip().strip("'").strip('"')
    return info


def construir_entradas(pares, nombres, origen, nombre_origen, archivo):
    entradas = []
    for modulo, nombre_script in pares:
        por_idioma = nombres.get(nombre_script, {})
        entradas.append({
            "_name": nombre_script,
            "_module": modulo,
            "_full_id": f"{modulo}.{nombre_script}",
            "_source": origen,
            "_source_name": nombre_origen,
            "_source_file": archivo,
            "DisplayName": por_idioma.get("EN"),
            "_translations": {i: n for i, n in por_idioma.items() if i != "EN"},
        })
    return entradas


def procesar_vanilla(carpeta_media):
    nombres = leer_nombres(carpeta_media / "lua" / "shared")
    entradas = []
    for archivo in sorted((carpeta_media / "scripts").rglob("*.txt")):
        pares = vehiculos_de_archivo(archivo)
        entradas.extend(construir_entradas(pares, nombres, "vanilla", None, archivo.name))
    return entradas


def procesar_mod(carpeta_mod):
    carpeta_version = elegir_carpeta_version(carpeta_mod)
    carpeta_common = carpeta_mod / "common"

    # Carpetas donde buscar scripts: la versión más reciente y common/.
    # Si el mod no tiene ninguna, se usa la propia carpeta del mod.
    raices = [d for d in (carpeta_version, carpeta_common) if d and d.exists()]
    if not raices:
        raices = [carpeta_mod]

    nombre_mod = carpeta_mod.name
    for candidata in [carpeta_version, carpeta_mod]:
        if candidata and (candidata / "mod.info").exists():
            info = leer_mod_info(candidata / "mod.info")
            nombre_mod = info.get("name", nombre_mod)
            break

    nombres = leer_nombres(carpeta_mod)

    entradas = []
    for raiz in raices:
        carpeta_scripts = raiz / "media" / "scripts"
        if not carpeta_scripts.exists():
            continue
        for archivo in sorted(carpeta_scripts.rglob("*.txt")):
            pares = vehiculos_de_archivo(archivo)
            entradas.extend(construir_entradas(pares, nombres, carpeta_mod.name, nombre_mod, archivo.name))
    return entradas


def main():
    if len(sys.argv) < 4:
        print(f"Uso: {sys.argv[0]} <media_vanilla> <workshop_content_108600> <salida.json>")
        sys.exit(1)

    carpeta_media = Path(sys.argv[1])
    carpeta_content = Path(sys.argv[2])
    ruta_salida = Path(sys.argv[3])

    todos = procesar_vanilla(carpeta_media)
    n_vanilla = len(todos)

    mods_con_vehiculos = 0
    for carpeta_workshop in sorted(p for p in carpeta_content.iterdir() if p.is_dir()):
        carpeta_mods = carpeta_workshop / "mods"
        if not carpeta_mods.exists():
            continue
        for carpeta_mod in sorted(p for p in carpeta_mods.iterdir() if p.is_dir()):
            entradas = procesar_mod(carpeta_mod)
            if entradas:
                mods_con_vehiculos += 1
                todos.extend(entradas)

    # Si un mismo ID aparece varias veces (versiones repetidas, o un mod que
    # redefine uno vanilla) se queda la primera aparición, vanilla primero.
    vistos = set()
    unicos = []
    for v in todos:
        if v["_full_id"] in vistos:
            continue
        vistos.add(v["_full_id"])
        unicos.append(v)
    duplicados = len(todos) - len(unicos)

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(unicos, f, indent=2, ensure_ascii=False)

    sin_nombre = [v for v in unicos if not v["DisplayName"]]
    posibles_plantillas = [v for v in unicos if "template" in v["_name"].lower()]

    print(f"Vehículos vanilla: {n_vanilla}")
    print(f"Mods con vehículos: {mods_con_vehiculos}")
    print(f"Total de vehículos únicos: {len(unicos)} ({duplicados} duplicados descartados)")
    print(f"Con nombre en inglés: {len(unicos) - len(sin_nombre)}")
    print(f"Sin nombre en inglés: {len(sin_nombre)}")
    print("  Ejemplos sin nombre:", [v["_full_id"] for v in sin_nombre[:8]])
    print(f"Nombres que contienen 'template': {len(posibles_plantillas)}")
    print("  Ejemplos:", [v["_full_id"] for v in posibles_plantillas[:5]])
    print(f"Guardado: {ruta_salida}")


if __name__ == "__main__":
    main()