# PHASE 1 STEP 2.3 — C-02 Sub-contract Matrix

> Status: DOCUMENTATION ONLY. All three sub-contracts OWNER DECISION: PENDING. Nothing implemented,
> no source/schema/API/ranking change, no commit/push. Date (UTC): 2026-09-27.
> Cross-contract rule preserved: FACTS → DERIVED STATE → DECISION/RANKING → EXPLANATION.
> LLM output is never source of truth for palette/fit/mood; missing evidence stays missing.

| Sub-contract | Evidence exists? | Deterministic now? | Ranking eligible? | Migration? | API change? | Owner decision |
|---|---|---|---|---|---|---|
| C-02-P Palette | YES — 17 `colors` codes (0005), per-item `color_id`, `_color_points` + neutral set | YES — monochrome frozen by reference; warm/cool proposed, approval required | LOCKED: ranking SIGNAL +5 (budget Option A) | No | No | LOCKED — IMPLEMENTED (Step 2.8; map `c02-p/1`) |
| C-02-F Fit | YES — nullable `fit`+`fit_confidence` on `wardrobe_items` (0023) + vision evidence persisted at save | YES — threshold 0.6 LOCKED; request map frozen (tailored unsupported) | LOCKED + IMPLEMENTED (Step 2.11): evidence-gated SIGNAL +5, gate only | Migration `0023` applied in code (PG run: BLOCKED here) | Additive optional fields (old clients unaffected) | LOCKED — IMPLEMENTED |
| C-02-M Mood | NO — zero backend mood data | N/A — context/explanation-only | LOCKED: 0, NOT a signal — CLOSED Step 2.12 (verified: no scoring/filter/weight/taxonomy/LLM; no code change needed) | No | No | CLOSED — LOCKED |

### Remaining implementation inputs (C-02-P + C-02-F implemented Step 2.8/2.11)
- Palette: warm/cool set freeze confirmation outstanding (implementation uses locked proposal).
- Fit: DONE (map `c02-f/1`, gate 0.6 LOCKED, weight +5 LOCKED, budget Option A live).
- Mood: none — no inputs outstanding; future taxonomy is separate work with its own contract.
- Budget rebalance: LOCKED — OPTION A, now live (35+5+5+5+5+5+5+5=70; caps/tie-break/hard constraints untouched).

### Recommended implementation order
1. **Palette** — complete data already persisted (`color_id` per item + vocab + scoring pattern);
   only the warm/cool set freeze + one weight stand between contract and implementation. No dependencies.
2. **Fit** — AFTER palette (same sub-term pattern reused; avoids concurrent weight changes) AND aligned
   with the C-06 sidecar direction (evidence must keep flowing into `image_ref`; no column per boundary).
   Needs map + threshold + weight approvals.
3. **Mood** — LAST: requires an entirely new approved taxonomy with a product-content gate (DEC-014 #22
   precedent); interim context-only behavior is already fully specified above, so nothing blocks on it.
   Keeps the fabrication risk (highest here) isolated until real data exists.
