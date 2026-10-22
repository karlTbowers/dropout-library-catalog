# DropOut library catalog — instructions for Claude

This repo builds the public, browsable catalog of the DropOut KiCad library (`karlTbowers/dropout-kicad-library`): one page per part with its symbol and footprint drawings, every field, distributor links, and (planned) an interactive 3D view. It is published to GitHub Pages at **https://karltbowers.github.io/dropout-library-catalog/**.

It is a separate repo so the library stays lean: every board mounts the library as a submodule, and none of them needs the site's sources or tooling. The library repo contains only parts and their checks.

**Company-wide process** is in the DropOut Hardware Handbook (the `dropout-hardware` Claude Code plugin; working copy at `~/Dev/dropout-hardware-handbook`). The library's own rules (KLC, atomic parts, required fields) are in the library repo's `CLAUDE.md` and `docs/CONTRIBUTING.md`. This file covers only the catalog.

## How it works

```
scripts/extract_catalog.py     reads a library checkout → src/data/parts.json + public/parts/<Lib>/<Symbol>/*.svg
src/lib/parts.ts               loads parts.json (empty catalog if absent)
src/pages/index.astro          catalog: search + category and manufacturer filters, one row per part
src/pages/parts/[...slug].astro  part page: drawings, field table, datasheet/DigiKey/Mouser, copy buttons, STEP link
src/styles/tokens.css          every colour and font as a CSS token (light and dark)
.github/workflows/catalog.yml  extract (kicad/kicad:10.0) → build (Node) → deploy (Pages)
```

The workflow checks out the library's `main` at build time; nothing from the library is committed here. It runs on:
- `repository_dispatch` (`library-updated`), sent by the library's CI on every push to its `main` (needs the library secret `CATALOG_DISPATCH_TOKEN`, see below);
- a nightly schedule, as a fallback;
- pushes to this repo's `main`, and manually (`workflow_dispatch`). Pull requests build without deploying.

`parts.json` and `public/parts/` are generated, not committed (`.gitignore`).

## Build locally

Needs Node 22+, Python 3, and KiCad 10 (`kicad-cli`).

```bash
python3 scripts/extract_catalog.py ~/Dev/dropout-kicad-library --out .
npm ci && npm run dev        # http://localhost:4321/dropout-library-catalog/
```

## Decisions already made with the user

- **Generator: Astro.** Not Hugo, Jekyll, seite, or KiCAD-Prism (the user reviewed and rejected KiCAD-Prism).
- **Separate repo** from the library (2026-10-22), named `dropout-library-catalog`; rebuilt by library push (dispatch) plus nightly.
- **Interactive 3D model viewer is required** (see to-do).
- **No DropOut branding exists yet.** Clean, neutral engineering-datasheet look, light and dark modes, all colours and fonts as tokens in `src/styles/tokens.css` so branding can drop in later.
- **Catalog page:** search plus filters (category, manufacturer, package); one row per part.
- **Part page:** symbol and footprint SVGs side by side; full field table; datasheet, DigiKey, and Mouser links; copy buttons for MPN and library reference (`DropOut_Power:LM74910H-Q1`); 3D viewer.
- **Never call distributor APIs from the browser.** Stock/price data, when added, comes from a scheduled job using Actions secrets.

## Status

Done (skeleton, 2026-10-22): extraction of fields and symbol/footprint SVGs (footprint drawings plot F.Cu, B.Cu, F.Mask, F.SilkS, F.CrtYd), catalog page with search and filters, part page with drawings, fields, links, copy buttons, and a STEP download link; workflow with dispatch, nightly, and Pages deploy. Tested on a one-part sample library and on the empty library.

To do, alongside the first real parts:
1. **3D:** in the extract job, build one GLB per footprint by placing the footprint on a minimal temporary board and running `kicad-cli pcb export glb`; add a `<model-viewer>` (or small three.js island) on part pages only: orbit/zoom/pan/reset, top/bottom/isometric presets, toggles for substrate and silkscreen, theme-matched background, "Download STEP". The GLB shows the model on the real pads, so it doubles as a model-alignment check.
2. **Package filter** on the catalog page (needs a package field or footprint-derived package).
3. **Pagefind** static search once the catalog outgrows the client-side filter.
4. **Later:** "used in" board links, nightly DigiKey/Mouser stock and price snapshot, per-part changelog from library git history.

## The dispatch token (one-time, done by the user)

The library's CI triggers this repo with a fine-grained personal access token stored as the library secret `CATALOG_DISPATCH_TOKEN`: repository access **only** `dropout-library-catalog`, permission **Contents: read and write** (required by the repository-dispatch API). Until it exists, the library's notify step skips with a notice and the nightly build keeps the catalog at most a day behind.
