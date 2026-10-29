// Catalog data written by scripts/extract_catalog.py (src/data/parts.json, not committed).
// Without it (a fresh clone, before extraction) the catalog is simply empty.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export interface Part {
	id: string; // DropOut_<Category>:<Symbol>
	slug: string; // <Library>/<Symbol>, URL path under /parts/
	library: string;
	category: string;
	name: string;
	extends: string | null;
	value: string;
	description: string;
	keywords: string;
	datasheet: string;
	footprint: string; // empty for a part not placed on the PCB
	on_board: boolean; // false for a part bought but not placed on the PCB (e.g. a panel connector): no footprint
	manufacturer: string;
	mpn: string;
	digikey_pn: string;
	mouser_pn: string;
	model: string | null; // the footprint's model path as written in the footprint (off-board parts: from Notes)
	model_glb: string | null; // models/<FpLib>/<Footprint>.glb (off-board parts: models/parts/<Lib>/<Symbol>.glb) under public/
	fields: Record<string, string>;
	symbol_svgs: string[];
	footprint_svg: string | null;
	thumb_svg: string | null; // footprint drawing without the REF** text, for thumbnails
	catalog: CatalogBlock | null; // family membership, from the part's part.yaml (mechanical parts)
}

// A part's `catalog:` block (library parts/<MPN>/part.yaml; format in parts/families.yaml there).
export interface CatalogBlock {
	family: string;
	group: string;
	attributes: Record<string, string>;
	mates_with?: string[];
}

export interface Family {
	title: string;
	intro?: string;
	groups: string[];
}

export function loadFamilies(): Record<string, Family> {
	const file = join(process.cwd(), 'src/data/families.json');
	return existsSync(file) ? (JSON.parse(readFileSync(file, 'utf8')) as Record<string, Family>) : {};
}

export function loadParts(): Part[] {
	const file = join(process.cwd(), 'src/data/parts.json');
	return existsSync(file) ? (JSON.parse(readFileSync(file, 'utf8')) as Part[]) : [];
}

// Picture for lists and family tables: the footprint, or the symbol for a part with no footprint.
export const thumbnail = (p: Part) => p.thumb_svg ?? p.symbol_svgs[0] ?? null;

export const asset = (path: string) => `${import.meta.env.BASE_URL.replace(/\/$/, '')}/${path}`;

export const LIBRARY_REPO = 'https://github.com/karlTbowers/dropout-kicad-library';
