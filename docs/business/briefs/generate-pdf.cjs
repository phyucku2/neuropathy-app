/**
 * Regenerate a brief PDF from its committed HTML source.
 *
 * Usage:
 *   NODE_PATH=<repo>/frontend/node_modules node docs/business/briefs/generate-pdf.cjs <name>
 * where <name> is one of the brief basenames in this directory, e.g.:
 *   ... generate-pdf.cjs product-and-technology-brief
 *   ... generate-pdf.cjs cto-brief
 *   ... generate-pdf.cjs build-inventory
 *   ... generate-pdf.cjs compliance-officer-brief
 *
 * Requires Chromium via @playwright/test (already a frontend devDependency). The
 * HTML sources are self-contained (inline CSS, print styles) so no network is needed.
 * The rendered PDF is written next to the HTML with a Title-Cased filename.
 */
const path = require('path');
const { chromium } = require('@playwright/test');

const name = process.argv[2];
if (!name) {
  console.error('usage: generate-pdf.cjs <brief-basename>');
  process.exit(1);
}

const dir = __dirname;
const html = path.join(dir, `${name}.html`);
const out = path.join(dir, `${name}.pdf`);

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto('file://' + html, { waitUntil: 'networkidle' });
    await page.pdf({ path: out, printBackground: true, preferCSSPageSize: true });
    console.log('WROTE', out);
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
