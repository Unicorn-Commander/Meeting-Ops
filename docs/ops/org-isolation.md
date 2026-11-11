# Organization isolation (operator reference)

How Meeting-Ops keeps one organization's (org's) meetings away from another's,
as the code implements it today. Every claim below cites `file:line`. All names,
emails, and ids in examples are fictional placeholders (`example.com`).

This is an operator's map, not a threat model. It answers four questions:

1. How is the current org chosen for a request?
2. Which queries filter by org?
3. How is a session moved between orgs?
4. What does an operator run to prove isolation holds?

## 1. How the current org is chosen

Every org-scoped HTTP route depends on `get_current_organization`, which calls
`resolve_active_organization` (`backend/auth/dependencies.py:341-347`).

`resolve_active_organization` (`backend/auth/organization.py:237`) picks the org
in this order:

1. Explicit selector. A request may name a workspace with the
   `X-MeetingOps-Org` header (`ORG_HEADER_NAME`, `backend/auth/organization.py:17`)
   or the `?org=` / `?org_slug=` query params (`ORG_QUERY_PARAM_NAMES`,
   `backend/auth/organization.py:18`), read by `get_requested_org_slug`
   (`backend/auth/organization.py:222-234`). The query params exist because
   browser WebSockets and media tags cannot set custom headers
   (`backend/auth/organization.py:227-228`).
2. No usable selector: fall back through a preference chain
   (`backend/auth/organization.py:281-314`): the user's server-side home
   workspace `User.default_organization_id` (`:296-305`), then the platform
   default org `DEFAULT_ORG_SLUG` when they are a member (`:306-314`), then
   their first membership (`:313`).
3. No memberships at all: auto-provision into the platform default
   (`backend/auth/organization.py:315-317`).

The selector is a convenience, never a security boundary
(`backend/auth/organization.py:244-254`). An unknown or inaccessible selector is
logged and dropped, and resolution falls back to the user's default rather than
404-ing or widening scope (`backend/auth/organization.py:256-279`).

The actual boundary is the membership check at the bottom of the resolver: if
the resolved org has no `UserOrganization` row for the caller and the caller is
not a superuser, it raises 403 (`backend/auth/organization.py:319-332`). The
role returned is `superuser` for superusers, otherwise the membership role
(`backend/auth/organization.py:334`).

Memberships come from Keycloak group claims, synced additively on login: claims
grant and refresh memberships but never prune them
(`backend/auth/organization.py:136-219`, additive note `:189-193`). A brand-new
user with no claims gets a private personal org rather than being dumped into a
shared default (`backend/auth/organization.py:159-175`).

WebSockets reuse the same membership set: the handshake materialises
`user._org_ids` and a session-bound socket is admitted only when the session's
org is in that set (`backend/auth/ws_auth.py:140-149`, `:168-171`).

## 2. Which queries filter by org

The default list query is scoped by `organization_id` through
`_scoped_session_query` (`backend/api/simple_recording_db.py:394-397`), used by
the default branch of `list_sessions` (`backend/api/simple_recording_db.py:895-904`).

Two opt-in query flags widen scope, and both are constrained:

- `include_all_my_orgs=true` unions only the orgs the caller is a member of,
  for everyone including superusers (`backend/api/simple_recording_db.py:866-894`).
- `all_tenants=true` is a platform-admin god-view honored only for superusers
  and logged when used; silently ignored otherwise
  (`backend/api/simple_recording_db.py:840-865`).

Other read paths filter the same way:

- Session detail / lookup: `_scoped_session_query` / `_get_session_for_org`
  (`backend/api/simple_recording_db.py:637`, `:649`).
- Keyword search: scoped to the active org
  (`backend/api/simple_recording_db.py:1155`).
- Semantic (vector) search: passes `organization_id=active_org.organization.id`
  (`backend/api/simple_recording_db.py:1244`), which becomes a Qdrant payload
  filter in `_org_filter` (`backend/services/semantic_search_service.py:167-177`).
- Sessions router list: `RecordingSession.organization_id == active_org...`
  (`backend/api/sessions.py:35`).
