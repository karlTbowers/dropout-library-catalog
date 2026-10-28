# DropOut library catalog — instructions for Claude

This repo builds the public, browsable catalog of the DropOut KiCad library (`karlTbowers/dropout-kicad-library`): one page per part with its symbol and footprint drawings, every field, distributor links, and an interactive 3D view of its footprint's model. It is published to GitHub Pages at **https://karltbowers.github.io/dropout-library-catalog/**.

It is a separate repo so the library stays lean: every board mounts the library as a submodule, and none of them needs the site's sources or tooling. The library repo contains only parts and their checks.

**Company-wide process** is in the DropOut Hardware Handbook (the `dropout-hardware` Claude Code plugin; working copy at `~/Dev/dropout-hardware-handbook`). The library's own rules (KLC, atomic parts, required fields) are in the library repo's `CLAUDE.md` and `docs/CONTRIBUTING.md`. This file covers only the catalog.

## How it works

```
scripts/extract_catalog.py     reads a library checkout → src/data/parts.json + public/parts/<Lib>/<Symbol>/*.svg
                               (symbol-<n>.svg, footprint.svg, and thumb.svg: the footprint without REF**, cropped)
                               + public/models/<FpLib>/<Footprint>.glb (one per footprint with a model)
scripts/optimize_models.mjs    `npm run models`: compresses those GLBs in place (gltf-transform, meshopt)
src/components/ModelViewer.astro  3D viewer (three.js), or a "no 3D model" panel
src/lib/parts.ts               loads parts.json (empty catalog if absent)
src/lib/specs.ts               category names, spec columns and filters per category, value parsing (4.7uF, 4k7, 1/16W)
src/components/PartBrowser.astro  filter sidebar with live counts, sortable columns, chips, state in the URL, cards on phones
src/pages/index.astro          home: category tiles + all parts, filtered by the header search as you type
src/pages/category/[cat].astro one page per library category with its spec columns and filters
src/pages/parts/[...slug].astro  part page: drawings, 3D viewer, field table, datasheet/DigiKey/Mouser, copy buttons, STEP link
src/styles/tokens.css          every colour and font as a CSS token (light and dark)
.github/workflows/catalog.yml  extract (kicad/kicad:10.0) → build (Node: models, astro) → deploy (Pages)
```

The workflow checks out the library's `main` at build time; nothing from the library is committed here. It runs on:
- `repository_dispatch` (`library-updated`), sent by the library's CI on every push to its `main` (needs the library secret `CATALOG_DISPATCH_TOKEN`, see below);
- a nightly schedule, as a fallback;
- pushes to this repo's `main`, and manually (`workflow_dispatch`). Pull requests build without deploying.

`parts.json`, `public/parts/`, and `public/models/` are generated, not committed (`.gitignore`).

## Build locally

Needs Node 22+, Python 3, and KiCad 10 (`kicad-cli`).

```bash
python3 scripts/extract_catalog.py ~/Dev/dropout-kicad-library --out .
npm ci && npm run models && npm run dev   # http://localhost:4321/dropout-library-catalog/
```

## Decisions already made with the user

