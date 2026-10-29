// McMaster-style family tables: one table per group, the attributes that differ as columns and the
// ones every row shares listed above the table. Manufacturer and Temperature come from the parts'
// fields; everything else from their `catalog:` blocks.
import { thumbnail, type Family, type Part } from './parts';

export interface GroupTable {
	name: string;
	slug: string;
	parts: Part[];
	shared: [string, string][]; // same value on every row
	columns: string[]; // differs between rows, in first-seen order
	value: (p: Part, col: string) => string;
	mates: string[]; // MPNs every row mates with
	picture: string | null; // a thumbnail for the group
	rowPictures: boolean; // rows have different footprints, so show one per row
}

export const slugify = (s: string) =>
	s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

const attr = (p: Part, col: string): string => {
	if (col === 'Manufacturer') return p.manufacturer;
	if (col === 'Temperature') return p.fields.Temperature_Grade ?? '';
	if (col === 'Mates with') return (p.catalog?.mates_with ?? []).join(', ');
	return p.catalog?.attributes[col] ?? '';
};

export function groupTables(family: string, fam: Family, parts: Part[]): GroupTable[] {
	return fam.groups
		.map((name) => {
			const rows = parts.filter((p) => p.catalog?.family === family && p.catalog.group === name);
			const names = ['Manufacturer', ...new Set(rows.flatMap((p) => Object.keys(p.catalog!.attributes))), 'Temperature', 'Mates with'];
			const shared: [string, string][] = [];
			const columns: string[] = [];
			for (const n of names) {
				const vals = new Set(rows.map((p) => attr(p, n)));
				if (vals.size > 1) columns.push(n);
				else if (n !== 'Mates with' && [...vals][0]) shared.push([n, [...vals][0]]);
			}
			const mates = columns.includes('Mates with') ? [] : rows[0]?.catalog?.mates_with ?? [];
			return {
				name,
				slug: slugify(name),
				parts: rows,
				shared,
				columns,
				value: attr,
				mates,
				picture: rows.length ? thumbnail(rows.find((p) => p.thumb_svg) ?? rows[0]) : null,
				rowPictures: new Set(rows.map((p) => p.footprint)).size > 1,
			};
		})
		.filter((g) => g.parts.length > 0);
}

// Library parts by MPN, for linking "mates with" to parts we have.
export function byMpn(parts: Part[]): Map<string, Part> {
	return new Map(parts.map((p) => [p.mpn, p]));
}
