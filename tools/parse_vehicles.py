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
  heredan, encadenando si ese a su vez hereda de otro. Un vehículo puede
  llamarse igual que la plantilla de la que hereda (vehicle StepVan con
  template! = StepVan); en ese caso se usa la plantilla.
- Nombre legible: no está en el script, sino en las traducciones, con la
  clave IGUI_VehicleName<NombreDelScript>. Se aceptan dos formatos:
      JSON:  "IGUI_VehicleNameCarLights": "Chevalier Nyala",
      TXT:   IGUI_VehicleNameCarLights = "Chevalier Nyala"
  Se leen todos los .json y .txt de cada carpeta de idioma, sin asumir el
  nombre del archivo.
- Idiomas: inglés (nombre principal) y los mismos 10 soportados para items.
- Estadísticas ("stats"): mass, engineForce, engineQuality, engineLoudness,
  maxSpeed, seats y mechanicType, leídas SOLO del nivel superior del
  vehículo (se ignoran los bloques anidados: model, skin, wheel, part...).
  Son valores internos del juego, sin unidades reales.
- Contenedores ("contenedores"): para cada vehículo se leen sus piezas
  (`part Nombre { ... container { ... } }`), siguiendo las inclusiones de
  plantillas (`template = Trunk/part/TruckBed`), las sobrescrituras del
  propio vehículo (incluido el comodín `part Seat*`) y la herencia
  `template!`. La capacidad de cada contenedor sale de:
    1. un `capacity` escrito en su bloque container ("script"), o si no
    2. el MaxCapacity del item de la pieza ("item"): itemType + mechanicType
       del vehículo, por ejemplo Base.SmallTrunk + 3 -> Base.SmallTrunk3.
  No cuentan como almacenamiento: los contenedores de combustible o aire
  (los que tienen contentType, el depósito, los neumáticos y la batería) ni
  las piezas ficticias (sin capacidad y con itemType = nil: los mods
  desactivan así el TruckBed genérico y ponen su propio maletero).
  Necesita data/items.json y data/items_mods.json junto a la salida.
- Almacenamiento ("almacenamiento"): suma de los contenedores de
  almacenamiento con capacidad conocida, SIN el asiento del conductor
  (SeatFrontLeft), repartida en:
    maletero: piezas con "Trunk" en el nombre, TruckBed y TruckBedOpen
    asientos: piezas Seat*
    otros:    el resto (guantera, baca, soporte de armas, cajones...)
  "completo" es False si algún contenedor real no tiene capacidad
  resoluble (el total es entonces un mínimo).
- Imagen: para los vehículos de mods se copia el preview.png del mod (el
  indicado en 'poster=' de mod.info) a data/vehicle_previews/, reducido a
  un máximo de 512 px. Es la portada del mod, no una foto de cada vehículo.
  Los vehículos vanilla no tienen imagen.
- Se excluyen las variantes no funcionales (coches quemados o destruidos):
  cualquier nombre de script que contenga "burnt" o "smashed".
- Remolques: con REMOLQUES = False se excluyen; con REMOLQUES = True se
  incluyen. Se considera remolque al vehículo que (1) no tiene engineForce o
  asientos, (2) tiene un nombre de script que empieza por "Trailer", o
  (3) tiene un nombre en inglés que contiene "trailer".

Uso:
    python tools/parse_vehicles.py <media_vanilla> <workshop_content_108600> <salida.json>
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

# Grupo 1: prefijo 'template' (si lo hay). Grupo 2: nombre del script.
VEHICLE_RE = re.compile(r"^[ \t]*(template[ \t]+)?vehicle[ \t]+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)
MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)
NOMBRE_RE = re.compile(r'^\s*"?IGUI_VehicleName([A-Za-z0-9_]+)"?\s*[=:]\s*"?(.*?)"?\s*,?\s*$')
VERSION_DIR_RE = re.compile(r"^\d+(\.\d+)*$")

