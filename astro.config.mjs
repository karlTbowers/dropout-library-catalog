// @ts-check
import { defineConfig } from 'astro/config';

// DropOut library catalog, published by .github/workflows/catalog.yml to
// https://karltbowers.github.io/dropout-library-catalog/
export default defineConfig({
	site: 'https://karltbowers.github.io',
	base: '/dropout-library-catalog',
	trailingSlash: 'always',
});
