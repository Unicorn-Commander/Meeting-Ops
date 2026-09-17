# Project-Ops bridge write-path flip (L2/L2c)

## Why

Meeting-Ops writes meeting action items into Project-Ops on one of two paths:

| path      | endpoint            | actor token                                          |
|-----------|---------------------|------------------------------------------------------|
| `direct`  | `POST /tasks`       | Keycloak `project-ops` service account (`azp=project-ops`) |
| `triage`  | `POST /triage/ingest` | Brigade-exchanged `meeting-ops` (`act.client_id=meeting-ops`) |

After Project-Ops L2c, the `project-ops` service-account token used by the
`direct` path is classified as a MACHINE actor `project-ops`, so the
human-role `POST /tasks` route stops accepting it. The `triage` path arrives
as the allow-listed federation actor `meeting-ops` and is the intended
successor (see `backend/src/common/workspace/federation-token.ts` in
Project-Ops).

## Setting

`PROJECTOPS_WRITE_PATH` on the `meet-backend` container.

- `direct` (default) — legacy direct task-create. Today's behaviour.
- `triage` — federation ingest (propose-only; a human approves in Project-Ops).

Anything else falls back to `direct`. The setting is read at call time, so a
flip needs only an env change + restart (no code deploy).

## Flip

Add to the `meet-backend` `environment:` block (deploy compose):

```yaml
PROJECTOPS_WRITE_PATH: triage
```

Restart `meet-backend`.

## Verification

After the flip, confirm the bridge has left the direct path:

```bash
# The writer logs a delegation line on the first affected session:
docker logs meet-backend 2>&1 | grep -E "path=triage"

# A write must produce triage proposals, never a direct task:
#   action_items.raw_payload gains po_triage_submitted_at and NOT po_task_id.
docker exec meet-backend \
  python scripts/backfill_action_items_to_projectops.py --dry-run
docker exec meet-backend \
  python scripts/backfill_action_items_to_projectops.py --org-id <ORG>
```

Watch Project-Ops triage inbox: new Meeting-Ops action items must appear as
`MEETING_OPS` proposals (no task is created until a human approves).

## Rollback

Set the flag back (or remove it) and restart:

```yaml
PROJECTOPS_WRITE_PATH: direct
```

The direct writer skips existing task links, triage submission stamps, and
items already managed by the proposal lifecycle. Pending or rejected proposals
therefore remain in human review instead of becoming tasks during rollback.
The triage writer also skips existing task links and submitted proposals.

This flag rollback does not restore compatibility with Project-Ops L2/L2c:
its human-only `/tasks` route rejects the direct machine token. Keep the
triage path enabled after L2/L2c deploy, or coordinate a Project-Ops rollback
before resuming fresh direct writes. Local replay tests do not prove the live
Brigade grant, token exchange, or tenant routing; verify those before deploy.
