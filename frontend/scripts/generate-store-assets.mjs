/**
 * Deterministic Play Store / Android visual-asset generator.
 *
 * Renders a single SVG brand mark — a circled dot-with-orbit "signal/tracking"
 * glyph derived from the app's ◍ wordmark aesthetic (src/components/AppShell.tsx)
 * — onto the brand navy→sky gradient (src/styles/tokens.css:
 * --color-brand-navy-deep #0f2a45 → --color-brand-blue-bright #2e86c8) and
 * screenshots it at every required size with Playwright's bundled Chromium
 * (no new dependencies; PLAYWRIGHT_BROWSERS_PATH is preinstalled).
 *
 * Outputs (idempotent — same filenames/paths every run, no manifest changes):
 *   - android/app/src/main/res/mipmap-*\/ic_launcher.png            (legacy launcher)
 *   - android/app/src/main/res/mipmap-*\/ic_launcher_round.png      (legacy round)
 *   - android/app/src/main/res/mipmap-*\/ic_launcher_foreground.png (adaptive foreground)
 *   - android/app/src/main/res/drawable*\/splash.png                (splash set)
 *   - docs/store-assets/icon-512.png                 (Play listing icon, 512×512)
 *   - docs/store-assets/feature-graphic-1024x500.png (Play feature graphic)
 *
 * The adaptive-icon FOREGROUND layer carries the full-bleed gradient + glyph:
 * the background layer is `@color/ic_launcher_background` (values XML), and this
 * script deliberately touches image files only — the full-bleed foreground fills
 * any launcher mask, so the XML color never shows.
 *
 * NO text in any icon. Run from frontend/:  node scripts/generate-store-assets.mjs
 */

import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const here = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(here, '..');
const RES = join(FRONTEND, 'android', 'app', 'src', 'main', 'res');
const STORE_ASSETS = join(FRONTEND, '..', 'docs', 'store-assets');

// Brand gradient stops — MUST mirror src/styles/tokens.css.
const NAVY_DEEP = '#0f2a45'; // --color-brand-navy-deep
const BLUE_BRIGHT = '#2e86c8'; // --color-brand-blue-bright
const GRADIENT = `linear-gradient(135deg, ${NAVY_DEEP} 0%, ${BLUE_BRIGHT} 100%)`;

/**
 * The brand mark: a ring with a deliberate gap, an orbiting dot sitting in the
 * gap, and a solid center dot — "signal being tracked around a center", a clean
 * medical-tracking read of the ◍ glyph. White on the brand gradient, no text.
 * ViewBox is 120×120 centered at (60,60).
 */
function glyphSvg() {
  const R = 34; // ring radius
  const pt = (deg, r = R) => {
    const a = (deg * Math.PI) / 180;
    return `${(60 + r * Math.cos(a)).toFixed(2)} ${(60 - r * Math.sin(a)).toFixed(2)}`;
  };
  // Visible arc: from 73° counterclockwise the long way round to 17°, leaving a
  // 56° gap centered at 45° (top-right) where the orbit dot sits.
  const arc = `M ${pt(73)} A ${R} ${R} 0 1 0 ${pt(17)}`;
  const [ox, oy] = pt(45).split(' ');
  return `
    <svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="">
      <path d="${arc}" fill="none" stroke="#ffffff" stroke-width="7" stroke-linecap="round"/>
      <circle cx="${ox}" cy="${oy}" r="7.5" fill="#ffffff"/>
      <circle cx="60" cy="60" r="13.5" fill="#ffffff"/>
    </svg>`;
}

/**
 * Compose one asset page: a `w`×`h` canvas with an optional gradient background
 * (or transparent), the glyph centered at `glyphFrac` of the short edge, and an
 * optional circular/rounded mask for legacy round icons.
 */
function assetHtml({ w, h, background, glyphFrac, radius = '0' }) {
  const glyphSize = Math.round(Math.min(w, h) * glyphFrac);
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    html, body { margin: 0; padding: 0; background: transparent; }
    .canvas {
      width: ${w}px; height: ${h}px;
      background: ${background};
      border-radius: ${radius};
      display: flex; align-items: center; justify-content: center;
      overflow: hidden;
    }
    svg { width: ${glyphSize}px; height: ${glyphSize}px; display: block; }
  </style></head><body><div class="canvas">${glyphSvg()}</div></body></html>`;
}

/** Feature graphic (1024×500): gradient, glyph, and the app wordmark. */
function featureGraphicHtml(poppinsDataUri) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    @font-face {
      font-family: 'Poppins';
      font-weight: 600;
      src: url('${poppinsDataUri}') format('woff2');
    }
    html, body { margin: 0; padding: 0; }
    .canvas {
      width: 1024px; height: 500px; background: ${GRADIENT};
      display: flex; align-items: center; justify-content: center; gap: 48px;
    }
    svg { width: 260px; height: 260px; display: block; }
    .wordmark {
      font-family: 'Poppins', sans-serif; font-weight: 600;
      font-size: 88px; color: #ffffff; letter-spacing: 1px;
    }
    .tagline {
      font-family: 'Poppins', sans-serif; font-weight: 600;
      font-size: 30px; color: rgba(255, 255, 255, 0.85); margin-top: 4px;
    }
  </style></head><body><div class="canvas">
    ${glyphSvg()}
    <div>
      <div class="wordmark">Neuropathy</div>
      <div class="tagline">Track what your body is telling you</div>
    </div>
  </div></body></html>`;
}

