# Store daily/weekly digests in Meeting-Ops; make email a personal opt-in

Scheduled digests previously required an organization to opt into email, so the
in-app Digests page had no scheduled history for everyone else. The existing
generator now stores daily and weekly summaries for eligible organizations with
completed meetings, then separately delivers optional email. The existing page
adds history tabs, details with source-meeting links, and personal checkboxes
shared with Settings → Notifications. `GET /api/digests` keeps its existing
response and queued-job contract.

**Email precedence:** both account preferences default OFF. An explicit org
`settings.weekly_digest.enabled=false` blocks daily and weekly delivery.
Explicit true permits delivery; an absent org setting uses the existing
`WEEKLY_DIGEST_DEFAULT_ON=false` fallback. Even when the org permits email,
only active, verified members who personally selected that cadence receive it.
Legacy org recipient lists never bypass personal consent. These controls do not
block scheduled in-app generation.

Migration 063 is additive: two user preferences, digest source ids/generated-at,
and a unique recipient/window delivery-claim table. A successful recipient is
never resent on rerun. Ambiguous transport/crash outcomes retain their claim to
avoid duplicates and need operator review before retry; definitive failures
release only the failed recipient's claim.

Apply migration before starting the updated API and bulk-import worker. Daily
runs at 13:00 UTC; weekly at Monday 13:15 UTC. No new service or credentials.
See [rollout, flags, API, and recovery details](in-app-digests.md).

## Validation

See the final [lane receipt](in-app-digests-receipt.md) for exact test counts and
base-commit comparisons. All validation uses local data and mocked providers.
No deployment, mail delivery, or live API/LLM calls were performed.
