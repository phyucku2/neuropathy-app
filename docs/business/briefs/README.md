# Briefs

Presentation-grade briefs about the platform, kept as **self-contained HTML sources**
(inline CSS + print styles) so they are versioned, diffable, and regenerable as PDFs on
demand. These were previously produced only as throwaway PDFs in a session scratchpad;
they are committed here so the work is not lost when an ephemeral environment is
reclaimed.

> These briefs are prepared by engineering as orientation. They are **not** billing,
> legal, regulatory, or investment advice, and they make **no claim of compliance,
> certification, or FDA clearance**. Every figure in the reimbursement/compliance
> material is for a qualified professional to validate. See
> [`../../compliance/gap-register/`](../../compliance/gap-register/) for the honest
> control posture.

## The briefs

| File | Audience | What it is |
|---|---|---|
| [`product-and-technology-brief.html`](./product-and-technology-brief.html) | Investor / general | What the platform is, the problem, the architecture at a glance, status, and the ask. |
| [`cto-brief.html`](./cto-brief.html) | Technical / CTO diligence | System design, data model, security posture, testing/CI, and technical risks. |
| [`build-inventory.html`](./build-inventory.html) | Internal | Everything built so far (features, endpoints, ADRs) plus the prioritized to-do list. |
| [`compliance-officer-brief.html`](./compliance-officer-brief.html) | Compliance reviewer | Orientation for the reimbursement compliance review (D1–D3, assertions A1–A8). Pairs with [`../../product/reimbursement-signoff-packet.md`](../../product/reimbursement-signoff-packet.md). |

## Regenerating a PDF

The HTML is the source of truth; a PDF is a render. Chromium ships via the frontend's
`@playwright/test` devDependency (no `playwright install` needed in this environment).

```sh
# from the repo root, after `npm ci` in ./frontend
NODE_PATH="$PWD/frontend/node_modules" node docs/business/briefs/generate-pdf.cjs product-and-technology-brief
```

Swap the last argument for any brief basename. The PDF is written next to the HTML.
`*.pdf` in this directory is gitignored — regenerate rather than commit binaries.

## Keeping them honest and current

These are point-in-time snapshots. When the underlying facts change, update the HTML
source in the same PR as the change (the same discipline as the ADRs and
`roadmap-status.md`). The living, always-current records are:

- [`../../roadmap-status.md`](../../roadmap-status.md) — wave/portion status
- [`../../decisions/`](../../decisions/) — the ADR trail
- [`../../compliance/gap-register/`](../../compliance/gap-register/) — control posture