- **Generator: Astro.** Not Hugo, Jekyll, seite, or KiCAD-Prism (the user reviewed and rejected KiCAD-Prism).
- **Separate repo** from the library (2026-10-22), named `dropout-library-catalog`; rebuilt by library push (dispatch) plus nightly.
- **Interactive 3D model viewer is required.**
- **3D approach (2026-10-22): convert at build time, view with three.js.** In the extract job, each footprint is placed on a small temporary board (outline 1 mm outside the footprint's graphics; `lib/dropout-kicad-library` symlinked to the library checkout so the `${KIPRJMOD}` model path resolves) and exported with `kicad-cli pcb export glb --include-pads --include-silkscreen --include-soldermask`. Then `gltf-transform optimize` (meshopt + quantization, no simplification, meshes and materials kept separate) in the build job. Why:
  - KiCad does the STEP tessellation and placement exactly as a board would, so the STEP colours (body, balls/pins) come through, and the model sits on the real pads, which doubles as a model-alignment check. No OpenCascade/CadQuery install needed: `kicad-cli` is already in the extract container.
  - Pages stay fast: no STEP parsing in the browser (occt-import-js would ship a multi-megabyte WASM and tessellate on every visit). The S32K344's LFBGA-257 is 2.5 MB as exported, 0.4 MB compressed.
  - three.js over `<model-viewer>`: it needs toggling named meshes (board, silkscreen), precise top/bottom views, and a background from the theme tokens; three.js does all of it in a small island, while `<model-viewer>` bundles three.js anyway and hides the scene graph.
  - three.js is an npm dependency at an exact version (`package.json`), bundled by Astro and loaded only when a viewer scrolls near the screen; no CDN scripts. `gltf-transform` is a dev dependency, also exact.
- **Viewer:** orbit (drag), zoom (wheel/pinch), pan (right-drag/two-finger); 3D/Top/Bottom presets; Board and Silkscreen toggles (by glTF mesh name: `board_PCB`, `board_soldermask`, `board_silkscreen`; `board_pad` and the component always show); background `--viewer-bg`; renders on demand. Footprints without a model (or whose STEP is missing from the library) get a "No 3D model for this footprint." panel; a load failure shows a message, not a broken canvas. A failed GLB export is a build warning, not a build failure.
- **No DropOut branding exists yet.** Clean, neutral engineering-datasheet look, light and dark modes, all colours and fonts as tokens in `src/styles/tokens.css` so branding can drop in later.
- **Catalog page:** search plus filters (category, manufacturer, package); one row per part.
- **Part page:** symbol and footprint SVGs side by side; full field table; datasheet, DigiKey, and Mouser links; copy buttons for MPN and library reference (`DropOut_Power:LM74910H-Q1`); 3D viewer.
- **UX model (2026-10-28): DigiKey for electronic parts, McMaster-Carr for mechanical ones.** Phase 1 (done): category tiles; per-category spec columns and filters built from fields the parts already have (`Case`, `Voltage`, `Tolerance`, `Power`, `Dielectric`, AEC qualification from `Temperature_Grade`); filter counts per option; numeric sorting; filters, search and sort in the URL; value-aware search (`100n` = `0.1u`, `4k7`); one card per part on phones; part page with a summary (key specs, badges, Datasheet/DigiKey/Mouser/STEP buttons, copyable symbol and MPN), grouped specs, KiCad fields collapsed, and alternatives (same value and case for passives, same footprint otherwise). Phase 2 (planned): McMaster-style family pages for mechanical parts with a variant table and "mates with" links; needs `family` and structured attributes in the library's `part.yaml`, read by the extractor straight from `parts/`.
- **Never call distributor APIs from the browser.** Stock/price data, when added, comes from a scheduled job using Actions secrets.

## Status

Done (2026-10-22): 3D viewer (see decision above). Skeleton: extraction of fields and symbol/footprint SVGs (footprint drawings plot F.Cu, B.Cu, F.Mask, F.SilkS, F.CrtYd), catalog page with search and filters, part page with drawings, fields, links, copy buttons, and a STEP download link; workflow with dispatch, nightly, and Pages deploy. Tested on a one-part sample library and on the empty library.

To do, alongside the first real parts:
1. **Package filter** for categories without a `Case` field (needs a package field or footprint-derived package).
2. **Pagefind** static search once the catalog outgrows the client-side filter.
3. **Later:** "used in" board links, nightly DigiKey/Mouser stock and price snapshot, per-part changelog from library git history.

## The dispatch token (one-time, done by the user)

The library's CI triggers this repo with a fine-grained personal access token stored as the library secret `CATALOG_DISPATCH_TOKEN`: repository access **only** `dropout-library-catalog`, permission **Contents: read and write** (required by the repository-dispatch API). Until it exists, the library's notify step skips with a notice and the nightly build keeps the catalog at most a day behind.
