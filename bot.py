import os
import io
import json
import difflib
import discord
from discord import app_commands
from dotenv import load_dotenv
from PIL import Image

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")


# --- Carga de datos: vanilla + mods ---------------------------------------

def cargar_json(ruta, obligatorio=True):
    if not os.path.exists(ruta):
        if obligatorio:
            raise FileNotFoundError(f"Falta {ruta}")
        print(f"AVISO: no existe {ruta}, se continúa sin esos datos")
        return []
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


items_vanilla = cargar_json("data/items.json")
items_mods = cargar_json("data/items_mods.json")
ITEMS = items_vanilla + items_mods

# Los vehículos son opcionales: si falta el archivo, el bot arranca igual.
VEHICULOS = cargar_json("data/vehicles.json", obligatorio=False)

TRADUCCIONES = {
    **cargar_json("data/translations.json"),
    **cargar_json("data/translations_mods.json"),
}


def primero(valor):
    """Algunos campos pueden venir como lista si la clave se repetía en el script."""
    return valor[0] if isinstance(valor, list) else valor


def nombre_mostrado(item):
    return item.get("DisplayName") or item.get("_name")


def nombre_vehiculo(vehiculo):
    """Nombre legible del vehículo; si no tiene, el nombre del script."""
    return vehiculo.get("DisplayName") or vehiculo["_name"]


def limpiar_tipo(item):
    tipo = primero(item.get("ItemType", "?"))
    if isinstance(tipo, str):
        return tipo.replace("base:", "")
    return tipo


# --- Nombres de búsqueda (inglés + traducciones) --------------------------

def nombres_item(item):
    nombres = {nombre_mostrado(item)}
    nombres.update(TRADUCCIONES.get(item["_full_id"], {}).values())
    return list(nombres)


def nombres_vehiculo(vehiculo):
    nombres = {nombre_vehiculo(vehiculo)}
    nombres.update(vehiculo.get("_translations", {}).values())
    if not vehiculo.get("DisplayName"):
        nombres.add(vehiculo["_name"])  # sin nombre legible, se busca por el del script
    return list(nombres)


# Precalculado una sola vez al arrancar, para no repetirlo en cada búsqueda.
NOMBRES_ITEMS = {it["_full_id"]: nombres_item(it) for it in ITEMS}
NOMBRES_VEHICULOS = {v["_full_id"]: nombres_vehiculo(v) for v in VEHICULOS}


# --- Búsqueda ------------------------------------------------------------

def buscar(consulta, lista, nombres_por_id):
    """Devuelve (resultados, total) buscando en `lista`:
    1. Coincidencia exacta con algún nombre -> una sola opción.
    2. Todas las palabras de la consulta aparecen (en cualquier orden) en
       los nombres o en el nombre del mod.
    3. Si no hay nada, sugerencias por similitud con difflib."""
    consulta_normalizada = consulta.strip().lower()
    palabras = consulta_normalizada.split()

    exactos = [
        it for it in lista
        if any(n.lower() == consulta_normalizada for n in nombres_por_id[it["_full_id"]])
    ]
    if exactos:
        return exactos[:1], 1

    def coincide(it):
        texto = " ".join(nombres_por_id[it["_full_id"]]).lower()
        texto += " " + str(it.get("_source_name") or it.get("_source", "")).lower()
        return all(p in texto for p in palabras)

    parciales = sorted(
        (it for it in lista if coincide(it)),
        key=lambda it: nombres_por_id[it["_full_id"]][0].lower(),
    )
    if parciales:
        return parciales[:25], len(parciales)  # Discord permite máximo 25 opciones en un Select

    aplanados = [(n, it) for it in lista for n in nombres_por_id[it["_full_id"]]]
    similares = difflib.get_close_matches(consulta, [n for n, _ in aplanados], n=5, cutoff=0.5)

    sugeridos = []
    vistos = set()
    for nombre, it in aplanados:
        if nombre in similares and it["_full_id"] not in vistos:
            sugeridos.append(it)
            vistos.add(it["_full_id"])
    return sugeridos, len(sugeridos)


# --- Iconos: vanilla + mods -------------------------------------------

def ruta_icono(item):
    """Busca el icono primero en los vanilla (data/icons/) y, si no está,
    en los de mods (data/icons_mods/). Devuelve None si no hay ninguno."""
    if not item.get("_icon_file"):
        return None
    ruta_vanilla = f"data/icons/{item['_icon_file']}"
    if os.path.exists(ruta_vanilla):
        return ruta_vanilla
    ruta_mod = f"data/icons_mods/{item['_icon_file']}"
    if os.path.exists(ruta_mod):
        return ruta_mod
    return None


def reescalar_icono(ruta_icono_archivo, factor=4):
    """Amplía un icono x`factor` con NEAREST para mantener el pixel art
    nítido, y lo devuelve como bytes en memoria."""
    with Image.open(ruta_icono_archivo) as img:
        nuevo_tamano = (img.width * factor, img.height * factor)
        img_grande = img.resize(nuevo_tamano, Image.NEAREST)
        buffer = io.BytesIO()
        img_grande.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer


# --- Embeds -----------------------------------------------------------

def origen(elemento):
    return elemento.get("_source_name") or elemento.get("_source", "vanilla")


def construir_embed(item):
    embed = discord.Embed(title=nombre_mostrado(item), color=discord.Color.dark_grey())
    embed.add_field(name="ID", value=f"`{item['_full_id']}`", inline=True)
    embed.add_field(name="Tipo", value=str(limpiar_tipo(item)), inline=True)
    embed.add_field(name="Categoría", value=str(primero(item.get("DisplayCategory", "?"))), inline=True)
    embed.add_field(name="Origen", value=origen(item), inline=True)

    archivo = None
    ruta = ruta_icono(item)
    if ruta:
        buffer = reescalar_icono(ruta)
        archivo = discord.File(buffer, filename=item["_icon_file"])
        embed.set_image(url=f"attachment://{item['_icon_file']}")

    return embed, archivo


