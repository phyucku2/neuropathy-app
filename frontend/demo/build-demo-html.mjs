/**
 * Assemble the captured screenshots (./shots/*.png) into ONE self-contained HTML
 * walkthrough at docs/business/demo/app-demo.html — embedded base64 images, no network,
 * opens in any browser. Run capture.spec.ts first (see README).
 *
 *   node demo/build-demo-html.mjs        # from the frontend/ directory
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const shots = resolve(here, 'shots');
const outDir = resolve(here, '../../docs/business/demo');
const outFile = resolve(outDir, 'app-demo.html');

/** Ordered tour. `img` matches a file in ./shots (without .png). Cover has no img. */
const SLIDES = [
  {
    cover: true,
    title: 'Neuropathy Care Platform',
    subtitle: 'A guided walkthrough of the working app',
    body:
      'Every screen on the following pages is a real screenshot of the built application, ' +
      'captured running on synthetic demo data — no server, no real patient information. ' +
      'The platform turns daily function, lab results, and balance/gait metrics into one ' +
      'explainable, non-diagnostic trend a patient can share with their care team.',
  },
  {
    img: '01-login',
    eyebrow: 'Entry',
    title: 'Sign in',
    body:
      'Patients and clinicians share one secure entry (Argon2id + JWT, memory-only access ' +
      'tokens). The About and Privacy pages are reachable without an account, so a store ' +
      'reviewer or a curious visitor can read the disclaimers first.',
  },
  {
    img: '02-home-improving',
    eyebrow: 'Patient home',
    title: 'The 30-day trend, explained',
    body:
      'The hero states a direction (Improving) with a confidence meter — never a diagnosis. ' +
      '“What’s driving it” shows each signal with its SOURCE badge: self-reported check-in, ' +
      'BioMech balance, or an imported lab. Data gaps are named honestly. A standing ' +
      '“Not medical advice — share with your care team” line anchors every view.',
  },
  {
    img: '03-home-declining',
    eyebrow: 'Honesty',
    title: 'Truthful in both directions',
    body:
      'The same surface renders a declining trend without softening it, and shows ' +
      '“not enough data” instead of inventing a reassuring “stable”. The explanation is ' +
      'deterministic and sourced — there is no black-box score.',
  },
  {
    img: '04-trends',
    eyebrow: 'Trends',
    title: 'Each metric over time',
    body:
      'Per-signal charts let a patient (or clinician) see the trajectory behind the headline. ' +
      'When a measurement’s unit changes, the app refuses to compute a misleading delta and ' +
      'says so — research-grade integrity over a pretty number.',
  },
  {
    img: '05-checkin',
    eyebrow: 'Engagement',
    title: 'A 60-second daily check-in',
    body:
      'A few plain-language questions capture daily function. This is the adherence stream ' +
      'that a remote-monitoring (RTM) program is built on — captured with full provenance and ' +
      'a true local date, and queued offline if the connection drops.',
  },
  {
    img: '06-add',
    eyebrow: 'Data in',
    title: 'Bring your own data',
    body:
      'Patients can add a BioMech assessment report or a lab PDF. Every datum keeps its ' +
      'provenance (self-report vs device report vs EMR lab) — the raw material the trend, and ' +
      'any future billing evidence, is built from.',
  },
  {
    img: '07-settings',
    eyebrow: 'Control',
    title: 'Sources, consent & privacy',
    body:
      'Per-stream, revocable consent; connect an EMR via SMART-on-FHIR; a patient-held ' +
      'share-with-clinic that clinicians cannot override; a daily reminder; a one-tap data ' +
      'export; and account deletion. The patient is in control by construction.',
  },
  {
    img: '08-about',
    eyebrow: 'Positioning',
    title: 'Non-diagnostic by design',
    body:
      'The in-app About/Privacy pages carry the non-diagnostic disclaimer, the IP/licensee ' +
      'line, and a plain-language privacy summary. The product is deliberately an enabler for ' +
      'a care team, not a replacement for one.',
  },
  {
    img: '09-clinician-panel',
    eyebrow: 'Clinician',
    title: 'The care-team panel',
    body:
      'A clinician sees only the patients who have actively shared with them — consent is the ' +
      'gate, and it is the patient’s to give and revoke. No consent, no visibility.',
  },
  {
    img: '10-clinician-patient-detail',
    eyebrow: 'Clinician',
    title: 'The shared patient view',
    body:
      'For a consented patient, the clinician sees the same explainable trend and sourced ' +
      'signals — a shared, honest picture that supports a conversation rather than dictating ' +
      'a decision.',
  },
];

