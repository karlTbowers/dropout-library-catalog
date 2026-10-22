// Compresses the GLBs that scripts/extract_catalog.py wrote to public/models/, in place, before
// `astro build`. Meshopt + quantization take KiCad's export to about a sixth of its size. Meshes
// stay separate (board_PCB, board_soldermask, board_silkscreen, board_pad, the component) so the
// viewer can toggle them, materials stay as exported (STEP colours), and geometry is not simplified.
import { execFileSync } from 'node:child_process';
import { readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = 'public/models';
const glbs = (dir) =>
	readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
		e.isDirectory() ? glbs(join(dir, e.name)) : e.name.endsWith('.glb') ? [join(dir, e.name)] : [],
	);

let files = [];
try {
	files = glbs(root);
} catch {}
for (const f of files) {
	const before = statSync(f).size;
	execFileSync('npx', ['--no-install', 'gltf-transform', 'optimize', f, f,
		'--compress', 'meshopt', '--texture-compress', 'false', '--simplify', 'false',
		'--palette', 'false', '--join-meshes', 'false', '--join-named', 'false'], { stdio: 'pipe' });
	console.log(`${f}: ${(before / 1024).toFixed(0)} KB -> ${(statSync(f).size / 1024).toFixed(0)} KB`);
}
console.log(`models: ${files.length} GLB(s) optimized`);