# Bloques dentro de un vehículo o plantilla.
PIEZA_RE = re.compile(r"^[ \t]*part[ \t]+([^\s{]+)\s*\{", re.MULTILINE)
CONTENEDOR_RE = re.compile(r"^[ \t]*container\s*\{", re.MULTILINE)
# 'template = X' o 'template = X/part/Pieza'. No casa con 'template! = X'.
INCLUSION_RE = re.compile(r"^[ \t]*template[ \t]*=[ \t]*([^\s,]+)", re.MULTILINE)

IDIOMAS = {"EN", "ES", "ES_CL", "ES_MX", "FR", "DE", "IT", "PT", "RU", "PL", "NL"}

# Variantes no funcionales (coches quemados o destruidos): no se pueden
# conducir, así que no se incluyen. Se busca en cualquier parte del nombre,
# sin distinguir mayúsculas (ej. NormalCarBurntPolice).
MARCAS_NO_FUNCIONALES = ("burnt", "smashed")

# Solo para el diagnóstico final: sufijos que ya excluía la primera versión.
SUFIJOS_ANTIGUOS = ("Burnt", "SmashedFront", "SmashedRear", "SmashedLeft", "SmashedRight")

# Remolques: True = incluirlos en la lista, False = excluirlos.
REMOLQUES = False

# Piezas con contenedor que no guardan objetos (combustible, aire, batería).
PIEZAS_NO_ALMACENAMIENTO = ("GasTank", "Tire", "Battery")

# Pieza del asiento del conductor: no se cuenta, porque si se llena de
# objetos el jugador no puede entrar al vehículo.
ASIENTO_CONDUCTOR = "SeatFrontLeft"

# Propiedades del nivel superior del vehículo que se guardan en "stats".
CAMPOS_ESTADISTICAS = (
    "mass", "engineForce", "engineQuality", "engineLoudness", "maxSpeed", "seats", "mechanicType",
)

TAMANO_MAX_PREVIEW = 512


def es_no_funcional(nombre):
    n = nombre.lower()
    return any(marca in n for marca in MARCAS_NO_FUNCIONALES)


def motivo_remolque(vehiculo):
    """Devuelve el motivo por el que se considera remolque, o None si no lo es."""
    stats = vehiculo["stats"]
    if not stats.get("engineForce") or not stats.get("seats"):
        return "sin motor o sin asientos"
    if vehiculo["_name"].lower().startswith("trailer"):
        return "nombre de script empieza por Trailer"
    if "trailer" in (vehiculo.get("DisplayName") or "").lower():
        return "nombre en inglés contiene 'trailer'"
    return None


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


def profundidades(texto):
    """Lista con la profundidad de llaves en cada posición del texto."""
    resultado = []
    d = 0
    for c in texto:
        if c == "}":
            d -= 1
        resultado.append(d)
        if c == "{":
            d += 1
    return resultado


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
        n = float(str(valor).strip().rstrip("fF"))
    except ValueError:
        return None
    return int(n) if n == int(n) else n


def analizar_cuerpo(cuerpo):
    """Devuelve (inclusiones, piezas) del nivel superior de un vehículo o plantilla.
    - inclusiones: lista de 'Plantilla' o 'Plantilla/part/Pieza' (líneas 'template = ...').
    - piezas: lista de (nombre, propiedades, contenedor) de los bloques
      'part Nombre { ... }'. 'contenedor' es el diccionario de propiedades de su
      bloque 'container', o None si la pieza no tiene."""
    prof = profundidades(cuerpo)

    inclusiones = [m.group(1) for m in INCLUSION_RE.finditer(cuerpo) if prof[m.start()] == 0]

    piezas = []
    for m in PIEZA_RE.finditer(cuerpo):
        if prof[m.start()] != 0:
            continue
        abre = m.end() - 1
        cierra = buscar_cierre(cuerpo, abre)
        if cierra < 0:
            continue
        bloque = cuerpo[abre + 1:cierra]
        props = propiedades_nivel_superior(bloque)

        contenedor = None
        prof_bloque = profundidades(bloque)
        for mc in CONTENEDOR_RE.finditer(bloque):
            if prof_bloque[mc.start()] != 0:
                continue
            abre_c = mc.end() - 1
            cierra_c = buscar_cierre(bloque, abre_c)
            if cierra_c >= 0:
                contenedor = propiedades_nivel_superior(bloque[abre_c + 1:cierra_c])
            break
        piezas.append((m.group(1), props, contenedor))

    return inclusiones, piezas


