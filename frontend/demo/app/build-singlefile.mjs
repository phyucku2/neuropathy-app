/**
 * Fold the vite demo build (dist/index.html + one JS + one CSS) into ONE
 * self-contained HTML file at dist/neuropathy-demo.html.
 *
 * No new npm dependency: this reads the dist output and inlines the single script
 * and stylesheet (fonts/images are already data: URIs thanks to the high
 * assetsInlineLimit in vite.demo.config.ts). Run AFTER `vite build`.
 *
 *   node demo/app/build-singlefile.mjs        # from the frontend/ directory
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const dist = resolve(here, 'dist');
const outFile = resolve(dist, 'neuropathy-demo.html');

let html = readFileSync(resolve(dist, 'index.html'), 'utf8');

/** Read a dist asset referenced by an absolute-ish or relative href. */
function readAsset(ref) {
  const clean = ref.replace(/^\.?\//, '').split('?')[0];
  return readFileSync(resolve(dist, clean), 'utf8');
}

// Inline every <link rel="stylesheet" href="..."> as an inline <style>.
html = html.replace(
  /<link[^>]*rel=["']stylesheet["'][^>]*href=["']([^"']+)["'][^>]*>/gi,
  (_match, href) => `<style>\n${readAsset(href)}\n</style>`,
);

// Inline every module <script src="..."> as an inline module script.
html = html.replace(
  /<script([^>]*)\ssrc=["']([^"']+)["']([^>]*)><\/script>/gi,
  (_match, pre, src, post) => {
    const attrs = `${pre} ${post}`.replace(/\scrossorigin/gi, '').trim();
    const typeAttr = /type=/.test(attrs) ? attrs : `type="module" ${attrs}`.trim();
    return `<script ${typeAttr}>\n${readAsset(src)}\n</script>`;
  },
);

// Drop modulepreload hints — the module is inline now, nothing to preload.
html = html.replace(/<link[^>]*rel=["']modulepreload["'][^>]*>/gi, '');

writeFileSync(outFile, html);
const kb = Math.round(Buffer.byteLength(html) / 1024);
console.log(`WROTE ${outFile} (${kb} KB)`);
