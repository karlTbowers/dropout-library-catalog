// Display names, spec columns, and filter facets derived from the fields every part already has.
// Values come straight from the library's symbols (Value, Voltage, Tolerance, Power, Dielectric,
// Case, Temperature_Grade); nothing here invents data.
import type { Part } from './parts';

export interface Category {
	key: string; // library suffix, e.g. MCU_NXP
	slug: string; // URL segment, e.g. mcu-nxp
	label: string;
}

const CATEGORY_LABEL: Record<string, string> = {
	Capacitor: 'Capacitors',
	Resistor: 'Resistors',
	Inductor: 'Inductors & chokes',
	Connector: 'Connectors & test points',
	Interface: 'Interface ICs',
	MCU_NXP: 'Microcontrollers',
	Memory: 'Memory',
	Power: 'Power management',
	PowerSwitch: 'Power switches',
	Protection: 'Protection',
	Sensor: 'Sensors',
	Thermistor: 'Thermistors',
	Timing: 'Crystals & oscillators',
};

export function category(key: string): Category {
	const label = CATEGORY_LABEL[key] ?? key.replace(/_/g, ' ');
	return { key, slug: key.toLowerCase().replace(/_/g, '-'), label };
}

// AEC qualification, the first thing an automotive designer filters on.
export function qualification(p: Part): string {
	const t = p.fields.Temperature_Grade ?? '';
	const m = t.match(/AEC-Q(100|101|200)/);
	return m ? `AEC-Q${m[1]}` : 'Not AEC qualified';
}

const SI: Record<string, number> = { p: 1e-12, n: 1e-9, u: 1e-6, µ: 1e-6, m: 1e-3, R: 1, k: 1e3, K: 1e3, M: 1e6, G: 1e9 };

// "4.7uF" → 4.7e-6, "49.9R" → 49.9, "100k" → 1e5, "1/16W" → 0.0625, "±10%" → 10. NaN if not a number.
export function parseNumber(s: string): number {
	if (!s) return NaN;
	const frac = s.match(/^(\d+)\/(\d+)/);
	if (frac) return Number(frac[1]) / Number(frac[2]);
	const m = s.replace(/^±/, '').match(/^(\d+(?:\.\d+)?)\s*([pnuµmRkKMG])?(\d+)?/);
	if (!m) return NaN;
	// "4R7" / "2k2" style: the prefix letter is the decimal point
	const n = m[3] ? Number(`${m[1]}.${m[3]}`) : Number(m[1]);
	return n * (m[2] ? SI[m[2]] : 1);
}

// Value as an engineer reads it: "4.7uF" → "4.7 µF", "100k" → "100 kΩ", "0R" → "0 Ω".
export function displayValue(p: Part): string {
	const v = p.value;
	if (!v || v === p.name || v === p.mpn) return '';
	if (p.category === 'Resistor' || p.category === 'Thermistor') {
		const m = v.match(/^(\d+(?:\.\d+)?)([kKM]?)R?$/);
		if (m) return `${m[1]} ${m[2] ? m[2].replace('K', 'k') : ''}Ω`;
	}
	const c = v.match(/^(\d+(?:\.\d+)?)([pnuµm]?)F$/);
	if (c) return `${c[1]} ${c[2].replace('u', 'µ')}F`;
	return v;
}

export const spaceUnit = (s: string) => s.replace(/^(±?[\d./]+)\s*([A-Za-z%]+)$/, (_, n, u) => (u === '%' ? `${n}%` : `${n} ${u}`));

// Footprint name without its library, e.g. "C_0603_1608Metric".
export const footprintName = (p: Part) => p.footprint.split(':')[1] ?? p.footprint;

export interface Column {
	id: string;
	label: string;
	value: (p: Part) => string; // shown text
	sort?: (p: Part) => number | string; // defaults to the shown text
	facet?: boolean; // also offered as a filter
	mono?: boolean;
}

const field = (k: string) => (p: Part) => spaceUnit(p.fields[k] ?? '');
const num = (k: string) => (p: Part) => parseNumber(p.fields[k] ?? '');

const COMMON_END: Column[] = [
	{ id: 'qual', label: 'Qualification', value: qualification, facet: true },
];

const BY_CATEGORY: Record<string, Column[]> = {
	Capacitor: [
		{ id: 'value', label: 'Capacitance', value: displayValue, sort: (p) => parseNumber(p.value), facet: true },
		{ id: 'voltage', label: 'Voltage', value: field('Voltage'), sort: num('Voltage'), facet: true },
		{ id: 'tol', label: 'Tolerance', value: field('Tolerance'), sort: num('Tolerance'), facet: true },
		{ id: 'diel', label: 'Dielectric', value: field('Dielectric'), facet: true },
		{ id: 'case', label: 'Case', value: field('Case'), facet: true },
	],
	Resistor: [
		{ id: 'value', label: 'Resistance', value: displayValue, sort: (p) => parseNumber(p.value), facet: true },
		{ id: 'tol', label: 'Tolerance', value: field('Tolerance'), sort: num('Tolerance'), facet: true },
		{ id: 'power', label: 'Power', value: field('Power'), sort: num('Power'), facet: true },
		{ id: 'voltage', label: 'Voltage', value: field('Voltage'), sort: num('Voltage'), facet: true },
		{ id: 'case', label: 'Case', value: field('Case'), facet: true },
	],
};

const MFR: Column = { id: 'mfr', label: 'Manufacturer', value: (p) => p.manufacturer, facet: true };
const CAT: Column = { id: 'cat', label: 'Category', value: (p) => category(p.category).label, facet: true };
const PACKAGE: Column = { id: 'fp', label: 'Footprint', value: footprintName, mono: true };

// Columns (and filters) for a category page, or for the all-parts list when key is null.
export function columnsFor(key: string | null): Column[] {
	if (!key) return [MFR, CAT, PACKAGE, ...COMMON_END];
	return [MFR, ...(BY_CATEGORY[key] ?? [PACKAGE]), ...COMMON_END];
}

// Key specs for a part's summary: the category's columns that have a value.
export function keySpecs(p: Part): [string, string][] {
	return (BY_CATEGORY[p.category] ?? [])
		.map((c) => [c.label, c.value(p)] as [string, string])
		.filter(([, v]) => v);
}
