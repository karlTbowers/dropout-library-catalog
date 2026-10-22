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
	footprint: string;
	manufacturer: string;
	mpn: string;
	digikey_pn: string;
	mouser_pn: string;
	model: string | null;
	fields: Record<string, string>;
	symbol_svgs: string[];
	footprint_svg: string | null;
}

export function loadParts(): Part[] {
	const file = join(process.cwd(), 'src/data/parts.json');
	return existsSync(file) ? (JSON.parse(readFileSync(file, 'utf8')) as Part[]) : [];
}

export const asset = (path: string) => `${import.meta.env.BASE_URL.replace(/\/$/, '')}/${path}`;

export const LIBRARY_REPO = 'https://github.com/karlTbowers/dropout-kicad-library';