# Estadísticas de vehículo que se muestran, en este orden. Solo aparecen
# las que el vehículo tenga definidas.
ESTADISTICAS_VEHICULO = [
    ("engineForce", "Fuerza del motor"),
    ("maxSpeed", "Velocidad máx."),
    ("mass", "Masa"),
    ("seats", "Asientos"),
    ("engineQuality", "Calidad del motor"),
    ("engineLoudness", "Ruido del motor"),
]


def construir_embed_vehiculo(vehiculo):
    embed = discord.Embed(title=nombre_vehiculo(vehiculo), color=discord.Color.dark_grey())
    embed.add_field(name="ID", value=f"`{vehiculo['_full_id']}`", inline=True)
    embed.add_field(name="Origen", value=origen(vehiculo), inline=True)

    stats = vehiculo.get("stats", {})
    for clave, etiqueta in ESTADISTICAS_VEHICULO:
        if clave in stats:
            embed.add_field(name=etiqueta, value=f"{stats[clave]:g}", inline=True)

    if stats:
        embed.set_footer(text="Valores internos del juego, sin unidades reales")
    return embed


async def enviar_resultado(interaction: discord.Interaction, elemento, modo: str):
    """Envía el resultado final como mensaje público (no efímero).
    Modos: item_id, item_info, vehiculo_id, vehiculo_info."""
    if modo in ("item_id", "vehiculo_id"):
        await interaction.response.send_message(f"`{elemento['_full_id']}`")
    elif modo == "vehiculo_info":
        await interaction.response.send_message(embed=construir_embed_vehiculo(elemento))
    else:  # item_info
        embed, archivo = construir_embed(elemento)
        if archivo:
            await interaction.response.send_message(embed=embed, file=archivo)
        else:
            await interaction.response.send_message(embed=embed)


# --- Menú de selección cuando hay varias coincidencias --------------------

class Selector(discord.ui.View):
    def __init__(self, elementos, modo, etiqueta):
        super().__init__(timeout=60)
        self.elementos = elementos
        self.modo = modo

        # Se añade el ID como descripción porque varios elementos pueden
        # tener el mismo nombre (por ejemplo, las puertas delantera y trasera).
        opciones = [
            discord.SelectOption(
                label=etiqueta(el)[:100],
                description=el["_full_id"][:100],
                value=str(i),
            )
            for i, el in enumerate(elementos)
        ]
        select = discord.ui.Select(placeholder="Elige una opción...", options=opciones)
        select.callback = self.al_seleccionar
        self.add_item(select)

    async def al_seleccionar(self, interaction: discord.Interaction):
        elemento = self.elementos[int(interaction.data["values"][0])]
        await enviar_resultado(interaction, elemento, self.modo)


# --- Lógica compartida por los cuatro comandos ----------------------------

async def manejar_busqueda(interaction: discord.Interaction, nombre: str, modo: str):
    if modo.startswith("vehiculo"):
        lista, nombres, etiqueta = VEHICULOS, NOMBRES_VEHICULOS, nombre_vehiculo
    else:
        lista, nombres, etiqueta = ITEMS, NOMBRES_ITEMS, nombre_mostrado

    resultados, total = buscar(nombre, lista, nombres)

    if not resultados:
        await interaction.response.send_message(
            f"No he encontrado nada parecido a **{nombre}**.", ephemeral=True
        )
        return

    if len(resultados) == 1:
        await enviar_resultado(interaction, resultados[0], modo)
        return

    aviso = ""
    if total > len(resultados):
        aviso = f" (mostrando los {len(resultados)} primeros; añade más palabras para afinar)"
    await interaction.response.send_message(
        f"He encontrado {total} resultados para **{nombre}**{aviso}. Elige uno:",
        view=Selector(resultados, modo, etiqueta),
        ephemeral=True,
    )


# --- Bot y comandos ---------------------------------------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Conectado como {client.user} (ID: {client.user.id})")
    print(f"   {len(ITEMS)} items ({len(items_vanilla)} vanilla + {len(items_mods)} de mods)")
    print(f"   {len(VEHICULOS)} vehículos")


@tree.command(name="getitemid", description="Devuelve el ID de un item de Project Zomboid")
@app_commands.describe(nombre="Nombre del item a buscar (en cualquier idioma soportado)")
async def getitemid(interaction: discord.Interaction, nombre: str):
    await manejar_busqueda(interaction, nombre, "item_id")


@tree.command(name="getiteminfo", description="Muestra la ficha completa de un item de Project Zomboid")
@app_commands.describe(nombre="Nombre del item a buscar (en cualquier idioma soportado)")
async def getiteminfo(interaction: discord.Interaction, nombre: str):
    await manejar_busqueda(interaction, nombre, "item_info")


@tree.command(name="getvehicleid", description="Devuelve el ID de un vehículo de Project Zomboid")
@app_commands.describe(nombre="Nombre del vehículo a buscar (en cualquier idioma soportado)")
async def getvehicleid(interaction: discord.Interaction, nombre: str):
    await manejar_busqueda(interaction, nombre, "vehiculo_id")


@tree.command(name="getvehicleinfo", description="Muestra la ficha de un vehículo de Project Zomboid")
@app_commands.describe(nombre="Nombre del vehículo a buscar (en cualquier idioma soportado)")
async def getvehicleinfo(interaction: discord.Interaction, nombre: str):
    await manejar_busqueda(interaction, nombre, "vehiculo_info")


client.run(TOKEN)