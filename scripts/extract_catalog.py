#!/usr/bin/env python3
"""Extract the DropOut KiCad library into catalog data for the site.

  python3 scripts/extract_catalog.py <library-dir> [--out .]

Reads <library-dir>/symbols/*.kicad_sym and <library-dir>/footprints/*.pretty and writes:

  src/data/parts.json                         one entry per symbol (every field, library ref,
                                              footprint, 3D model path, drawing paths)
  public/parts/<Lib>/<Symbol>/symbol-<n>.svg  one drawing per symbol unit
  public/parts/<Lib>/<Symbol>/footprint.svg   the linked footprint, when it is in the library

Drawings come from kicad-cli (KiCad 10). An empty library gives an empty catalog.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


# Footprint drawing layers: pads, silkscreen, courtyard (the fab layer's large value text hides small pads)
FP_LAYERS = "F.Cu,B.Cu,F.Mask,F.SilkS,F.CrtYd"


def kicad_cli():
    for c in ("kicad-cli", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"):
        if shutil.which(c) or os.path.exists(c):
            return c
    sys.exit("kicad-cli not found")


# --- minimal S-expression reader ------------------------------------------------------

TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')


def parse_sexpr(text):
    stack, cur = [], []
    pos = 0
    while True:
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        if m.group(1):
            stack.append(cur)
            cur = []
        elif m.group(2):
            done, cur = cur, stack.pop()
            cur.append(done)
        elif m.group(3) is not None:
            cur.append(m.group(3).replace('\\"', '"').replace("\\\\", "\\"))
        else:
            cur.append(m.group(4))
    return cur[0] if cur else []


def children(node, tag):
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def first(node, tag):
    found = children(node, tag)
    return found[0] if found else None


# --- extraction -----------------------------------------------------------------------

def slug(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def read_symbols(sym_file):
    lib = os.path.basename(sym_file)[: -len(".kicad_sym")]
    tree = parse_sexpr(open(sym_file, encoding="utf-8").read())
    for sym in children(tree, "symbol"):
        name = sym[1]
        fields = {p[1]: p[2] for p in children(sym, "property") if len(p) > 2}
        extends = first(sym, "extends")
        yield lib, name, fields, extends[1] if extends else None


def footprint_model(pretty_dir, fp_name):
    path = os.path.join(pretty_dir, f"{fp_name}.kicad_mod")
    if not os.path.exists(path):
        return None
    model = first(parse_sexpr(open(path, encoding="utf-8").read()), "model")
    return model[1] if model else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("library")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()
    lib_dir, out = os.path.abspath(args.library), os.path.abspath(args.out)
    cli = kicad_cli()

    parts_dir = os.path.join(out, "public", "parts")
    shutil.rmtree(parts_dir, ignore_errors=True)
    os.makedirs(parts_dir)
    os.makedirs(os.path.join(out, "src", "data"), exist_ok=True)

    sym_dir = os.path.join(lib_dir, "symbols")
    fp_dir = os.path.join(lib_dir, "footprints")
    sym_files = sorted(f for f in os.listdir(sym_dir) if f.endswith(".kicad_sym")) if os.path.isdir(sym_dir) else []

    parts = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in sym_files:
            sym_path = os.path.join(sym_dir, f)
            for lib, name, fields, extends in read_symbols(sym_path):
                base = f"parts/{slug(lib)}/{slug(name)}"
                dest = os.path.join(out, "public", base)
                os.makedirs(dest, exist_ok=True)

                # symbol drawing(s): kicad-cli writes <name>_unit<n>.svg
                export = os.path.join(tmp, "sym")
                shutil.rmtree(export, ignore_errors=True)
                subprocess.run([cli, "sym", "export", "svg", "-s", name, "-o", export, sym_path],
                               check=True, capture_output=True)
                units = []
                for svg in sorted(os.listdir(export), key=lambda s: int(re.search(r"_unit(\d+)\.svg$", s).group(1))):
                    n = re.search(r"_unit(\d+)\.svg$", svg).group(1)
                    shutil.copy(os.path.join(export, svg), os.path.join(dest, f"symbol-{n}.svg"))
                    units.append(f"{base}/symbol-{n}.svg")

                # footprint drawing, when the footprint is in this library
                footprint = fields.get("Footprint", "")
                fp_svg = model = None
                if ":" in footprint:
                    fp_lib, fp_name = footprint.split(":", 1)
                    pretty = os.path.join(fp_dir, f"{fp_lib}.pretty")
                    if os.path.exists(os.path.join(pretty, f"{fp_name}.kicad_mod")):
                        export = os.path.join(tmp, "fp")
                        shutil.rmtree(export, ignore_errors=True)
                        os.makedirs(export)  # unlike sym export, fp export doesn't create it
                        subprocess.run([cli, "fp", "export", "svg", "--fp", fp_name, "-l", FP_LAYERS, "-o", export, pretty],
                                       check=True, capture_output=True)
                        shutil.copy(os.path.join(export, f"{fp_name}.svg"), os.path.join(dest, "footprint.svg"))
                        fp_svg = f"{base}/footprint.svg"
                        model = footprint_model(pretty, fp_name)

                parts.append({
                    "id": f"{lib}:{name}",
                    "slug": f"{slug(lib)}/{slug(name)}",
                    "library": lib,
                    "category": lib.removeprefix("DropOut_"),
                    "name": name,
                    "extends": extends,
                    "value": fields.get("Value", ""),
                    "description": fields.get("Description", ""),
                    "keywords": fields.get("ki_keywords", ""),
                    "datasheet": fields.get("Datasheet", ""),
                    "footprint": footprint,
                    "manufacturer": fields.get("Manufacturer", ""),
                    "mpn": fields.get("MPN", ""),
                    "digikey_pn": fields.get("DigiKey_PN", ""),
                    "mouser_pn": fields.get("Mouser_PN", ""),
                    "model": model,
                    "fields": fields,
                    "symbol_svgs": units,
                    "footprint_svg": fp_svg,
                })

    parts.sort(key=lambda p: (p["library"], p["name"]))
    with open(os.path.join(out, "src", "data", "parts.json"), "w", encoding="utf-8") as fh:
        json.dump(parts, fh, indent=1, ensure_ascii=False)
    print(f"catalog: {len(parts)} part(s) from {len(sym_files)} symbol librar{'y' if len(sym_files) == 1 else 'ies'}")


if __name__ == "__main__":
    main()
