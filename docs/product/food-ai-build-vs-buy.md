# Food-image AI for patient food logging (V2) — build vs. buy vs. hybrid

> **Research synthesis, not clinical, regulatory, or procurement advice.** This informs a
> non-diagnostic V2 food-logging feature. Every factual claim carries its source; anything
> unverified or time-sensitive is flagged. Vendor pricing changes frequently — reconfirm
> before budgeting. Cost-model token math is our own estimate (§4), labelled as such.

## Bottom line (read this first)

For a cost-conscious, non-diagnostic, HIPAA-relevant food-logging V2 that is **already on
Azure with Azure OpenAI (GPT-4o)**, the evidence favors a **GPT-4o-vision + free-nutrition-
database hybrid** over both a dedicated third-party food-AI API and a build-your-own model —
on cost, accuracy, and compliance flexibility.

1. **Dedicated food APIs are neither cheap nor accurate at single-guess food ID.** In the
   only standardized head-to-head benchmark, the best platform (Calorie Mama) reached only
   **62.9% top-1**, and most were far worse (Foodvisor 46.2%, LogMeal 24.2%). Pricing is
   largely subscription/enterprise-gated (Nutritionix **$499–$1,850+/mo**; Calorie Mama
   contact-only), not cheap per-call.
2. **A general VLM now matches or beats the dedicated APIs** with no custom training: a
   zero-shot GPT-4-Vision pipeline grounded in a free USDA database hit **47.7 kcal MAE** vs
   Foodvisor's **168 kcal**. Since we already pay for GPT-4o on Azure, this is the cheapest
   path at low/medium volume.
3. **Quantitative accuracy is the unsolved gap for _every_ option.** Portion/macro error is
   large across the board (GPT-4o ~23–36% macro error; residual calorie MAE >100 kcal even
   with metadata; protein MAPE 60%+). **No current option is clinical-grade** → position
   food logging as **estimation, not measurement**, with a human confirm/edit step. This
   matches our existing non-diagnostic framing.
4. **Split the architecture by food type.** Free **barcode** scanning (Open Food Facts) for
   packaged foods and **text/NL** logging carry a large share of real-world logs; reserve
   **image recognition (GPT-4o)** for prepared/plated meals where there is no barcode.
5. **Compliance leans the same way.** Microsoft signs a **BAA covering Azure OpenAI** — a
   concrete advantage. **No** dedicated food vendor's BAA/HIPAA posture could be confirmed
   from public sources; all would need direct confirmation.

---

## 1. Vendor pricing & HIPAA posture

All figures fetched **2026-07-17**; vendor pages are mostly undated and change often —
**reconfirm before budgeting.**

| Vendor | Model | Published price | Free tier | BAA/HIPAA |
|---|---|---|---|---|
| **Nutritionix** | Per-MAU, billed annually | Starter **$499/mo** (≤200 MAU), MVP **$999/mo** (≤1000 MAU), Unicorn from **$1,850/mo** | Business Trial (≤2 MAU) | Not published — confirm |
| **Passio Nutrition-AI** | Token-based, on-device SDK | **$2.50/M** tokens (1–20M) → **$2.35/M** (500M+); auto-refills flat $2.50/M (volume discount **not** applied); >50k active users → custom | — | Not published — confirm |
| **LogMeal** | Credit-based | Food recognition = 1 credit; nutrition/recipe = 0 extra | Trial: 30 days **or** 200 queries, 5 users, no card | Not published — confirm |
| **Calorie Mama (Azumio)** | Contact-only | **Not disclosed** | None disclosed | **Nothing disclosed** |
| **Edamam** | (in scope) | **No verified pricing surfaced** — genuine gap | — | Confirm |
| **Azure OpenAI (GPT-4o)** | Per-token (image → input tokens) | ~$2.50/1M input, ~$10/1M output (see §4) | Pay-as-you-go | **Microsoft signs a BAA** covering Azure OpenAI |

> ⚠️ **Passio "refill" caveat:** the tiered $2.50→$2.35 rates are for volume *purchases*;
> auto-refills are billed flat at $2.50/M with the volume discount **not** applied. A claim
> that a single recognition request consumes ~3,000–5,000 Passio tokens **did not survive
> verification** — do not budget on it.