async function renderPng(page, { w, h, html, transparent, out }) {
  mkdirSync(dirname(out), { recursive: true });
  await page.setViewportSize({ width: w, height: h });
  await page.setContent(html, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: out, omitBackground: Boolean(transparent) });
  console.log(`wrote ${out} (${w}x${h})`);
}

async function main() {
  const { readFileSync } = await import('node:fs');
  const poppins = readFileSync(
    join(
      FRONTEND,
      'node_modules',
      '@fontsource',
      'poppins',
      'files',
      'poppins-latin-600-normal.woff2',
    ),
  );
  const poppinsDataUri = `data:font/woff2;base64,${poppins.toString('base64')}`;

  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  const jobs = [];

  // ---- Android launcher icons (exact existing sizes — no manifest change) ----
  // Legacy launcher: full-square gradient tile with a conventional rounded-corner
  // mask (transparent corners); round: full circle.
  const MIPMAP = { mdpi: 48, hdpi: 72, xhdpi: 96, xxhdpi: 144, xxxhdpi: 192 };
  for (const [density, size] of Object.entries(MIPMAP)) {
    jobs.push({
      w: size,
      h: size,
      transparent: true,
      out: join(RES, `mipmap-${density}`, 'ic_launcher.png'),
      html: assetHtml({ w: size, h: size, background: GRADIENT, glyphFrac: 0.62, radius: '18%' }),
    });
    jobs.push({
      w: size,
      h: size,
      transparent: true,
      out: join(RES, `mipmap-${density}`, 'ic_launcher_round.png'),
      html: assetHtml({ w: size, h: size, background: GRADIENT, glyphFrac: 0.6, radius: '50%' }),
    });
  }

  // Adaptive-icon foreground layer (108dp canvas per density; glyph kept well
  // inside the central 66dp safe zone; gradient is full-bleed — see header note).
  const FOREGROUND = { mdpi: 108, hdpi: 162, xhdpi: 216, xxhdpi: 324, xxxhdpi: 432 };
  for (const [density, size] of Object.entries(FOREGROUND)) {
    jobs.push({
      w: size,
      h: size,
      transparent: false,
      out: join(RES, `mipmap-${density}`, 'ic_launcher_foreground.png'),
      html: assetHtml({ w: size, h: size, background: GRADIENT, glyphFrac: 0.42 }),
    });
  }

  // ---- Splash screens (exact existing sizes/paths) ----
  const SPLASH = {
    drawable: [480, 320],
    'drawable-land-mdpi': [480, 320],
    'drawable-land-hdpi': [800, 480],
    'drawable-land-xhdpi': [1280, 720],
    'drawable-land-xxhdpi': [1600, 960],
    'drawable-land-xxxhdpi': [1920, 1280],
    'drawable-port-mdpi': [320, 480],
    'drawable-port-hdpi': [480, 800],
    'drawable-port-xhdpi': [720, 1280],
    'drawable-port-xxhdpi': [960, 1600],
    'drawable-port-xxxhdpi': [1280, 1920],
  };
  for (const [dir, [w, h]] of Object.entries(SPLASH)) {
    jobs.push({
      w,
      h,
      transparent: false,
      out: join(RES, dir, 'splash.png'),
      html: assetHtml({ w, h, background: GRADIENT, glyphFrac: 0.28 }),
    });
  }

  // ---- Play listing assets ----
  jobs.push({
    w: 512,
    h: 512,
    transparent: false,
    out: join(STORE_ASSETS, 'icon-512.png'),
    // Play requires a full-bleed square (Play applies its own corner mask).
    html: assetHtml({ w: 512, h: 512, background: GRADIENT, glyphFrac: 0.62 }),
  });
  jobs.push({
    w: 1024,
    h: 500,
    transparent: false,
    out: join(STORE_ASSETS, 'feature-graphic-1024x500.png'),
    html: featureGraphicHtml(poppinsDataUri),
  });

  for (const job of jobs) {
    await renderPng(page, job);
  }

  await browser.close();
  console.log(`\n${jobs.length} assets generated.`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
