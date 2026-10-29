#!/usr/bin/env python3
"""Extract the DropOut KiCad library into catalog data for the site.

  python3 scripts/extract_catalog.py <library-dir> [--out .]

Reads <library-dir>/symbols/*.kicad_sym and <library-dir>/footprints/*.pretty and writes:

  src/data/parts.json                         one entry per symbol (every field, library ref,
                                              footprint, 3D model path, drawing paths)
  public/parts/<Lib>/<Symbol>/symbol-<n>.svg  one drawing per symbol unit
  public/parts/<Lib>/<Symbol>/footprint.svg   the linked footprint, when it is in the library
  public/parts/<Lib>/<Symbol>/thumb.svg       the same without REF**, cropped, for thumbnails
  public/models/<FpLib>/<Footprint>.glb       the footprint's 3D model on its pads, one per footprint
                                              (each parts.json entry also carries `schematic`, the
                                              part as KiCad clipboard text for "Copy to schematic")
  src/data/families.json                      catalog families for mechanical parts, from
                                              <library-dir>/parts/families.yaml; each part's
                                              `catalog:` block (part.yaml) lands in parts.json

Drawings and models come from kicad-cli (KiCad 10). Each GLB is the footprint placed on a small
temporary board (pads, mask, silkscreen) with its STEP model, so the model's colours are kept and
any misalignment with the pads shows. The site build compresses them (scripts/optimize_models.mjs).
An empty library gives an empty catalog. Family data needs PyYAML (python3-yaml).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid


# Footprint drawing layers: pads, silkscreen, courtyard (the fab layer's large value text hides small pads)
FP_LAYERS = "F.Cu,B.Cu,F.Mask,F.SilkS,F.CrtYd"


def kicad_cli():
    for c in ("kicad-cli", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"):
        if shutil.which(c) or os.path.exists(c):
            return c
    sys.exit("kicad-cli not found")


# Footprints reference models as ${KIPRJMOD}/<this prefix>/3dmodels/..., i.e. the library mounted
# as a submodule at lib/dropout-kicad-library (library CLAUDE.md)
MODEL_PREFIX = "${KIPRJMOD}/lib/dropout-kicad-library/"


# --- minimal S-expression reader ------------------------------------------------------

TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))')


class Quoted(str):
    """A string that was quoted in the source, so dump_sexpr() quotes it again."""


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
            cur.append(Quoted(m.group(3).replace('\\"', '"').replace("\\\\", "\\")))
        else:
            cur.append(m.group(4))
    return cur[0] if cur else []


def dump_sexpr(node, depth=0):
    """Write a parsed tree back out in KiCad's layout (tabs, one list per line)."""
    if not isinstance(node, list):
        return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"' if isinstance(node, Quoted) else node
    tab = "\t" * depth
    if not any(isinstance(c, list) for c in node):
        return tab + "(" + " ".join(dump_sexpr(c) for c in node) + ")"
    out = tab + "(" + " ".join(dump_sexpr(c) for c in node if not isinstance(c, list))
    for c in node:
        if isinstance(c, list):
            out += "\n" + dump_sexpr(c, depth + 1)
    return out + "\n" + tab + ")"


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
        yield lib, name, fields, extends[1] if extends else None, sym