def vehiculos_de_archivo(ruta):
    """Devuelve una lista de (modulo, nombre_script, propiedades, es_plantilla,
    inclusiones, piezas)."""
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
            cuerpo_v = cuerpo[m.end():cierra_v]
            props = propiedades_nivel_superior(cuerpo_v)
            inclusiones, piezas = analizar_cuerpo(cuerpo_v)
            encontrados.append((modulo, m.group(2), props, m.group(1) is not None, inclusiones, piezas))
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
    for modulo, nombre_script, props, es_plantilla, inclusiones, piezas in pares:
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
            "_inclusiones": inclusiones,
            "_piezas": piezas,
            "DisplayName": por_idioma.get("EN"),
            "_translations": {i: n for i, n in por_idioma.items() if i != "EN"},
            "stats": stats,
        })
    return entradas


def indexar(entradas):
    """Devuelve ({id: vehículo}, {id: plantilla})."""
    vehiculos = {e["_full_id"]: e for e in entradas if not e["_plantilla"]}
    plantillas = {e["_full_id"]: e for e in entradas if e["_plantilla"]}
    return vehiculos, plantillas


def buscar_padre(e, vehiculos, plantillas):
    """Busca el vehículo o plantilla del que hereda `e` con 'template!'.
    Un vehículo puede llamarse igual que la plantilla de la que hereda
    (vehicle StepVan con template! = StepVan). Se descarta el propio
    elemento para que encuentre la plantilla y no se tome a sí mismo."""
    ref = e["_hereda_de"]
    id_padre = ref if "." in ref else f"{e['_module']}.{ref}"
    for candidato in (vehiculos.get(id_padre), plantillas.get(id_padre)):
        if candidato is not None and candidato is not e:
            return candidato
    return None


def resolver_herencia(entradas):
    """Rellena las estadísticas que faltan con las del vehículo (o plantilla)
    del que se hereda mediante 'template! = Nombre'. Lo que el vehículo define
    por sí mismo tiene prioridad sobre lo heredado.
    Devuelve (vehiculos_que_ganan_engineForce, referencias_sin_resolver)."""
    vehiculos, plantillas = indexar(entradas)

    def stats_completas(e, visitados):
        stats = dict(e["stats"])
        if not e["_hereda_de"] or e["_full_id"] in visitados:
            return stats
        padre = buscar_padre(e, vehiculos, plantillas)
        if padre is None:
            return stats
        for campo, valor in stats_completas(padre, visitados | {e["_full_id"]}).items():
            stats.setdefault(campo, valor)
        return stats

    ganan_motor = 0
    sin_resolver = []
    for e in entradas:
        if not e["_hereda_de"]:
            continue
        if buscar_padre(e, vehiculos, plantillas) is None:
            if not e["_plantilla"]:
                sin_resolver.append((e["_full_id"], e["_hereda_de"]))
            continue
        tenia_motor = "engineForce" in e["stats"]
        e["stats"] = stats_completas(e, set())
        if not tenia_motor and "engineForce" in e["stats"]:
            ganan_motor += 1
    return ganan_motor, sin_resolver


def cargar_items(carpeta_data):
    """Carga items.json e items_mods.json (si existen) como {full_id: item}."""
    items = {}
    for nombre in ("items.json", "items_mods.json"):
        ruta = carpeta_data / nombre
        if not ruta.exists():
            print(f"AVISO: no existe {ruta}; las capacidades que dependen de items no se podrán resolver")
            continue
        for it in json.loads(ruta.read_text(encoding="utf-8")):
            items[it["_full_id"]] = it
    return items


