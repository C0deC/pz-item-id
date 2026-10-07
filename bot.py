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

with open("data/items.json", encoding="utf-8") as f:
    items_vanilla = json.load(f)

with open("data/items_mods.json", encoding="utf-8") as f:
    items_mods = json.load(f)

ITEMS = items_vanilla + items_mods

with open("data/translations.json", encoding="utf-8") as f:
    traducciones_vanilla = json.load(f)

with open("data/translations_mods.json", encoding="utf-8") as f:
    traducciones_mods = json.load(f)

TRADUCCIONES = {**traducciones_vanilla, **traducciones_mods}


def primero(valor):
    """Algunos campos pueden venir como lista si la clave se repetía en el script."""
    return valor[0] if isinstance(valor, list) else valor


def nombre_mostrado(item):
    return item.get("DisplayName") or item.get("_name")


def limpiar_tipo(item):
    tipo = primero(item.get("ItemType", "?"))
    if isinstance(tipo, str):
        return tipo.replace("base:", "")
    return tipo


# --- Nombres de búsqueda (inglés + traducciones) --------------------------

def calcular_nombres_busqueda(item):
    """Devuelve todos los nombres por los que se puede encontrar este item:
    el nombre mostrado (inglés) más todas sus traducciones disponibles."""
    nombres = {nombre_mostrado(item)}
    traducciones_item = TRADUCCIONES.get(item["_full_id"], {})
    nombres.update(traducciones_item.values())
    return list(nombres)


# Precalculado una sola vez al arrancar, para no repetirlo en cada búsqueda.
NOMBRES_POR_ITEM = {item["_full_id"]: calcular_nombres_busqueda(item) for item in ITEMS}

# Lista aplanada (nombre, item) para las sugerencias por similitud.
NOMBRES_APLANADOS = [
    (nombre, item)
    for item in ITEMS
    for nombre in NOMBRES_POR_ITEM[item["_full_id"]]
]


# --- Búsqueda ------------------------------------------------------------

def buscar_items(consulta):
    """Devuelve una lista de items que coinciden con la consulta, mirando
    tanto el nombre en inglés como sus traducciones:
    1. Coincidencia exacta (ignorando mayúsculas) -> una sola opción.
    2. Coincidencia parcial (el texto está contenido en algún nombre) -> puede haber varias.
    3. Si no hay nada, sugerencias por similitud con difflib."""
    consulta_normalizada = consulta.strip().lower()

    exactos = [
        item for item in ITEMS
        if any(n.lower() == consulta_normalizada for n in NOMBRES_POR_ITEM[item["_full_id"]])
    ]
    if exactos:
        return exactos[:1]

    parciales = [
        item for item in ITEMS
        if any(consulta_normalizada in n.lower() for n in NOMBRES_POR_ITEM[item["_full_id"]])
    ]
    if parciales:
        return parciales[:25]  # Discord permite máximo 25 opciones en un Select

    todos_los_nombres = [n for n, _ in NOMBRES_APLANADOS]
    similares = difflib.get_close_matches(consulta, todos_los_nombres, n=5, cutoff=0.5)

    items_sugeridos = []
    vistos = set()
    for nombre, item in NOMBRES_APLANADOS:
        if nombre in similares and item["_full_id"] not in vistos:
            items_sugeridos.append(item)
            vistos.add(item["_full_id"])
    return items_sugeridos


# --- Iconos: vanilla + mods -------------------------------------------

def ruta_icono(item):
    """Devuelve la ruta del icono del item, buscando primero en los
    iconos vanilla (data/icons/) y, si no está ahí, en los de mods
    (data/icons_mods/), o None si no hay icono en ningún sitio."""
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
    """Amplía un icono x`factor` usando NEAREST para mantener el pixel art
    nítido (sin difuminar), y lo devuelve como bytes en memoria (sin
    escribir nada a disco)."""
    with Image.open(ruta_icono_archivo) as img:
        nuevo_tamano = (img.width * factor, img.height * factor)
        img_grande = img.resize(nuevo_tamano, Image.NEAREST)
        buffer = io.BytesIO()
        img_grande.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer


# --- Construcción del embed para /getinfo --------------------------------

def construir_embed(item):
    embed = discord.Embed(title=nombre_mostrado(item), color=discord.Color.dark_grey())
    embed.add_field(name="ID", value=f"`{item['_full_id']}`", inline=True)
    embed.add_field(name="Tipo", value=str(limpiar_tipo(item)), inline=True)
    embed.add_field(name="Categoría", value=str(primero(item.get("DisplayCategory", "?"))), inline=True)
    embed.add_field(name="Origen", value=item.get("_source_name") or item.get("_source", "vanilla"), inline=True)

    archivo = None
    ruta = ruta_icono(item)
    if ruta:
        buffer = reescalar_icono(ruta)
        archivo = discord.File(buffer, filename=item["_icon_file"])
        embed.set_image(url=f"attachment://{item['_icon_file']}")

    return embed, archivo


# --- Menú de selección cuando hay varias coincidencias --------------------

class SelectorItems(discord.ui.View):
    def __init__(self, items, modo):
        super().__init__(timeout=60)
        self.items = items
        self.modo = modo  # "id" o "info"

        opciones = [
            discord.SelectOption(label=nombre_mostrado(it)[:100], value=str(i))
            for i, it in enumerate(items)
        ]
        select = discord.ui.Select(placeholder="Elige un item...", options=opciones)
        select.callback = self.al_seleccionar
        self.add_item(select)

    async def al_seleccionar(self, interaction: discord.Interaction):
        indice = int(interaction.data["values"][0])
        item = self.items[indice]

        # Mensaje nuevo y público (no edita el menú efímero original),
        # para que el resultado se vea igual de visible que una
        # coincidencia única, tanto para items vanilla como de mods.
        if self.modo == "id":
            await interaction.response.send_message(f"`{item['_full_id']}`")
        else:
            embed, archivo = construir_embed(item)
            if archivo:
                await interaction.response.send_message(embed=embed, file=archivo)
            else:
                await interaction.response.send_message(embed=embed)


# --- Lógica compartida entre /getid y /getinfo ----------------------------

async def manejar_busqueda(interaction: discord.Interaction, nombre: str, modo: str):
    resultados = buscar_items(nombre)

    if not resultados:
        await interaction.response.send_message(
            f"No he encontrado ningún item parecido a **{nombre}**.", ephemeral=True
        )
        return

    if len(resultados) == 1:
        item = resultados[0]
        if modo == "id":
            await interaction.response.send_message(f"`{item['_full_id']}`")
        else:
            embed, archivo = construir_embed(item)
            if archivo:
                await interaction.response.send_message(embed=embed, file=archivo)
            else:
                await interaction.response.send_message(embed=embed)
        return

    vista = SelectorItems(resultados, modo)
    await interaction.response.send_message(
        f"He encontrado {len(resultados)} items que coinciden con **{nombre}**. Elige uno:",
        view=vista,
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
    print(f"   {len(ITEMS)} items cargados ({len(items_vanilla)} vanilla + {len(items_mods)} de mods)")


@tree.command(name="getid", description="Devuelve el ID de un item de Project Zomboid")
@app_commands.describe(nombre="Nombre del item a buscar (en cualquier idioma soportado)")
async def getid(interaction: discord.Interaction, nombre: str):
    await manejar_busqueda(interaction, nombre, "id")


@tree.command(name="getinfo", description="Muestra la ficha completa de un item de Project Zomboid")
@app_commands.describe(nombre="Nombre del item a buscar (en cualquier idioma soportado)")
async def getinfo(interaction: discord.Interaction, nombre: str):
    await manejar_busqueda(interaction, nombre, "info")


client.run(TOKEN)