- Analytics aggregates: every endpoint filters on the active org
  (`backend/api/analytics_simple.py:54`, `:176`, `:238`, `:309`, `:377`).

A cross-org read of another org's session returns 404 (not 403) so existence is
never revealed; this is the contract the tests pin (see section 4).

## 3. How a session is moved between orgs

Two routes reassign a session's org. Both live in
`backend/api/session_move_org.py`.

- `POST /api/simple/recording-sessions/{id}/move-org`
  (`backend/api/session_move_org.py:540-544`). Source org is the caller's active
  org. The caller must be admin/manager in the source org, the session creator,
  or a superuser (`_source_role_allows_move`, `:170-183`), and must be a member
  of the target org (`_target_membership_allows_receive`, `:186-203`).
- `PUT /api/simple/recording-sessions/{id}/organization`
  (`backend/api/session_move_org.py:512-516`). Resolves the session in any org,
  then requires the caller to have write access to it
  (`_user_can_write_session`, `:433-440`, enforced `:527-528`).

Both funnel into the same cascade. `_cascade_update`
(`backend/api/session_move_org.py:280-350`) rewrites `organization_id` on every
org-scoped child row (transcriptions, action_items, session_attachments,
session_collaborators, agent_sessions, audio_files, chat_history,
speaker_session_link, upload_jobs, tts_jobs). Children are updated first and the
parent `recording_sessions` row last (`:301-306`, `:347`), so a mid-cascade
failure never leaves a parent in the new org with children still in the old one.

Side effects:

- Audit: one `audit_logs` row with `action='move_session_org'`
  (`backend/api/session_move_org.py:470-486` and `:597-613`).
- Qdrant: best-effort payload retag; a failure is logged and surfaced but does
  not roll back the DB move (`_retag_qdrant`, `:211-272`).
- Orphaned speaker links: a moved session's `speaker_session_link.speaker_id`
  may still point at a `SpeakerProfile` in the source org; these are surfaced
  for manual cleanup, not auto-nulled (`:353-398`).

There is no separate CLI script; the move is API-only.

## 4. What an operator runs to prove isolation

The repo's own suite is the proof. Run from `backend/`:

```bash
python3 -m pytest tests/ -v
```

Focused isolation gates:

- `tests/test_pilot_org_isolation.py`: pilot gate. Two tenants each get an
  exclusive marker; the caller is always a member of one org, and any appearance
  of the other org's marker in a response is a leak. Covers list, detail,
  legacy detail, keyword + semantic search, insights, transcript/media/export,
  all analytics aggregates, per-meeting chat + RAG + chat history, and the MCP
  read tools. Forged/foreign/numeric org selectors and `include_all_my_orgs` /
  `all_tenants` from a regular member must never expand scope
  (`test_missing_and_forged_org_context_never_expands_scope`).
- `tests/test_cross_org_isolation.py`: unit + HTTP regression. Pins the Qdrant
  and Postgres search paths, satellite device CRUD, and conference-room CRUD as
  org-scoped; cross-org reads must 404 and register must bind to the caller's
  org regardless of any payload org hint.
- `tests/test_session_move_org.py`: the `move-org` route. Asserts the cascade
  counts, that a moved session disappears from the source org's list and appears
  in the target org's list, and the 403/400/404 auth failure modes.
- `tests/test_session_org_reassign.py`: the `PUT .../organization` route. Asserts
  owner can move to an org they belong to, cannot move a session they cannot
  write, cannot move into an org they are not a member of, action items cascade,
  and that the list header + `include_all_my_orgs` stay member-scoped.

Supporting suites: `tests/test_multi_org.py`,
`tests/test_system_settings_isolation.py`,
`tests/test_federation_org_wide_reads.py`,
`tests/test_register_org_role_injection.py`,
`tests/test_provider_org_route.py`,
`tests/test_brigade_per_org_toggle.py`.

A green run of the four focused files is the operator's evidence that reads are
tenant-scoped and that the two move routes cannot be used to cross a boundary.