def capacidad_de(info, mecanica, items):
    """Devuelve (capacidad, origen) de un contenedor ya resuelto.
    origen: 'script' si el container declara capacity; 'item' si sale del
    MaxCapacity del item de la pieza (itemType + mechanicType); 'sin dato'
    si no se puede resolver."""
    cont = info["contenedor"]
    if "capacity" in cont:
        numero = a_numero(cont["capacity"])
        if numero is not None:
            return numero, "script"

    tipo = info["props"].get("itemType")
    if tipo and mecanica is not None:
        item = items.get(f"{tipo}{mecanica}")
        if item and "MaxCapacity" in item:
            valor = item["MaxCapacity"]
            valor = valor[0] if isinstance(valor, list) else valor
            numero = a_numero(valor)
            if numero is not None:
                return numero, "item"

    return None, "sin dato"


def calcular_contenedores(entradas, objetivos, items):
    """Para cada vehículo de `objetivos` devuelve la lista de sus contenedores:
    {pieza, capacidad, origen, contentType, ficticio, almacenamiento}. Se
    resuelven las piezas siguiendo, en este orden: la herencia 'template!', las
    inclusiones de plantillas ('template = X' o 'template = X/part/Pieza') y las
    piezas propias del vehículo (el comodín 'part Seat*' se aplica a todas las
    piezas cuyo nombre empiece igual)."""
    vehiculos, plantillas = indexar(entradas)
    cache = {}

    def copiar(info):
        return {
            "props": dict(info["props"]),
            "contenedor": None if info["contenedor"] is None else dict(info["contenedor"]),
        }

    def fusionar(base, nuevo):
        base["props"].update(nuevo["props"])
        if nuevo["contenedor"] is not None:
            if base["contenedor"] is None:
                base["contenedor"] = {}
            base["contenedor"].update(nuevo["contenedor"])

    def fusionar_en(exactas, nombre, info):
        if nombre not in exactas:
            exactas[nombre] = {"props": {}, "contenedor": None}
        fusionar(exactas[nombre], info)

    def con_comodines(nombre, info, comodines):
        """Aplica primero los comodines que casan con `nombre` y encima la pieza."""
        base = {"props": {}, "contenedor": None}
        for prefijo, c in comodines:
            if nombre.startswith(prefijo):
                fusionar(base, c)
        fusionar(base, info)
        return base

    def buscar_plantilla(e, nombre):
        id_t = nombre if "." in nombre else f"{e['_module']}.{nombre}"
        for candidato in (plantillas.get(id_t), vehiculos.get(id_t)):
            if candidato is not None and candidato is not e:
                return candidato
        return None

    def resolver(e, visitados):
        clave = (e["_full_id"], e["_plantilla"])
        if clave in cache:
            return cache[clave]
        if clave in visitados:
            return {"exactas": {}, "comodines": []}
        visitados = visitados | {clave}

        exactas = {}
        comodines = []

        if e["_hereda_de"]:
            padre = buscar_padre(e, vehiculos, plantillas)
            if padre is not None:
                rp = resolver(padre, visitados)
                exactas = {n: copiar(i) for n, i in rp["exactas"].items()}
                comodines = [(p, copiar(i)) for p, i in rp["comodines"]]

        for inclusion in e["_inclusiones"]:
            nombre_t, _, pieza = inclusion.partition("/part/")
            t = buscar_plantilla(e, nombre_t)
            if t is None:
                continue
            rt = resolver(t, visitados)
            if pieza:
                if pieza in rt["exactas"]:
                    fusionar_en(exactas, pieza, con_comodines(pieza, rt["exactas"][pieza], rt["comodines"]))
            else:
                for n, i in rt["exactas"].items():
                    fusionar_en(exactas, n, con_comodines(n, i, rt["comodines"]))
                comodines.extend((p, copiar(i)) for p, i in rt["comodines"])

        for nombre, props, cont in e["_piezas"]:
            info = {"props": props, "contenedor": cont}
            if nombre.endswith("*"):
                prefijo = nombre[:-1]
                for n in exactas:
                    if n.startswith(prefijo):
                        fusionar(exactas[n], info)
                comodines.append((prefijo, copiar(info)))
            else:
                if nombre not in exactas:
                    vacia = {"props": {}, "contenedor": None}
                    fusionar_en(exactas, nombre, con_comodines(nombre, vacia, comodines))
                fusionar(exactas[nombre], info)

        resultado = {"exactas": exactas, "comodines": comodines}
        cache[clave] = resultado
        return resultado

    salida = {}
    for e in objetivos:
        mecanica = e["stats"].get("mechanicType")
        contenedores = []
        for nombre, info in resolver(e, set())["exactas"].items():
            cont = info["contenedor"]
            if cont is None:
                continue
            capacidad, origen = capacidad_de(info, mecanica, items)

            # Pieza ficticia: sin capacidad y con itemType = nil. Los mods
            # desactivan así el TruckBed genérico y ponen su propio maletero.
            tipo = str(info["props"].get("itemType", "")).strip().lower()
            ficticio = origen == "sin dato" and tipo == "nil"

            contenedores.append({
                "pieza": nombre,
                "capacidad": capacidad,
                "origen": origen,
                "contentType": cont.get("contentType"),
                "ficticio": ficticio,
                "almacenamiento": "contentType" not in cont
                                  and not nombre.startswith(PIEZAS_NO_ALMACENAMIENTO)
                                  and not ficticio,
            })
        salida[e["_full_id"]] = contenedores
    return salida


