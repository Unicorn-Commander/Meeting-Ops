# Meeting-Ops — Knowledge Graph + Agent Chat: design + plan

> Design-swarm output, 2026-06-06. PLAN ONLY (no code written). Verified at HEAD `e26efc2` / v3.26.14.
> Adversarial-review must-fixes folded in. Decisions for Aaron are at the end of each section.

---

## Founder brief (decision-ready)

### Feature 1 — Knowledge Graph page

**Recommended approach.** Ship a minimal **Alternative A**: one Meeting-Ops-owned, hard-capped, org-filtered endpoint, **person-centric only**. Reuse the existing 3D viewer (`BrigadeGraphViewer.tsx`) as-is, hold node count under the WebGL-comfortable range with a server cap (250), and avoid a net-new 2D dependency. Topics/Decisions have no stable cross-meeting IDs (they're position-keyed: `meeting_ops_topic_{session_pk}_{idx}`), so person is the only graph view whose node identity is trustworthy today — which is *why* it goes first.

**First-iteration scope.** A `/knowledge-graph` page (ship-dark behind a flag, dogfood-first): for one selected confirmed-contact Speaker, render their meeting subgraph (their meetings + co-speakers + that meeting's topics/decisions/action-items), capped, org-filtered, with native click-through to `/sessions/{id}` and deep-links out to Brigade for whole-org / time-window / 360 views. Postgres is the tenancy boundary (resolve the speaker row org-scoped *before* any Brigade call; cross-org → 404). Four empty-states + an extended isolation test. **~5–7.5 dev-days.**

### Feature 2 — Agent Chat upgrade (model picker + rename)

**Recommended approach.** The headline ask is "let me swap the underlying chat model," but the real cost hole is upstream: `upsert_provider_setting` gates only on admin role (no tier check), so any Basic/Pro admin can drop in an external key that then bills every server LLM call. Lead with tier-gating external **provider config** (the key source), then add an enterprise-gated, allow-list-validated per-chat `model` override that is **local-models-only** (externals stripped at the source). Validation lives in the dispatcher (`dispatch_chat`), never the registry (the registry is also on the ungated upload path, so it can't be the trust boundary). The override is privilege-down-only: only an opaque, server-allow-listed model id crosses the wire — never an endpoint or key.

**First-iteration scope.** MF-1 provider-config gate → allow-list service → dispatcher `model` param (gated + validated) → plumb through `run_meeting_rag` → Open-WebUI-style grouped/typeahead `<AgentModelPicker>` (Local + Brigade groups only, override hidden unless enterprise) → rename "AI Chat" → "Agent chat". **~4–5 dev-days.** No registry change, no history-store change.

### What I'd build first across both
1. **MF-1 provider-config gate now** — small, UI-independent, closes the tier/cost-ownership gap; deploys ahead of everything.
2. **KG person-view v1** — highest visible "wow," pure $0-marginal client-side render; first answer the `per_org_graph` decision (it makes the safe path the easy path).
3. **Defer both unifies** (SessionDetails chat-history reconciliation; KG topic/time/NL views) to second PRs — they carry migration/IDOR/cost risk that shouldn't gate the first slices.

---

## Knowledge Graph — first-iteration build steps

1. **Backend endpoint** — NEW `backend/api/knowledge_graph.py`, `GET /api/knowledge-graph/person/{speaker_id}?hops={1|2}`. Same deps as the per-session endpoint (`recording.py:2475`). Tier gate `require_feature("brigade_integration")` (Pro+). **Postgres-first tenancy**: resolve `SpeakerProfile` by id AND `organization_id` first; cross-org → 404. Query is either A-native (new `BrigadeClient.query_graph()` + Cypher with `ALL(x IN nodes(p) WHERE x.org_id=$org)` per-hop guard) or A-fallback (reuse LIVE `fetch_entity_context` + Python cap, **safe only in `per_org_graph` mode`). Shaper strips `org_id`/`graph`/`tenancy_mode` on the wire. Cap via `KNOWLEDGE_GRAPH_NODE_CAP` (default 250) + `truncated` flag. ~1.5–2.5d.
2. **Frontend page** — NEW `frontend/src/pages/KnowledgeGraph.tsx`, reuse `BrigadeGraphViewer.tsx` as-is. Person typeahead (confirmed contacts only), hops toggle, click-through to `/sessions/{id}`, 4 empty-states. Nav + route in `AppRouterSimplified.tsx` behind `VITE_KNOWLEDGE_GRAPH_PAGE_ENABLED`. ~2–3d.
3. **Brigade deep-links** for whole-org/time/360 via existing `build_brigade_graph_url()` (note: `?graph=` param inert until a pending Brigade PR). ~0.5d.
4. **Dogfood flags** — `KNOWLEDGE_GRAPH_PAGE_ENABLED` + `VITE_...` true on magicunicorn.dev, `KNOWLEDGE_GRAPH_NODE_CAP=250`, confirm `BRIGADE_API_KEY` + per-org brigade.enabled + Pro+ tier; seed-verify against a confirmed repeat attendee (e.g. marcus@examplefirm.com). ~0.5d.
5. **Isolation test** — extend `backend/tests/test_cross_org_isolation.py` with the new graph endpoint (cross-org → 404; no foreign `org_id` on the wire) + a param-only-Cypher CI check. ~0.5–1d.

**Later:** topic-centric (needs stable Topic/Decision IDs), time-window, path-between-people, 2D/large-graph render tier, /rag↔graph integration, lazy expand-on-click. **Cut from v1:** NL "ask the graph in English" (per-interaction LLM call breaks the $0-marginal moat).

### Decisions for Aaron — Knowledge Graph
1. **Native-vs-Brigade Cypher.** A-native keeps `org_id` enforcement in MO's domain but needs a new Brigade authenticated Cypher route + `BrigadeClient.query_graph()` (neither exists; cross-team handshake). A-fallback reuses live `fetch_entity_context` but is only structurally safe in `per_org_graph` mode.
2. **Tenancy mode.** Default is `shared` (isolation by `org_id` property — one missing WHERE-clause from a leak). `per_org_graph` = physically separate graph per org. Recommended for paying customers; also makes A-fallback safe and collapses Decision 1.
3. **NL graph-query** cut from v1 (moat). Confirm it stays out.
4. **Tier line** — v1 is clean Pro+ (free/basic 403). Keep clean, or a Basic single-meeting teaser as an upgrade lever?

---

## Agent Chat — first-iteration build steps

1. **MF-1 (security prereq)** — `backend/api/provider_settings.py`: after the admin check (line 140), if configuring an **external** LLM provider, require `byok_models` (enterprise) via `gate_feature_for_caller`. Add `EXTERNAL_LLM_PROVIDERS` set next to `VALID_PROVIDERS`. Ships ahead of the UI. ~0.5d.
2. **Allow-list service** — extract `_build_available_models`/`_is_local_model_id` from `system_caps.py` into NEW `backend/services/providers/model_catalog.py` + `resolve_allowed_model_ids(org_id, db)`. `/api/system/pipeline` shape unchanged. ~0.5d.
3. **Dispatcher param** — `backend/api/agents.py`: `ChatRequest.model: Optional[str]`. In `dispatch_chat`, before the meeting-rag branch: ignore for Brigade agents; for meeting-rag gate on `byok_models` + validate against `resolve_allowed_model_ids` (400 if not local-allow-listed). Validation here, never in the registry. ~1d.
4. **Plumb through** — `backend/services/agents/meeting_rag.py`: `run_meeting_rag(model=...)` → `get_llm(org_id, task="chat", model_override=model)` (registry already correct). Must ship with Step 3 or the picker is a silent no-op. ~0.5d.
5. **Picker** — NEW `frontend/src/components/AgentModelPicker.tsx` (Open-WebUI-style grouped + typeahead; Local + Brigade groups only; model override in an "Advanced" disclosure, hidden unless enterprise, disabled for Brigade agents). Wire `RAGChat.tsx` + `AskBar.tsx`. ~1.5–2d.
6. **Rename** "AI Chat" → "Agent chat" (labels only; route stays `/rag`). ~1–2h.

**Later (PR 2):** session-aware agent history + reconcile the `__rag__` vs `__meeting_rag_agent__` split (UNION-on-read grace window); SessionDetails Chat tab → dispatcher with org-scoped `scope.session_id` (`_resolve_session`, avoid IDOR); deprecate `ai_chat.py` generation endpoints to SSE→`AIResponse` shims (preserve the MCP httpx JSON contract).

### Decisions for Aaron — Agent Chat
1. **MF-1 gate** — confirm external-provider config requires enterprise (`byok_models`). Whoever sets the external key owns its per-token spend (tensions the browser-first moat).
2. **Chat model ceiling** — override is enterprise-only AND local-allow-list-only (even an enterprise org with an Anthropic key can't pick `claude-*` from chat). Keep local-only for v1, or let enterprise chat to their external model?
3. **Drop "Raw models" picker arm** from v1 (today it's just one provider's local catalog; confusing). Confirm Local + Brigade only.
4. **Split SessionDetails unify into PR 2** (incompatible history keys + IDOR risk on `scope.session_id`). Confirm.