Sources: nutritionix.com/api, passio.ai/cost-breakdown, logmeal.com/api/pricing,
caloriemama.ai/api, azure.microsoft.com/pricing/details/azure-openai,
learn.microsoft.com (Azure OpenAI HIPAA/BAA).

---

## 2. Accuracy — what the benchmarks actually show

**Food identification (which food is it):**
- Only standardized head-to-head of the commercial APIs (JMIR Formative Research, **Dec
  2020**, 185 images, 7 platforms): top-1 ranged **62.9% (Calorie Mama)** → 46.2%
  (Foodvisor) → 24.2% (LogMeal) → 9.1% (Google Vision). Even the best misidentified >⅓ at
  top-1. **~5.5 years old — stale for current vendor models.**
- General VLMs on fine-grained ID (FoodNExTDB, Apr 2025): strong at coarse category
  (Gemini 2.0 Flash 85.8%, GPT-4o 80.7%) but **degrade sharply** with subcategory (→69.9%)
  and cooking style (→42.4%). Single-item images ~90–95%; **multi-item plates drop to
  ~76–82%.** This ceiling applies to **any** image approach — buy, build, or GPT-4o.

**Nutrition estimation (how much / macros) — the hard part:**
- Peer-reviewed (PMC12513282, 2025, 52 standardized photos): energy MAPE **35.8%** for both
  GPT-4o and Claude 3.5 Sonnet (64.2% Gemini 1.5 Pro); macro errors far larger — protein
  MAPE **60.7%** (GPT-4o), carbs 47.9–72.8%, fat 41.7–89.6%. Authors: general LLMs are **"not
  yet suitable for precise dietary assessment."**
- Dietitian-verified ACETADA (arXiv 2507.07048, Jul 2025): GPT-4o baseline calorie MAE
  **165.77 kcal**, improving only to ~154 kcal **even with GPS + food metadata**. Adding
  cheap context (timestamp, location, known items) cut avg calorie MAE ~76 kcal and portion
  error ~53 g — a **real but modest** lever that does not close the gap.
- Zero-shot GPT-4-Vision + USDA RAG (DietAI24, Nature Comms Medicine, Nov 2025): energy MAE
  **47.7 kcal** vs Foodvisor 168 kcal, Calorie Mama 277 kcal. (Developer-run eval; Foodvisor
  did not participate — favorable to the method, so treat 47.7 as best-case not guaranteed.)

**Takeaway:** the strongest *independent* evidence (PMC12513282, ACETADA) and the
method-favorable evidence (DietAI24) deliver the **same** message — coarse ID is workable,
**quantitative macros are not clinical-grade in any option.**

---

## 3. Build-your-own — why it's hard to justify

- Datasets exist (Food-101, **Nutrition5k** RGB-D per-dish mass/macros, Recipe1M+, plus free
  **USDA FoodData Central** and **Open Food Facts**), but portion/volume estimation from a
  single 2-D photo is the core unsolved difficulty — the same wall GPT-4o hits.
- The decisive point: **zero-shot GPT-4o already matches or beats dedicated models without
  any training** (§2). Building from scratch takes ML staff, labeling, GPU training +
  ongoing inference hosting, and a validation program — to land *at best* where the
  already-paid-for GPT-4o path lands. **Not justified for a cost-conscious V2.**
- No surviving claim quantified a specific own-model accuracy ceiling or training/hosting
  cost — but the direction is clear enough to defer building indefinitely.

---

## 4. The recommended hybrid — architecture & cost

**Pipeline:**
1. **Barcode first** (packaged foods) → Open Food Facts (free) → exact label macros. Highest
   accuracy, near-zero cost, covers a large share of real logs.
2. **Text / natural-language entry** → USDA FoodData Central (free) for the long tail of
   known foods the user can name.
3. **Photo → GPT-4o-vision** (Azure, under our existing BAA) for prepared/plated meals only.
   GPT-4o returns **food items + estimated portions**; we map items to **USDA/Open Food
   Facts** for the macros (grounding, per DietAI24). Enrich the prompt with cheap context
   (meal time, user history, any barcode/text hints) for the modest accuracy lever.