function dataUri(name) {
  const buf = readFileSync(resolve(shots, `${name}.png`));
  return `data:image/png;base64,${buf.toString('base64')}`;
}

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const slidesJson = JSON.stringify(
  SLIDES.map((s) => ({
    cover: !!s.cover,
    eyebrow: s.eyebrow ?? '',
    title: s.title,
    subtitle: s.subtitle ?? '',
    body: s.body,
    src: s.img ? dataUri(s.img) : '',
  })),
);

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Neuropathy Care Platform — App Walkthrough</title>
<style>
  :root {
    --ink:#12232e; --muted:#4a5b66; --faint:#7a8a94; --teal:#0e7c86; --teal-dark:#0a5c64;
    --green:#1f8a52; --line:#dbe4e7; --bg:#eef4f5; --card:#ffffff; --wash:#e7f3f4;
  }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; }
  body {
    font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; color:var(--ink);
    background:linear-gradient(160deg,#f4f9fa,#e5eef0); min-height:100%;
    display:flex; flex-direction:column;
  }
  header.top {
    display:flex; align-items:center; gap:10px; padding:14px 22px; border-bottom:1px solid var(--line);
    background:rgba(255,255,255,.7); backdrop-filter:blur(6px);
  }
  header.top .logo { width:22px; height:22px; border-radius:6px;
    background:linear-gradient(135deg,var(--teal),var(--teal-dark)); }
  header.top b { font-size:14.5px; letter-spacing:-.01em; }
  header.top .tag { margin-left:auto; font-size:11px; color:var(--faint); text-transform:uppercase; letter-spacing:.12em; }
  main { flex:1; display:flex; align-items:center; justify-content:center; padding:26px; }
  .stage { width:100%; max-width:1080px; display:grid; grid-template-columns:360px 1fr; gap:44px; align-items:center; }
  .phone {
    justify-self:center; width:340px; border-radius:34px; padding:12px; background:#0c1c24;
    box-shadow:0 24px 60px rgba(10,40,50,.28), inset 0 0 0 2px #223640; position:relative;
  }
  .phone::before { content:""; position:absolute; top:20px; left:50%; transform:translateX(-50%);
    width:96px; height:6px; border-radius:4px; background:#33474f; z-index:2; }
  .phone img { width:100%; display:block; border-radius:24px; background:#fff; }
  .copy .eyebrow { text-transform:uppercase; letter-spacing:.14em; font-size:11px; font-weight:700; color:var(--teal); }
  .copy h1 { font-size:30px; line-height:1.12; margin:.35em 0 .5em; letter-spacing:-.02em; }
  .copy p { font-size:15.5px; line-height:1.62; color:var(--muted); max-width:34em; margin:0; }
  .cover .phone { display:none; }
  .cover.stage { grid-template-columns:1fr; text-align:center; }
  .cover .copy { max-width:44em; margin:0 auto; }
  .cover .copy h1 { font-size:40px; }
  .cover .sub { font-size:17px; color:var(--teal-dark); font-weight:600; margin:-.2em 0 1em; }
  .cover .copy p { margin:0 auto; }
  footer.nav {
    display:flex; align-items:center; gap:16px; padding:16px 26px; border-top:1px solid var(--line);
    background:rgba(255,255,255,.7); backdrop-filter:blur(6px);
  }
  button.arrow {
    appearance:none; border:1px solid var(--line); background:#fff; color:var(--ink); cursor:pointer;
    font-size:14px; font-weight:600; padding:9px 16px; border-radius:10px; transition:.15s;
  }
  button.arrow:hover:not(:disabled) { border-color:var(--teal); color:var(--teal-dark); }
  button.arrow:disabled { opacity:.4; cursor:default; }
  .dots { display:flex; gap:8px; margin:0 auto; flex-wrap:wrap; }
  .dot { width:9px; height:9px; border-radius:50%; background:#c3d2d6; border:none; padding:0; cursor:pointer; transition:.15s; }
  .dot.on { background:var(--teal); transform:scale(1.25); }
  .counter { font-size:12.5px; color:var(--faint); min-width:52px; text-align:right; font-variant-numeric:tabular-nums; }
  .hint { font-size:11.5px; color:var(--faint); }
  .disc { text-align:center; font-size:11px; color:var(--faint); padding:0 26px 14px; }
  @media (max-width:820px) {
    .stage { grid-template-columns:1fr; gap:22px; }
    .phone { width:280px; }
    .copy { text-align:center; } .copy p { margin:0 auto; }
    .counter { display:none; }
  }
</style>
</head>
<body>
  <header class="top">
    <span class="logo"></span><b>Neuropathy Care Platform</b>
    <span class="tag">Product walkthrough · synthetic demo data</span>
  </header>
  <main><section id="stage" class="stage"></section></main>
  <footer class="nav">
    <button class="arrow" id="prev">← Back</button>
    <div class="dots" id="dots"></div>
    <button class="arrow" id="next">Next →</button>
    <span class="counter" id="counter"></span>
  </footer>
  <div class="disc">
    Screens are real captures of the built app on synthetic data. Not medical, billing, or legal
    advice; no real patient information. Prepared by engineering.
  </div>
<script>
  const SLIDES = ${slidesJson};
  let i = 0;
  const stage = document.getElementById('stage');
  const dots = document.getElementById('dots');
  const counter = document.getElementById('counter');
  const prev = document.getElementById('prev');
  const next = document.getElementById('next');

  SLIDES.forEach((_, n) => {
    const d = document.createElement('button');
    d.className = 'dot'; d.setAttribute('aria-label', 'Go to screen ' + (n + 1));
    d.onclick = () => go(n); dots.appendChild(d);
  });

  function render() {
    const s = SLIDES[i];
    stage.className = 'stage' + (s.cover ? ' cover' : '');
    if (s.cover) {
      stage.innerHTML =
        '<div class="copy">' +
          '<h1>' + s.title + '</h1>' +
          (s.subtitle ? '<div class="sub">' + s.subtitle + '</div>' : '') +
          '<p>' + s.body + '</p>' +
        '</div>';
    } else {
      stage.innerHTML =
        '<div class="phone"><img alt="' + s.title + '" src="' + s.src + '"></div>' +
        '<div class="copy">' +
          (s.eyebrow ? '<div class="eyebrow">' + s.eyebrow + '</div>' : '') +
          '<h1>' + s.title + '</h1>' +
          '<p>' + s.body + '</p>' +
        '</div>';
    }
    [...dots.children].forEach((d, n) => d.classList.toggle('on', n === i));
    counter.textContent = (i + 1) + ' / ' + SLIDES.length;
    prev.disabled = i === 0; next.disabled = i === SLIDES.length - 1;
  }
  function go(n) { i = Math.max(0, Math.min(SLIDES.length - 1, n)); render(); }
  prev.onclick = () => go(i - 1);
  next.onclick = () => go(i + 1);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); go(i + 1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); go(i - 1); }
  });
  render();
</script>
</body>
</html>
`;

mkdirSync(outDir, { recursive: true });
writeFileSync(outFile, html);
const kb = Math.round(Buffer.byteLength(html) / 1024);
console.log(`WROTE ${outFile} (${kb} KB, ${SLIDES.length} slides)`);
