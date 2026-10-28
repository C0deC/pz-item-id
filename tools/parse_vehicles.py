"""
Extrae los vehículos de Project Zomboid (vanilla y mods de Workshop) a un
único data/vehicles.json.

- ID: Módulo.NombreDelScript (ej. Base.70barracuda), a partir de los
  bloques `vehicle Nombre { ... }` de media/scripts.
- Plantillas: también se leen los bloques `template vehicle Nombre { ... }`,
  pero solo como fuente de datos heredables; no aparecen en la lista final.
- Herencia: muchas variantes (rotuladas, "expanded"...) declaran
  `template! = OtroVehiculo` y no repiten el motor, la masa, etc. Las
  estadísticas que les faltan se toman del vehículo (o plantilla) del que
  heredan, encadenando si ese a su vez hereda de otro.
- Nombre legible: no está en el script, sino en las traducciones, con la
  clave IGUI_VehicleName<NombreDelScript>. Se aceptan dos formatos:
      JSON:  "IGUI_VehicleNameCarLights": "Chevalier Nyala",
      TXT:   IGUI_VehicleNameCarLights = "Chevalier Nyala"
  Se leen todos los .json y .txt de cada carpeta de idioma, sin asumir el
  nombre del archivo.
- Idiomas: inglés (nombre principal) y los mismos 10 soportados para items.
- Estadísticas ("stats"): mass, engineForce, engineQuality, engineLoudness,
  maxSpeed y seats, leídas SOLO del nivel superior del vehículo (se ignoran
  los bloques anidados: model, skin, wheel, part...). Son valores internos
  del juego, sin unidades reales.
- Imagen: para los vehículos de mods se copia el preview.png del mod (el
  indicado en 'poster=' de mod.info) a data/vehicle_previews/, reducido a
  un máximo de 512 px. Es la portada del mod, no una foto de cada vehículo.
  Los vehículos vanilla no tienen imagen.
- Se excluyen las variantes no funcionales (coches quemados o destruidos):
  cualquier nombre de script que contenga "burnt" o "smashed".

Uso:
    python tools/parse_vehicles.py <media_vanilla> <workshop_content_108600> <salida.json>
"""

import json
import re
import sys
from pathlib import Path

from PIL import Image

# Grupo 1: prefijo 'template' (si lo hay). Grupo 2: nombre del script.
VEHICLE_RE = re.compile(r"^[ \t]*(template[ \t]+)?vehicle[ \t]+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)
MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)
NOMBRE_RE = re.compile(r'^\s*"?IGUI_VehicleName([A-Za-z0-9_]+)"?\s*[=:]\s*"?(.*?)"?\s*,?\s*$')
VERSION_DIR_RE = re.compile(r"^\d+(\.\d+)*$")

IDIOMAS = {"EN", "ES", "ES_CL", "ES_MX", "FR", "DE", "IT", "PT", "RU", "PL", "NL"}

# Variantes no funcionales (coches quemados o destruidos): no se pueden
# conducir, así que no se incluyen. Se busca en cualquier parte del nombre,
# sin distinguir mayúsculas (ej. NormalCarBurntPolice).
MARCAS_NO_FUNCIONALES = ("burnt", "smashed")

# Solo para el diagnóstico final: sufijos que ya excluía la primera versión.
SUFIJOS_ANTIGUOS = ("Burnt", "SmashedFront", "SmashedRear", "SmashedLeft", "SmashedRight")

# Propiedades del nivel superior del vehículo que se guardan en "stats".
CAMPOS_ESTADISTICAS = ("mass", "engineForce", "engineQuality", "engineLoudness", "maxSpeed", "seats")

TAMANO_MAX_PREVIEW = 512


def es_no_funcional(nombre):
    n = nombre.lower()
    return any(marca in n for marca in MARCAS_NO_FUNCIONALES)


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


def propiedades_nivel_superior(cuerpo):
    """Devuelve {clave: valor} de las líneas 'clave = valor' que están
    directamente dentro del vehículo, ignorando el contenido de los bloques
    anidados (model, skin, wheel, part...). Una clave repetida (por ejemplo
    varios 'template = ...') conserva el último valor; 'template!' es una
    clave distinta y se conserva aparte."""
    texto = []
    profundidad = 0
    for c in cuerpo:
        if c == "{":
            profundidad += 1
        elif c == "}":
            profundidad -= 1
        elif profundidad == 0:
            texto.append(c)

    props = {}
    for linea in "".join(texto).split("\n"):
        linea = linea.strip().rstrip(",").strip()
        if "=" in linea:
            clave, _, valor = linea.partition("=")
            props[clave.strip()] = valor.strip()
    return props


def a_numero(valor):
    """Convierte '120.0' en 120 y '0.8' en 0.8. Devuelve None si no es un número."""
    try:
        n = float(valor.strip().rstrip("fF"))
    except ValueError:
        return None
    return int(n) if n == int(n) else n