def num(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def schematic_snippet(lib, sym, x=101.6, y=101.6):
    """The symbol as KiCad Schematic Editor clipboard text: what its own Copy writes (KiCad 10,
    SCH_IO_KICAD_SEXPR::Format for the clipboard), a lib_symbols block with the definition under
    its schematic name "<lib>:<name>", then one placed symbol, with no kicad_sch wrapper. Paste
    reads that (LoadContent); anything else it pastes as a text item. The placed symbol has no
    instances block, so Paste takes the reference from its fields and annotates it like any
    pasted part. Multi-unit symbols place unit 1."""
    lib_id = Quoted(f"{lib}:{sym[1]}")
    cached = [lib_id if i == 1 else c for i, c in enumerate(sym)]
    placed = ["symbol", ["lib_id", lib_id], ["at", num(x), num(y), "0"], ["unit", "1"], ["body_style", "1"]]
    for flag in ("exclude_from_sim", "in_bom", "on_board", "in_pos_files"):
        placed += children(sym, flag)
    placed += [["dnp", "no"], ["uuid", Quoted(str(uuid.uuid4()))]]
    for prop in children(sym, "property"):
        at = first(prop, "at")
        # Library Y points up, schematic Y down; KiCad 10 schematics keep (hide yes) in effects
        text = Quoted(prop[2] + "?") if prop[1] == "Reference" else prop[2]  # unannotated, as in KiCad
        field = ["property", prop[1], text, ["at", num(x + float(at[1])), num(y - float(at[2])), at[3]]]
        effects = [list(e) for e in children(prop, "effects")]
        if first(prop, "hide") and effects:
            effects[0].append(["hide", "yes"])
        placed.append(field + effects)
    pins = sorted({n[1] for unit in children(sym, "symbol") for pin in children(unit, "pin") for n in children(pin, "number")})
    placed += [["pin", Quoted(n), ["uuid", Quoted(str(uuid.uuid4()))]] for n in pins]
    return dump_sexpr(["lib_symbols", cached]) + "\n" + dump_sexpr(placed) + "\n"


def read_families(lib_dir):
    """Catalog families (parts/families.yaml) and each part's catalog block by library ref."""
    parts_dir = os.path.join(lib_dir, "parts")
    fam_file = os.path.join(parts_dir, "families.yaml")
    if not os.path.exists(fam_file):
        return {}, {}
    try:
        import yaml
    except ImportError:
        sys.exit("extract_catalog: the library has parts/families.yaml; reading it needs PyYAML (pip install pyyaml, or apt python3-yaml)")
    families = yaml.safe_load(open(fam_file, encoding="utf-8")) or {}
    blocks = {}
    for d in sorted(os.listdir(parts_dir)):
        f = os.path.join(parts_dir, d, "part.yaml")
        if os.path.exists(f):
            y = yaml.safe_load(open(f, encoding="utf-8")) or {}
            if y.get("catalog") and y.get("library") and y.get("name"):
                blocks[f"{y['library']}:{y['name']}"] = y["catalog"]
    return families, blocks


def footprint_model(pretty_dir, fp_name):
    path = os.path.join(pretty_dir, f"{fp_name}.kicad_mod")
    if not os.path.exists(path):
        return None
    model = first(parse_sexpr(open(path, encoding="utf-8").read()), "model")
    return model[1] if model else None


def crop_svg(svg_file, margin=0.3):
    """Shrink a footprint SVG's page to what is drawn on it (plus a margin, in mm).

    kicad-cli plots a footprint centred on a page sized for its text fields, so an 0402 sits in
    a 15 mm wide image and shows tiny in thumbnails. Used for thumb.svg only; footprint.svg
    keeps KiCad's page so its REF** text stays in proportion. Its plots use only absolute M/L/Z paths and
    circles, so the drawn extent is exact; the hidden <text> search overlay is ignored. Leaves
    the file alone if it finds anything else."""
    s = open(svg_file, encoding="utf-8").read()
    xs, ys = [], []
    for d in re.findall(r'\sd="([^"]*)"', s):
        if re.search(r"[A-KN-Ya-z]", d):  # a command other than M, L, Z
            return
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
        xs += nums[0::2]
        ys += nums[1::2]
    for cx, cy, r in re.findall(r'<circle cx="(-?[\d.]+)" cy="(-?[\d.]+)" r="([\d.]+)"', s):
        xs += [float(cx) - float(r), float(cx) + float(r)]
        ys += [float(cy) - float(r), float(cy) + float(r)]
    if not xs:
        return
    pad = margin + max([float(w) for w in re.findall(r"stroke-width:([\d.]+)", s)] or [0]) / 2
    x0, y0 = min(xs) - pad, min(ys) - pad
    w, h = max(xs) + pad - x0, max(ys) + pad - y0
    s = re.sub(r'width="[\d.]+mm" height="[\d.]+mm" viewBox="[^"]*"',
               f'width="{w:.4f}mm" height="{h:.4f}mm" viewBox="{x0:.4f} {y0:.4f} {w:.4f} {h:.4f}"', s, count=1)
    open(svg_file, "w", encoding="utf-8").write(s)


def export_thumb(cli, pretty_dir, fp_name, out_file, tmp):
    """Footprint drawing for thumbnails: as footprint.svg, but without the REF** text, which
    dwarfs small parts. Plotted from a copy of the footprint with its Reference field hidden."""
    src = open(os.path.join(pretty_dir, f"{fp_name}.kicad_mod"), encoding="utf-8").read()
    hidden, n = re.subn(r'(\(property "Reference" "[^"]*")', r"\1 (hide yes)", src, count=1)
    if not n:
        return False
    lib = os.path.join(tmp, "thumb.pretty")
    export = os.path.join(tmp, "thumb")
    for d in (lib, export):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    open(os.path.join(lib, f"{fp_name}.kicad_mod"), "w", encoding="utf-8").write(hidden)
    r = subprocess.run([cli, "fp", "export", "svg", "--fp", fp_name, "-l", FP_LAYERS, "-o", export, lib], capture_output=True)
    svg = os.path.join(export, f"{fp_name}.svg")
    if r.returncode or not os.path.exists(svg):
        return False
    shutil.copy(svg, out_file)
    crop_svg(out_file)
    return True


POINT = re.compile(r"\((?:start|end|mid|center|xy|at) (-?[\d.]+) (-?[\d.]+)")


def export_glb(cli, lib_dir, pretty_dir, fp_lib, fp_name, out_file, tmp):
    """Place the footprint on a board just larger than it and export a GLB. Returns True on success."""
    work = os.path.join(tmp, "glb")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(os.path.join(work, "lib"))
    os.symlink(lib_dir, os.path.join(work, "lib", "dropout-kicad-library"))  # resolves ${KIPRJMOD}/lib/...

    fp = open(os.path.join(pretty_dir, f"{fp_name}.kicad_mod"), encoding="utf-8").read()
    pts = [(float(x), float(y)) for x, y in POINT.findall(fp)]
    xs, ys = [p[0] for p in pts] or [0], [p[1] for p in pts] or [0]
    m = 1.0  # board margin around the footprint, mm
    # a board footprint is the library footprint with a library-qualified name and a position
    placed = fp.replace(f'(footprint "{fp_name}"', f'(footprint "{fp_lib}:{fp_name}"\n\t(at 0 0)', 1)
    board = (
        '(kicad_pcb (version 20260206) (generator "dropout-catalog")\n'
        '(general (thickness 1.6))\n'
        '(layers (0 "F.Cu" signal) (2 "B.Cu" signal) (1 "F.Mask" user) (3 "B.Mask" user)'
        ' (5 "F.SilkS" user) (7 "B.SilkS" user) (25 "Edge.Cuts" user))\n'
        f"{placed}\n"
        f"(gr_rect (start {min(xs) - m} {min(ys) - m}) (end {max(xs) + m} {max(ys) + m})"
        ' (stroke (width 0.05) (type solid)) (fill no) (layer "Edge.Cuts"))\n)\n'
    )
    pcb = os.path.join(work, "board.kicad_pcb")
    open(pcb, "w", encoding="utf-8").write(board)
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    r = subprocess.run([cli, "pcb", "export", "glb", "-f", "--include-pads", "--include-silkscreen",
                        "--include-soldermask", "-o", out_file, pcb], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_file):
        print(f"warning: GLB export failed for {fp_lib}:{fp_name}: {r.stderr.strip() or r.stdout.strip()}",
              file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("library")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()
    lib_dir, out = os.path.abspath(args.library), os.path.abspath(args.out)
    cli = kicad_cli()

    parts_dir = os.path.join(out, "public", "parts")
    models_dir = os.path.join(out, "public", "models")
    for d in (parts_dir, models_dir):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    os.makedirs(os.path.join(out, "src", "data"), exist_ok=True)

    sym_dir = os.path.join(lib_dir, "symbols")
    fp_dir = os.path.join(lib_dir, "footprints")
    sym_files = sorted(f for f in os.listdir(sym_dir) if f.endswith(".kicad_sym")) if os.path.isdir(sym_dir) else []

    parts = []
    glbs = {}  # footprint -> GLB path (or None), one export per footprint
    with tempfile.TemporaryDirectory() as tmp:
        for f in sym_files:
            sym_path = os.path.join(sym_dir, f)
            for lib, name, fields, extends, sym in read_symbols(sym_path):
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
                fp_svg = thumb_svg = model = glb = None
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
                        thumb = export_thumb(cli, pretty, fp_name, os.path.join(dest, "thumb.svg"), tmp)
                        thumb_svg = f"{base}/thumb.svg" if thumb else fp_svg
                        model = footprint_model(pretty, fp_name)
                        if footprint not in glbs:
                            glbs[footprint] = None
                            step = model[len(MODEL_PREFIX):] if model and model.startswith(MODEL_PREFIX) else None
                            if step and os.path.exists(os.path.join(lib_dir, step)):
                                rel = f"models/{slug(fp_lib)}/{slug(fp_name)}.glb"
                                if export_glb(cli, lib_dir, pretty, fp_lib, fp_name, os.path.join(out, "public", rel), tmp):
                                    glbs[footprint] = rel
                        glb = glbs[footprint]

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
                    "model_glb": glb,
                    "fields": fields,
                    "symbol_svgs": units,
                    "footprint_svg": fp_svg,
                    "thumb_svg": thumb_svg,
                    # derived symbols would need flattening into their parent first; none exist yet
                    "schematic": None if extends else schematic_snippet(lib, sym),
                })

    families, blocks = read_families(lib_dir)
    for p in parts:
        c = blocks.get(p["id"])
        p["catalog"] = c if c and c.get("family") in families else None
    parts.sort(key=lambda p: (p["library"], p["name"]))
    with open(os.path.join(out, "src", "data", "families.json"), "w", encoding="utf-8") as fh:
        json.dump(families, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(out, "src", "data", "parts.json"), "w", encoding="utf-8") as fh:
        json.dump(parts, fh, indent=1, ensure_ascii=False)
    print(f"catalog: {len(parts)} part(s), {sum(1 for g in glbs.values() if g)} 3D model(s) from {len(sym_files)} symbol librar{'y' if len(sym_files) == 1 else 'ies'}, "
          f"{sum(1 for p in parts if p['catalog'])} in {len(families)} famil{'y' if len(families) == 1 else 'ies'}")


if __name__ == "__main__":
    main()