4. **Human confirm/edit step, always.** Ranged estimates, no false micronutrient precision,
   never for insulin dosing — consistent with the app's non-diagnostic stance.

**Per-photo GPT-4o cost — _our own estimate_, confirm against current Azure pricing.** GPT-4o
converts an image to input tokens (~85 base + 170/512-px tile; a ~1024×1024 food photo ≈ 4
tiles ≈ **~765 image tokens**). With a ~500-token prompt and ~300-token JSON reply:

- Input ≈ 1,265 tok × $2.50/1M ≈ **$0.0032**; output ≈ 300 tok × $10/1M ≈ **$0.0030**
- **≈ $0.006 per photo-log** (round to ~$0.006–0.010 for headroom).

| Monthly photo-logs | GPT-4o hybrid (≈$0.006–0.01/photo) | Nutritionix (flat MAU tiers) | Notes |
|---|---|---|---|
| **1,000** | **~$6–10/mo** | $499+/mo | free DBs $0; barcode/text logs ≈ $0 |
| **10,000** | **~$60–100/mo** | $999+/mo | |
| **100,000** | **~$600–1,000/mo** | $1,850+/mo (Unicorn) | at true scale, revisit on-device/dedicated |

The hybrid is **dramatically cheaper at low/medium volume** because barcode + text logs cost
≈$0 and only plated-meal photos hit the paid model. Dedicated APIs charge a flat monthly
floor regardless of volume. **Confirm the exact per-image token count against current Azure
OpenAI GPT-4o vision pricing before committing budget** — the image-tile token math is our
estimate, not a verified vendor figure.

---

## 5. On-device / PHI note

- **Passio's SDK can run recognition on-device** — the photo never leaves the phone, the
  strongest privacy story — but at a per-token cost, an unconfirmed BAA, and lower
  fine-grained accuracy than cloud GPT-4o. A future **hybrid-of-the-hybrid** (on-device
  pre-filter for easy/packaged items, cloud GPT-4o for hard plated meals) is worth
  revisiting at scale.
- For V2 on Azure, sending the photo to **Azure OpenAI under Microsoft's BAA** is the
  pragmatic compliant path; treat the food photo as PHI-adjacent and keep it out of PHI-free
  logs (consistent with ADR-0018).

---

## 6. Open questions to close before build

1. **Exact current per-image GPT-4o Azure cost** (image-tile token math at typical food-photo
   resolution) and the resulting bill at 1k/10k/100k — to finalize §4 (our estimate stands
   in for now).
2. **Which vendors will actually sign a BAA, and at what tier** (Passio, LogMeal, Foodvisor,
   Nutritionix, Edamam) — none confirmed from public sources.
3. **Edamam** current pricing / image capability / HIPAA posture — in scope but produced no
   verified evidence.
4. **On-device vs cloud PHI tradeoff** — does keeping the photo on-device (Passio) materially
   reduce compliance burden enough to offset higher cost and lower accuracy?

---

## Sources

Peer-reviewed / primary: PMC12513282 (2025); ACETADA (arXiv 2507.07048, 2025); DietAI24
(Nature Comms Medicine, 2025); FoodNExTDB (arXiv 2504.06925, 2025); JMIR Formative Research
7-platform benchmark (2020); Nutrition5k (arXiv 2103.03375). Vendor/primary: nutritionix.com/
api, passio.ai/cost-breakdown, logmeal.com/api/pricing, caloriemama.ai/api,
azure.microsoft.com/pricing/details/azure-openai, fdc.nal.usda.gov/api-guide, Open Food Facts.
January Food Benchmark (arXiv 2508.09966) is a vendor preprint — treated as directional only.

> Derived from the deep-research pass of 2026-07-17 (24 sources fetched, 94 claims extracted,
> 25 adversarially verified → 22 confirmed / 3 refuted). Refuted-and-excluded: the Passio
> per-request token figure, an over-specific Nutritionix MAU-cap claim, and a "no API can
> estimate portion size" claim.