def vehiculos_de_archivo(ruta):
    """Devuelve una lista de (modulo, nombre_script, propiedades, es_plantilla)."""
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
            props = propiedades_nivel_superior(cuerpo[m.end():cierra_v])
            encontrados.append((modulo, m.group(2), props, m.group(1) is not None))
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


def copiar_preview(carpeta_mod, carpeta_version, carpeta_common, poster, carpeta_previews):
    """Copia el preview del mod a carpeta_previews, reducido, y devuelve el
    nombre del archivo creado (o None si no se encuentra o no se puede leer).
    El nombre lleva el ID de Workshop para que no choque entre mods."""
    nombre = f"{carpeta_mod.parent.parent.name}_{carpeta_mod.name}"
    nombre = re.sub(r"[^A-Za-z0-9_.-]", "_", nombre) + ".png"
    destino = carpeta_previews / nombre
    if destino.exists():
        return nombre

    posters = [poster] if poster == "preview.png" else [poster, "preview.png"]
    for base in (carpeta_version, carpeta_mod, carpeta_common):
        if not base:
            continue
        for p in posters:
            origen = base / p
            if not origen.is_file():
                continue
            try:
                with Image.open(origen) as img:
                    img = img.convert("RGBA")
                    img.thumbnail((TAMANO_MAX_PREVIEW, TAMANO_MAX_PREVIEW))
                    carpeta_previews.mkdir(parents=True, exist_ok=True)
                    img.save(destino, "PNG")
                return nombre
            except Exception:
                continue
    return None


def construir_entradas(pares, nombres, origen, nombre_origen, archivo):
    entradas = []
    for modulo, nombre_script, props, es_plantilla in pares:
        por_idioma = nombres.get(nombre_script, {})

        stats = {}
        for campo in CAMPOS_ESTADISTICAS:
            if campo in props:
                numero = a_numero(props[campo])
                if numero is not None:
                    stats[campo] = numero

        entradas.append({
            "_name": nombre_script,
            "_module": modulo,
            "_full_id": f"{modulo}.{nombre_script}",
            "_source": origen,
            "_source_name": nombre_origen,
            "_source_file": archivo,
            "_preview": None,
            "_plantilla": es_plantilla,
            "_hereda_de": props.get("template!"),
            "DisplayName": por_idioma.get("EN"),
            "_translations": {i: n for i, n in por_idioma.items() if i != "EN"},
            "stats": stats,
        })
    return entradas


def resolver_herencia(entradas):
    """Rellena las estadísticas que faltan con las del vehículo (o plantilla)
    del que se hereda mediante 'template! = Nombre'. Lo que el vehículo define
    por sí mismo tiene prioridad sobre lo heredado.
    Devuelve (vehiculos_que_ganan_engineForce, referencias_sin_resolver)."""
    vehiculos = {e["_full_id"]: e for e in entradas if not e["_plantilla"]}
    plantillas = {e["_full_id"]: e for e in entradas if e["_plantilla"]}

    def buscar_padre(e):
        ref = e["_hereda_de"]
        id_padre = ref if "." in ref else f"{e['_module']}.{ref}"
        return vehiculos.get(id_padre) or plantillas.get(id_padre)

    def stats_completas(e, visitados):
        stats = dict(e["stats"])
        if not e["_hereda_de"] or e["_full_id"] in visitados:
            return stats
        padre = buscar_padre(e)
        if padre is None or padre is e:
            return stats
        for campo, valor in stats_completas(padre, visitados | {e["_full_id"]}).items():
            stats.setdefault(campo, valor)
        return stats

    ganan_motor = 0
    sin_resolver = []
    for e in entradas:
        if not e["_hereda_de"]:
            continue
        if buscar_padre(e) is None:
            if not e["_plantilla"]:
                sin_resolver.append((e["_full_id"], e["_hereda_de"]))
            continue
        tenia_motor = "engineForce" in e["stats"]
        e["stats"] = stats_completas(e, set())
        if not tenia_motor and "engineForce" in e["stats"]:
            ganan_motor += 1
    return ganan_motor, sin_resolver


def procesar_vanilla(carpeta_media):
    nombres = leer_nombres(carpeta_media / "lua" / "shared")
    entradas = []
    for archivo in sorted((carpeta_media / "scripts").rglob("*.txt")):
        pares = vehiculos_de_archivo(archivo)
        entradas.extend(construir_entradas(pares, nombres, "vanilla", None, archivo.name))
    return entradas


