# DropOut library catalog

Browsable catalog of the [DropOut KiCad library](https://github.com/karlTbowers/dropout-kicad-library): symbols, footprints, an interactive 3D model view, fields, and distributor links for every atomic part.

**Site:** https://karltbowers.github.io/dropout-library-catalog/

The catalog is rebuilt automatically whenever the library changes (and nightly). Nothing here needs editing to add a part: add it to the library and it appears.

Build locally (Node 22+, Python 3, KiCad 10):

```bash
python3 scripts/extract_catalog.py ~/Dev/dropout-kicad-library --out .
npm ci && npm run models && npm run dev
```

## License

TBD — to be chosen with the library's license.
