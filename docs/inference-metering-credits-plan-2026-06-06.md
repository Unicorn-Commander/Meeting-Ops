# UC Suite Inference Metering + Unicorn Credits — design brief

> Design-swarm output 2026-06-06 (7 agents). PLAN ONLY. Meeting-Ops claims file:line-verified; other apps are assumptions.

The key claims check out against the repo. Critical confirmations for the brief:

- `impl_llm.py:80-85` discards `result["usage"]` (reads `choices[0]` only) — verified, all three call paths (async/sync/stream).
- `uploads.py:1710` `direct = None if llm_model else _direct_summarizer_provider()` — but note the bypass only fires when `MEETING_OPS_LLM_URL`+`MEETING_OPS_LLM_MODEL` env are BOTH set (`:1632-1635` returns None otherwise). So it's the default path *when configured*, else it already falls through to `get_llm()`. Worth a precise note.
- `registry.py:79-81` `get_api_key` decrypt-failure silently returns `DEFAULT_LITELLM_API_KEY` — the fail-open BYOK leak the review flagged is REAL and verbatim.
- `default_llm()` (`registry.py:84+`) constructs raw `LiteLLMProvider` on system key for org-less calls — the un-attributable egress is real.
- `get_llm(` grep = 18 (the unified-model's "22" counts `default_llm` fallbacks + duplicates; 18 is the literal `get_llm(` count). I'll say "~18-22 call sites" to avoid overcommitting.
- Tier flags all confirmed: `byok_models` enterprise-only (`:197`), `agent_write_basic:True` free+basic (`:52/99`), `qwen36_summary`/`canonical_reprocess` pro+.
- Reprocess Redis counter `_add_org_audio_hours` INCRBYFLOAT + midnight TTL, **fail-open** (`:84` returns 0.0 on error) — confirmed, and the fail-open posture matters for the review's "cap must be load-bearing" point.

I have what I need. Writing the founder brief.

---

# UC Suite Inference Metering & Unicorn Credits — Founder Brief

**For:** Aaron · **Date:** 2026-06-06 · **Status:** design, nothing built · Meeting-Ops claims are `file:line`-verified; other apps are ASSUMPTIONS (only the MO repo was readable).

The whole point: **every inference call resolves at one chokepoint into Free / Metered / BYOK, credits debit only for the heavy-or-our-external-key tier, only on success, exactly once — and the browser-first moat is enforced in the billing layer itself, so there is no code path where a $0 browser action can ever debit a credit.**

---

## 1. The metering model (the recommendation)

- **Four cost tiers, decided once at the provider boundary.** **T0 Browser** (WebGPU/transformers.js — user's hardware, never reaches our server, $0, the moat). **T1 Light-our-GPU** (embeddings, rerank, small ≤3B agents — free but **capped**). **T2 Heavy-or-external** (big models on our GPUs *or* our Anthropic/OpenAI/OpenRouter/Lambda keys — **metered**). **T3 BYOK** (org's own key — **0 debit**, logged for analytics).
- **Meter at one chokepoint, not 18-22 call sites.** A `MeteredProvider` wrapper returned by `registry.get_llm()` / `get_stt` / `get_diarization` / `get_embeddings`. It classifies the tier, calls through, reads the provider's usage, debits credits for T2 only. The 18-22 existing call sites stay unchanged.
- **Three real plumbing fixes before anything meters** (all verified): (a) we **throw away `result["usage"]` on every call today** (`impl_llm.py:80-85` reads `choices[0]` only) — stash it instead; (b) the default per-meeting summary path **bypasses the registry** via `_direct_summarizer_provider` (`uploads.py:1710`, when `MEETING_OPS_LLM_URL` is set) — route it through the wrapper; (c) a CI guard banning raw `LiteLLMProvider(` outside the registry + closing `default_llm()` (org-less raw provider) and the BYOK decrypt-fail leak below.
- **Free Meeting-Ops, concretely:** live STT (Parakeet 0.6B) + live summary (Qwen3-0.6B) in-browser = T0, **already shipped, free every tier** — keep as-is. The local **`meeting-rag` basic agent** answering over your stored transcripts on the small model = T1, free for Free+Basic (`agent_write_basic:True`, `tier.py:52/99`) — **this is "basic agents are free."**
- **Metered Meeting-Ops, concretely:** the high-quality **completion pass** (Parakeet 1.1B + pyannote + Qwen3.6-35B, ~30-90 GPU-sec) is **bundled-free in Pro** (already `qwen36_summary`/`canonical_reprocess` gated to Pro+) and **sold as a one-off credit buy to Free/Basic** (clean upsell). **Extra reprocesses, large-context RAG, vision, and anything on our external keys = credits.**
- **BYOK = the customer's bill, no debit** — decided purely by whether their `OrgProviderSettings` key is present and decrypts. Today this is Enterprise-only (`byok_models:True` at `tier.py:197` only); **recommend loosening to Pro+** so heavy users self-serve their own spend instead of churning. No per-call BYOK fee.
- **The bundled completion pass is governed by a queue, not a meter.** The existing **16h/day soft cap + fair Arq deferral** (`reprocess_workers.py`) is the cost control — the *meeting* is the billable unit, not the token. Extend that same one Redis counter to two more (free-agent-calls/day, heavy-GPU-seconds/day).
- **Fail-closed is the rule.** Any call the wrapper can't confidently classify, or whose BYOK key fails to decrypt, ⇒ **most-expensive tier or hard-block** — never silently free. (Real leak today: `registry.py:79-81` silently falls back to **our** system key when a BYOK key won't decrypt, which would bill as free.)

