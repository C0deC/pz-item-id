"""
Parsea todas las definiciones de items de Project Zomboid desde media/scripts/*.txt.

Adaptado del script parse_items.py del repositorio pz-item-browser
(GitHub: KevinLinTW1021/pz-item-browser), con ajustes para:
- Ignorar bloques comentados con // antes de buscar module/item.
- Etiquetar cada item con su origen (_source) para soporte futuro de mods.

Cada .txt tiene esta forma:
    module ModuleName {
        item ItemName {
            DisplayName = ...,
            Type = ...,
            Icon = ...,
            ...
        }
        ...
    }

Las recetas, modelos, sonidos, etc. también viven dentro de módulos pero usan
otros prefijos distintos a "item". Aquí solo recogemos bloques `item NOMBRE { ... }`.

Salida: data/items.json
"""

import json
import re
import sys
from pathlib import Path


ITEM_RE = re.compile(r"\bitem\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)
MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z0-9_]+)\s*\{", re.MULTILINE)


def strip_line_comments(text):
    """Elimina todo lo que va después de // en cada línea, para que un
    module/item comentado no se detecte como uno real."""
    return "\n".join(line.split("//")[0] for line in text.split("\n"))


def find_matching_brace(text, open_idx):
    """Dado el índice de una '{', devuelve el índice de la '}' que la cierra."""
    depth = 0
    i = open_idx
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def parse_kv_block(block):
    """Parsea líneas 'Clave = Valor,' y las convierte en un diccionario.
    Si una misma clave aparece varias veces, el valor se convierte en una lista."""
    out = {}
    for line in block.split("\n"):
        line = line.split("/*")[0].split("//")[0].strip()
        if not line or line.startswith("/"):
            continue
        line = line.rstrip(",").strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        if k in out:
            if isinstance(out[k], list):
                out[k].append(v)
            else:
                out[k] = [out[k], v]
        else:
            out[k] = v
    return out


def parse_file(path):
    """Parsea un único archivo .txt y devuelve la lista de items encontrados en él."""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = strip_line_comments(text)
    items = []

    # Busca todos los bloques module { ... }
    for m_module in MODULE_RE.finditer(text):
        module_name = m_module.group(1)
        brace_open = text.find("{", m_module.end() - 1)
        if brace_open < 0:
            continue
        brace_close = find_matching_brace(text, brace_open)
        if brace_close < 0:
            continue
        module_body = text[brace_open + 1:brace_close]

        # Busca los items dentro de este módulo
        for m_item in ITEM_RE.finditer(module_body):
            item_name = m_item.group(1)
            i_open = module_body.find("{", m_item.end() - 1)
            if i_open < 0:
                continue
            i_close = find_matching_brace(module_body, i_open)
            if i_close < 0:
                continue
            item_body = module_body[i_open + 1:i_close]
            kv = parse_kv_block(item_body)
            kv["_name"] = item_name
            kv["_module"] = module_name
            kv["_full_id"] = f"{module_name}.{item_name}"
            kv["_source_file"] = path.name
            items.append(kv)

    return items


def parse_root(root_dir, source_label):
    """Parsea todos los .txt bajo root_dir, etiquetando cada item con
    source_label (ej. 'vanilla', o el nombre de un mod). Preparado para
    cuando añadamos rutas de mods, aunque de momento solo se use con vanilla."""
    txt_files = sorted(Path(root_dir).rglob("*.txt"))
    print(f"Explorando {len(txt_files)} archivos de script en {root_dir} (origen: {source_label})")

    items = []
    for p in txt_files:
        try:
            found = parse_file(p)
            for it in found:
                it["_source"] = source_label
            items.extend(found)
        except Exception as e:
            print(f"  {p.name}: FALLÓ -- {e}")
    return items


def main():
    if len(sys.argv) < 3:
        print(f"Uso: {sys.argv[0]} <carpeta_scripts> <json_salida>")
        sys.exit(1)
    scripts_dir = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    all_items = parse_root(scripts_dir, "vanilla")
    # Capa 2 (pendiente): sumar aquí más llamadas a parse_root() por cada
    # carpeta de mod instalado, con su nombre de mod como source_label.

    print(f"Total de items parseados: {len(all_items)}")

    # Estadísticas rápidas (algunas claves aparecen dos veces en los scripts
    # -> el valor es una lista, cogemos el primero)
    def first(v):
        return v[0] if isinstance(v, list) else v

    cats = {}
    types = {}
    with_icon = 0
    for it in all_items:
        c = first(it.get("DisplayCategory", "?"))
        cats[c] = cats.get(c, 0) + 1
        t = first(it.get("ItemType", it.get("Type", "?")))
        types[t] = types.get(t, 0) + 1
        if it.get("Icon"):
            with_icon += 1
    print(f"Con Icon=: {with_icon}")
    print(f"Tipos más frecuentes: {sorted(types.items(), key=lambda x: -x[1])[:8]}")
    print(f"Categorías más frecuentes: {sorted(cats.items(), key=lambda x: -x[1])[:8]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2, ensure_ascii=False)
    print(f"Guardado en: {out_path}")


if __name__ == "__main__":
    main()