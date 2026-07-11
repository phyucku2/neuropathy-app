# Brand & Design System

**Decision:** ADR-0002. **Tokens:** `tokens.json` (canonical), `tokens.css` (web).
**Status:** v0.1 — colors estimated from BioMech Lab screenshots; reconcile against
BioMech Health's official brand guide when provided.

Our app is a licensed sibling of **BioMech Lab**, so it shares BioMech's visual family
— a navy/blue palette, a green primary-action accent, and a friendly geometric heading
face — while remaining our own product with our own screens, wordmark, and fonts.

## The IP line (read before touching brand)
- ✅ Share: color palette, typographic *character*, status-color semantics.
- ❌ Never: BioMech's **logo/wordmark** (their trademark), their exact **licensed
  fonts**, or pixel-copied **layouts/report templates** (clean-room rule).
- We ship our **own** neuropathy-app wordmark set in Poppins.

## Color palette

| Role | Token | Hex | Where it comes from |
|---|---|---|---|
| Brand navy | `brand.navy` | `#173A5E` | Header base, dark surfaces |
| Brand blue | `brand.blue` | `#2E6DA4` | Section bars, primary UI, links |
| Bright blue | `brand.blueBright` | `#2E86C8` | Header gradient, active accents |
| Sky | `brand.sky` | `#7FB0D4` | Info status, muted accents |
| Sky tint | `brand.skyTint` | `#E8F1F8` | App background |
| Action green | `action.green` | `#2F8F5B` | Primary buttons ("Run Custom Report") |
| Danger | `status.danger` | `#C63F4C` | Urgent / red-flag |
| Warning | `status.warning` | `#D68A34` | Expiring / caution |
| Neutral | `status.neutral` | `#1F4E79` | Expired / archived |
| Text primary | `text.primary` | `#233444` | Body text |
| Card | `surface.card` | `#FFFFFF` | Content cards |

## Typography

- **Display / headings — Poppins** (SIL OFL 1.1). Friendly geometric sans mirroring
  BioMech Lab's heading feel.
- **Body / UI / data — Inter** (SIL OFL 1.1). A screen-optimized face chosen for our
  **primary persona**: older adults, often with diabetic low vision. Legibility beats
  personality for body text here.
- **Baseline body size is 17px** (not the usual 14–16), and touch targets are **48pt**
  — both deliberate accessibility choices (see `tokens.json.a11y`).
- Both fonts are **self-hosted** (download the OFL files into the app), never hotlinked,
  and the OFL license text ships with the app.

## Accessibility contrast (WCAG 2.2 AA)
Verified pairings (ratios approximate):
- Text primary `#233444` on card `#FFFFFF` → ~12:1 ✅ (AAA)
- White on brand blue `#2E6DA4` → ~4.9:1 ✅ (AA)
- White on action green `#2F8F5B` → ~3.9:1 — **large text / buttons only** (AA large);
  do not use for small text.
- White on danger `#C63F4C` → ~4.6:1 ✅ (AA)
- White on navy `#173A5E` → ~11:1 ✅ (AAA)

> Any new color pairing must be contrast-checked before use. Status colors must never
> be the *only* signal (color-blind + low-vision users) — pair with icon + text label.

## Usage notes
- **Green = action, blue = brand/navigation, navy = structure.** Don't use green for
  non-actionable emphasis.
- Status colors carry the BioMech dashboard semantics (red urgent → amber soon → sky
  info → navy expired); reuse them consistently so clinicians moving between products
  read them the same way.
- A dark theme is required (2 a.m. logging persona) — a dark token set is a follow-up
  once the platform is chosen.