---

## 2. Per-app push: browser vs our-GPU vs metered

Meeting-Ops is verified. Everything else is **ASSUMPTION** (repo not readable) — directional, to confirm per app.

| App | Push to **Browser (free, T0)** | **Light-our-GPU (free/capped, T1)** | **Metered (T2)** |
|---|---|---|---|
| **Meeting-Ops** ✓ | Live STT + live summary (shipped) | `meeting-rag` basic agent, embeddings, titles/sentiment | Completion pass (bundled Pro / credits Free), extra reprocess, vision, external keys |
| **Contact-Ops** | Dedupe scoring + record classify via in-browser embeddings | Light field normalization | Org-graph-wide entity resolution at import; external enrichment |
| **Email-Ops** | Inbox triage / "needs reply?" (short, single-shot — ideal) | Light classify | Full-thread summarize, long-context drafting, cleaner batch |
| **Project-Ops** | Action-item/date extraction from a pasted note; task dedupe | Title cleanup | Project-wide rollups, status narratives, cross-doc RAG |
| **Crisis-Ops** | Minimal (confidentiality) | — | Prefer **local-T2 or BYOK only**, never shared external keys (case-file isolation) |
| **Customer/Accounting-Ops** | Light classify / embedding search | — | Doc generation (invoice-draft), heavy reasoning |

**Rule of thumb:** short + single-shot + English + "good-enough" → browser (free). Big context / multi-doc / high-accuracy / best-possible → leaves the browser → meterable. Apps with no browser leg only get T1-light as their "free."

---

## 3. Unicorn Credits — pricing, markup, and how it hits Accounting-Ops

- **1 credit = $0.01 of list value** (100 = $1). Ledger in integer **micro-credits** so sub-cent GPU passes don't round to zero; customers only see whole credits.
- **Flat credits per named action is the default rail** (e.g. meeting completion 1-3, deep-research 25-50, invoice-draft ~3) — legible to SMB buyers, decoupled from token-counting, and lets us silently re-rate the cost table as models improve. **Reject raw token passthrough as the customer-facing model** — it's a race to the bottom and illegible to this buyer.
- **Passthrough only for our-external-key calls**, at **markup 1.25-1.4×** measured provider cost (OpenRouter ~1.25 since they already take 5.5%; Anthropic/OpenAI ~1.35). Mark streaming/disconnect debits `estimated:true`.
- **The margin lives in the subscription, not the markup.** AI-SaaS gross margins run 50-60% (vs 80-90% classic SaaS); OpenRouter itself profits on a purchase fee, not inference markup. Credits mostly meter the long tail + overage; **most users never buy one.**
- **The "pricebook" is the structural moat.** A versioned, **Aaron-editable-without-deploy** table keyed `(app, action) → {free | flat-credits | passthrough×M, metered: bool}`. The wallet is consulted **only when `metered:true`** — free/browser/light short-circuit before the wallet exists. Promoting a free agent to a paid heavy model = flip one row, no code change.
- **Accounting-Ops impact — keep them separate.** **Stripe = money system-of-record** (native Stripe Billing Credits: included allowance = recurring Credit Grant in the seat; top-ups = one-time Checkout). **Internal ledger = consumption SoR.** **Credit purchases do NOT go through `create_invoice_from_draft`** — that tool is the org's *outbound* AR (what they bill *their* clients), not what they owe *us*. Customer-Ops is a **read-only burn-rate projection**, never the wallet.
- **Stripe constraints to respect** (verified current): the Meter Events API caps at **1,000 events/sec** and only backdates **35 days**, so **bill on our internal ledger and batch-summarize to Stripe async** (never 1:1 per call). Reconcile the internal double-entry ledger to itself as a hard invariant, and to Stripe within a **tolerance band** (not exact equality — holds/estimates legitimately diverge).

---

## 4. Phased build plan (Meeting-Ops first)