def categoria_contenedor(pieza):
    """Clasifica un contenedor de almacenamiento por el nombre de su pieza:
    'conductor' (SeatFrontLeft), 'asiento', 'maletero' u 'otro'."""
    if pieza == ASIENTO_CONDUCTOR:
        return "conductor"
    if pieza.startswith("Seat"):
        return "asiento"
    if "trunk" in pieza.lower() or pieza in ("TruckBed", "TruckBedOpen"):
        return "maletero"
    return "otro"


def resumir_almacenamiento(contenedores):
    """Suma las capacidades conocidas de los contenedores de almacenamiento,
    sin el asiento del conductor. 'completo' es False si algún contenedor
    real no tiene capacidad resoluble (el total es entonces un mínimo)."""
    partes = {"maletero": 0, "asiento": 0, "otro": 0}
    completo = True
    for c in contenedores:
        categoria = categoria_contenedor(c["pieza"])
        if categoria == "conductor":
            continue
        if c["capacidad"] is None:
            completo = False
            continue
        partes[categoria] += c["capacidad"]
    return {
        "total": sum(partes.values()),
        "maletero": partes["maletero"],
        "asientos": partes["asiento"],
        "otros": partes["otro"],
        "completo": completo,
    }


def imprimir_resumen_almacenamiento(vehiculos, todos):
    """Diagnóstico del almacenamiento para revisar la clasificación."""
    ficticios = Counter()
    for v in vehiculos:
        for c in todos[v["_full_id"]]:
            if c["ficticio"]:
                ficticios[c["pieza"]] += 1
    print("Piezas ficticias ignoradas (itemType = nil y sin capacidad):", dict(ficticios.most_common(8)))

    incompletos = [v for v in vehiculos if not v["almacenamiento"]["completo"]]
    print(f"Almacenamiento completo: {len(vehiculos) - len(incompletos)} | "
          f"con algún contenedor sin dato: {len(incompletos)}")
    sin_dato = []
    for v in incompletos:
        for c in v["contenedores"]:
            if c["capacidad"] is None and categoria_contenedor(c["pieza"]) != "conductor":
                sin_dato.append((v["_name"], c["pieza"]))
    print("  Piezas sin dato más frecuentes:", dict(Counter(p for _, p in sin_dato).most_common(8)))
    print("  Ejemplos (vehículo, pieza):", sin_dato[:8])

    sin_maletero = [v for v in vehiculos if v["almacenamiento"]["maletero"] == 0]
    print(f"Vehículos sin maletero detectado: {len(sin_maletero)}")
    for v in sin_maletero[:10]:
        print("  ", v["_full_id"], [c["pieza"] for c in v["contenedores"]])

    por_categoria = {"maletero": Counter(), "otro": Counter()}
    for v in vehiculos:
        for c in v["contenedores"]:
            categoria = categoria_contenedor(c["pieza"])
            if categoria in por_categoria:
                por_categoria[categoria][c["pieza"]] += 1
    print("Piezas contadas como maletero (más frecuentes):", dict(por_categoria["maletero"].most_common(15)))
    print("Piezas contadas como 'otros' (más frecuentes):", dict(por_categoria["otro"].most_common(30)))


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

    # Se descartan los remolques salvo que REMOLQUES esté a True.
    remolques = []
    if not REMOLQUES:
        marcados = [(v, motivo_remolque(v)) for v in vehiculos]
        remolques = [(v, motivo) for v, motivo in marcados if motivo]
        vehiculos = [v for v, motivo in marcados if not motivo]

    # Contenedores y almacenamiento de cada vehículo final.
    items = cargar_items(ruta_salida.parent)
    todos_contenedores = calcular_contenedores(unicos, vehiculos, items)
    for v in vehiculos:
        v["contenedores"] = [
            {"pieza": c["pieza"], "capacidad": c["capacidad"], "origen": c["origen"]}
            for c in todos_contenedores[v["_full_id"]]
            if c["almacenamiento"]
        ]
        v["almacenamiento"] = resumir_almacenamiento(v["contenedores"])

    for v in vehiculos:
        for campo in ("_plantilla", "_hereda_de", "_inclusiones", "_piezas"):
            v.pop(campo, None)

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(vehiculos, f, indent=2, ensure_ascii=False)

    n_vanilla = sum(1 for v in vehiculos if v["_source"] == "vanilla")
    sin_nombre = [v for v in vehiculos if not v["DisplayName"]]
    de_mods = [v for v in vehiculos if v["_source"] != "vanilla"]
    con_preview = [v for v in de_mods if v["_preview"]]

    print(f"Vehículos vanilla: {n_vanilla}")
    print(f"Mods con vehículos: {mods_con_vehiculos}")
    print(f"Total de vehículos únicos: {len(vehiculos)} ({duplicados} duplicados descartados)")
    print(f"Plantillas leídas (solo como fuente de datos): {n_plantillas}")
    print(f"Excluidos por no funcionales: {len(excluidos_lista)}")
    print(f"  Excluidos solo por la regla ampliada: {len(solo_regla_ampliada)}")
    print(f"Remolques {'incluidos' if REMOLQUES else 'excluidos'} (REMOLQUES = {REMOLQUES}): {len(remolques)}")
    print(f"Con nombre en inglés: {len(vehiculos) - len(sin_nombre)}")
    print(f"Sin nombre en inglés: {len(sin_nombre)}")
    print(f"Herencia 'template!': {ganan_motor} vehículos ganan engineForce")
    print(f"  Referencias 'template!' sin resolver: {len(sin_resolver)}")
    print("Cobertura de estadísticas:")
    for campo in CAMPOS_ESTADISTICAS:
        n = sum(1 for v in vehiculos if campo in v["stats"])
        print(f"  {campo}: {n} de {len(vehiculos)}")
    print(f"Vehículos de mods con imagen de preview: {len(con_preview)} de {len(de_mods)}")

    print()
    print("Ejemplos de almacenamiento:")
    for nombre in ("SportsCar", "70barracuda", "StepVan_Cereal", "91range", "86oshkoshKYFD"):
        for v in vehiculos:
            if v["_name"] == nombre:
                print(f"  {nombre}: {v['almacenamiento']}")
                break
    print()
    imprimir_resumen_almacenamiento(vehiculos, todos_contenedores)
    print(f"Guardado: {ruta_salida}")


if __name__ == "__main__":
    main()