def procesar_mod(carpeta_mod, carpeta_previews):
    carpeta_version = elegir_carpeta_version(carpeta_mod)
    carpeta_common = carpeta_mod / "common"
    carpeta_common = carpeta_common if carpeta_common.exists() else None

    # Carpetas donde buscar scripts: la versión más reciente y common/.
    # Si el mod no tiene ninguna, se usa la propia carpeta del mod.
    raices = [d for d in (carpeta_version, carpeta_common) if d]
    if not raices:
        raices = [carpeta_mod]

    info = {}
    for candidata in [carpeta_version, carpeta_mod]:
        if candidata and (candidata / "mod.info").exists():
            info = leer_mod_info(candidata / "mod.info")
            break
    nombre_mod = info.get("name", carpeta_mod.name)
    poster = info.get("poster", "preview.png")

    nombres = leer_nombres(carpeta_mod)

    entradas = []
    for raiz in raices:
        carpeta_scripts = raiz / "media" / "scripts"
        if not carpeta_scripts.exists():
            continue
        for archivo in sorted(carpeta_scripts.rglob("*.txt")):
            pares = vehiculos_de_archivo(archivo)
            entradas.extend(construir_entradas(pares, nombres, carpeta_mod.name, nombre_mod, archivo.name))

    if any(not e["_plantilla"] for e in entradas):
        preview = copiar_preview(carpeta_mod, carpeta_version, carpeta_common, poster, carpeta_previews)
        for e in entradas:
            e["_preview"] = preview
    return entradas


def main():
    if len(sys.argv) < 4:
        print(f"Uso: {sys.argv[0]} <media_vanilla> <workshop_content_108600> <salida.json>")
        sys.exit(1)

    carpeta_media = Path(sys.argv[1])
    carpeta_content = Path(sys.argv[2])
    ruta_salida = Path(sys.argv[3])
    carpeta_previews = ruta_salida.parent / "vehicle_previews"

    todos = procesar_vanilla(carpeta_media)

    mods_con_vehiculos = 0
    for carpeta_workshop in sorted(p for p in carpeta_content.iterdir() if p.is_dir()):
        carpeta_mods = carpeta_workshop / "mods"
        if not carpeta_mods.exists():
            continue
        for carpeta_mod in sorted(p for p in carpeta_mods.iterdir() if p.is_dir()):
            entradas = procesar_mod(carpeta_mod, carpeta_previews)
            if any(not e["_plantilla"] for e in entradas):
                mods_con_vehiculos += 1
            todos.extend(entradas)

    # Si un mismo ID aparece varias veces (versiones repetidas, o un mod que
    # redefine uno vanilla) se queda la primera aparición, vanilla primero.
    vistos = set()
    unicos = []
    for e in todos:
        clave = (e["_full_id"], e["_plantilla"])
        if clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(e)
    duplicados = len(todos) - len(unicos)

    # La herencia se resuelve antes de descartar nada, por si un vehículo
    # hereda de otro que luego se excluye.
    ganan_motor, sin_resolver = resolver_herencia(unicos)

    n_plantillas = sum(1 for e in unicos if e["_plantilla"])
    candidatos = [e for e in unicos if not e["_plantilla"]]

    # Se descartan las variantes no funcionales (quemados / destruidos).
    excluidos_lista = [v for v in candidatos if es_no_funcional(v["_name"])]
    vehiculos = [v for v in candidatos if not es_no_funcional(v["_name"])]
    solo_regla_ampliada = [
        v["_full_id"] for v in excluidos_lista if not v["_name"].endswith(SUFIJOS_ANTIGUOS)
    ]

    for v in vehiculos:
        v.pop("_plantilla", None)
        v.pop("_hereda_de", None)

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(vehiculos, f, indent=2, ensure_ascii=False)

    n_vanilla = sum(1 for v in vehiculos if v["_source"] == "vanilla")
    sin_nombre = [v for v in vehiculos if not v["DisplayName"]]
    sin_motor = [v for v in vehiculos if "engineForce" not in v["stats"]]
    de_mods = [v for v in vehiculos if v["_source"] != "vanilla"]
    con_preview = [v for v in de_mods if v["_preview"]]

    print(f"Vehículos vanilla: {n_vanilla}")
    print(f"Mods con vehículos: {mods_con_vehiculos}")
    print(f"Total de vehículos únicos: {len(vehiculos)} ({duplicados} duplicados descartados)")
    print(f"Plantillas leídas (solo como fuente de datos): {n_plantillas}")
    print(f"Excluidos por no funcionales: {len(excluidos_lista)}")
    print(f"  Excluidos solo por la regla ampliada: {len(solo_regla_ampliada)}")
    print(f"Con nombre en inglés: {len(vehiculos) - len(sin_nombre)}")
    print(f"Sin nombre en inglés: {len(sin_nombre)}")
    print(f"Herencia 'template!': {ganan_motor} vehículos ganan engineForce")
    print(f"  Referencias 'template!' sin resolver: {len(sin_resolver)}")
    print("  Ejemplos:", sin_resolver[:8])
    print("Cobertura de estadísticas:")
    for campo in CAMPOS_ESTADISTICAS:
        n = sum(1 for v in vehiculos if campo in v["stats"])
        print(f"  {campo}: {n} de {len(vehiculos)}")
    print(f"Sin engineForce: {len(sin_motor)}")
    print("  Ejemplos:", [(v["_full_id"], v["_source_file"]) for v in sin_motor[:8]])
    print(f"Vehículos de mods con imagen de preview: {len(con_preview)} de {len(de_mods)}")
    print(f"Guardado: {ruta_salida}")


if __name__ == "__main__":
    main()