- **Phase 0 — Unblock (no behavior change).** Stop discarding `usage` (`impl_llm.py`), route the `_direct_summarizer_provider` default path through the registry (`uploads.py`), CI-guard raw `LiteLLMProvider(`, close `default_llm()` + the BYOK decrypt-fail-to-system-key leak. *Nothing meters until these land.*
- **Phase 1 — Classify + log, debit nothing.** Ship `MeteredProvider`; classify every server call T0-T3; write a `usage_events` table (idempotency key UNIQUE). **Run a full cycle log-only** to calibrate the pricebook against real usage before charging anyone — and to prove the wrapper covers 100% of egress.
- **Phase 2 — Pricebook + wallet.** Atomic wallet (`UPDATE … WHERE balance >= hold` — not read-then-write), reserve→settle→release on the shared request_id. **Turn debits on for exactly two things: extra/regenerate reprocess + our-external-key calls.** Bundled completion stays free-but-queued. **Ship the free-agent daily cap in this phase, not later.**
- **Phase 3 — Stripe credits + UX.** Recurring Credit Grant per tier + one-time top-up Checkout + webhook→wallet. "Usage & Credits" panel that **stays hidden until the user nears overage.** Daily reconciler.
- **Phase 4 — Generalize the queue-as-cost-control.** Extend the Redis counter to free-agent-calls + heavy-GPU-seconds; make the 16h cap tier-aware; wire the spill ladder (local → cheap OpenRouter 8B → Lambda burst → premium), all metered, BYOK short-circuiting.
- **Phase 5-6 — Customer-Ops projection + Lago, then per-app rollout** pointing at the **shared** wallet + pricebook (so Suite orgs pool credits automatically).

---

## Decisions for Aaron

1. **Credit price + markup.** Confirm **1 credit = $0.01** and the external-key markup band (recommend **1.25-1.4×**). Set the flat per-action prices: **meeting completion = 1-3 cr, deep-research = 25-50, invoice-draft = ~3** — your call on the exact numbers.
2. **Free-allowance lines.** Set the included credits per tier (proposed: Free **0**, Basic ~300, Pro ~1,500 ≈ 1,000 meetings, Suite ~2,500 pooled). And set **two hard caps the design needs from day one**: free-agent calls/day/org and the per-tier audio-hours cap (Pro > 16h, Enterprise unbounded). *The free agent is unbounded today — without a cap, 100 free users on the RAG agent saturate the same GPU your paying customers' completion pass runs on (~12.88 tok/s/user at 100 concurrent on a 3090). This cap is non-negotiable for Phase 1.*
3. **Which apps push browser-first first.** Meeting-Ops is done. Recommend **Email-Ops triage and Contact-Ops dedupe next** (best $0-browser fit). Confirm priority.
4. **BYOK tier + fee.** Loosen `byok_models` from Enterprise-only to **Pro+**, **no per-call fee** (value capture is the seat). Confirm — and confirm BYOK never bypasses a paid seat.
5. **Purchased-credit expiry (finance/legal).** "Never expire" creates an ASC-606 breakage liability **and a multi-state escheatment tail**. **Recommend purchased credits expire in 12-24 months** (included allowance stays use-it-or-lose-it). Your call, but make it with eyes open.
6. **Hardware reality behind the cost anchor.** The $0.02/meeting anchor assumes the **P40** runs the 35B summary — but **NVIDIA is dropping CUDA support for Pascal (frozen at 12.8/12.9, removed in 13.x)**. When the P40 ages out, the 35B pass moves to the 3090 (which can't comfortably batch it) and becomes the **first thing that spills to paid cloud GPUs**. Decide now: **what is the completion-pass cost — and does it stay Bucket-B-free or become metered — when the heavy model runs on Lambda rates instead of a free P40?** Also confirm whether **P40 + RTX 6000 stay in the heavy fleet at all** (the brief assumed "3060 + 3090"; the repo says otherwise).

**Review must-fixes folded in above:** free-tier cap as Phase 1 (Decision 2), fail-closed classification + BYOK-decrypt-leak close (§1, Phase 0), atomic wallet + estimated-streaming debits (Phase 2/§3), tolerance-band reconciliation + Stripe 1k/sec & 35-day limits (§3), P40/CUDA cost risk (Decision 6), purchased-credit expiry (Decision 5), pin free agents to the light model with no silent heavy-model escalation, and a `pending_credits` queue so a captured meeting is never stranded by an empty wallet mid-flow.

**Verified anchors:** `impl_llm.py:80-85` (usage discarded), `uploads.py:1623/1710` (registry bypass), `registry.py:79-81` (BYOK→system-key leak) + `:84+` (`default_llm` org-less raw provider), `tier.py:52/99/121/126/197` (free/Pro/BYOK gates), `reprocess_workers.py` (16h cap + fail-open Redis counter).