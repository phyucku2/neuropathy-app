import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Mirror the product build's __APP_VERSION__ inject (the About screen reads it).
const pkg = JSON.parse(readFileSync(new URL('../../package.json', import.meta.url), 'utf-8')) as {
  version: string;
};

const here = fileURLToPath(new URL('.', import.meta.url));

// A one-file demo build: no code-splitting (inlineDynamicImports collapses every
// React.lazy chunk into a single JS bundle), no CSS splitting, and a huge inline
// limit so fonts/images become data: URIs — leaving exactly one JS + one CSS asset
// for build-singlefile.mjs to fold into a single self-contained HTML.
export default defineConfig({
  root: here,
  base: './',
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    cssCodeSplit: false,
    assetsInlineLimit: 100_000_000,
    modulePreload: { polyfill: false },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'assets/demo.js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
});
