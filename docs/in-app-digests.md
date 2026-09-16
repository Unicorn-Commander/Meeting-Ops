# In-app daily and weekly digests

Daily and weekly digests live on the existing **Digests** page. Email is optional.
The existing `GET /api/digests` response and queued-generation contract are unchanged.

## Scheduling and eligibility

The existing bulk-import arq worker now runs:

- Daily at 13:00 UTC: store yesterday's completed meetings.
- Monday at 13:15 UTC: store the previous Monday–Sunday week.

Both use the existing summary generator and `MeetingDigest` rows. Only active
organizations with completed meetings in the UTC window are candidates. The
existing cron paid gate (paid org **or** non-free member) is preserved. This is
legacy cron eligibility; interactive generation still uses the stricter existing
account **and** active-workspace capability gate. Reading stored digests remains
available to all tiers, like the existing cache-hit API.

Generation runs regardless of org email settings or personal opt-ins. The pass
reuses stored organization digests, preferring unstored windows before applying
the organization cap. Empty windows consume no LLM work. Each org has its own
session and failure boundary. `dry_run=True` performs no generation or delivery.
Schedules produce the immediately preceding window; this is not a historical
backfill or automatic catch-up for missed days. An operator can rerun a specific
window with `store_scheduled_digests(period, date_str="YYYY-MM-DD")`.

## Email precedence (include in PR)

1. Period schedule flag must permit the pass.
2. `Organization.settings["weekly_digest"]["enabled"] = false` blocks **all**
   digest email (daily and weekly), while allowing in-app generation.
3. An explicit org `enabled = true` permits delivery. An absent `enabled` uses
   `WEEKLY_DIGEST_DEFAULT_ON` (still **false** by default).
4. The account must explicitly opt into that cadence. Both
   `User.email_daily_digest` and `User.email_weekly_digest` default **OFF**,
   including existing users after migration. No org/default flag opts a user in.
5. The recipient must currently be an active, verified member of that org.

Legacy org `recipients` lists and admin/manager fallback recipients no longer
subscribe anyone. Personal checkboxes appear on Digests and Settings →
Notifications and follow the account across workspaces. An org block is shown
alongside the saved preferences. Changing a preference does not immediately send
old digests; it takes effect on subsequent scheduled/manual passes.

## Delivery and idempotency

Generation commits the digest before the separate `deliver_digest` step. One
`digest_delivery` row claims each `(organization_id, period, date, user_id)`
**before** sending. Its unique constraint prevents concurrent or sequential
reruns from mailing that recipient/window again, even if an older installation
has duplicate digest rows. Only a successful send sets `sent_at`; history derives
“emailed to you” from the authenticated user's successful receipt. The old
org-wide `MeetingDigest.emailed_at` remains intact but is no longer a delivery
control or evidence that a particular user received email.

A definitive failed send (unconfigured sender or provider rejection) releases
only that recipient's claim for retry. Transport exceptions and server errors
are ambiguous: a provider may have accepted the message. Those claims remain
unresolved and are **not** automatically retried. A crash between send and stamp
has the same limitation. An operator must check delivery evidence before clearing
an unresolved claim. This favors duplicate prevention; it cannot guarantee
exactly-once delivery across Postgres and an external email provider.

## API additions

- `GET /api/digests/history?period=day|week&from=YYYY-MM-DD&to=YYYY-MM-DD&cursor=date|id&limit=30`
  returns `{items, next_cursor}` newest window first. Date bounds are inclusive;
  limit is 1–100. Every item includes id, period, date, meeting_count,
  generated_at, and emailed_to_you. Organization/project scope is enforced.
- `GET /api/digests/history/{id}` returns those fields plus content,
  sources_recorded, and source_meetings (`id`, `title`). Cross-org ids are 404;
  source links are rechecked for org membership and existence at read time.
- `GET /api/digests/preferences` returns both booleans plus
  organization_email_enabled for the active workspace.
- `PATCH /api/digests/preferences` updates only the authenticated account's
  supplied boolean fields. Preferences are not tier-gated.

All routes require existing user/organization authentication. Legacy digests
without recorded source ids show an honest “links were not recorded” state;
no inferred source backfill is performed. Generated-at falls back to the original
row creation time for those rows.

## Migration and dogfood handoff

Apply additive Alembic **063_in_app_digests**, after
`062_merge_combined_and_lease`, before starting the updated API or workers.
It adds two default-false user columns, nullable source ids/generated_at on
meeting_digest, and the recipient claim table with a unique window key.
No existing preferences are enabled and no old email receipts are inferred.

Persephone should apply the migration, rebuild the frontend/API, and restart the
existing bulk-import worker so it registers both crons. No new service is needed.
Use a paid dogfood org with completed meetings in the previous UTC day/week;
confirm the digest appears with both personal preferences off. To exercise
email, explicitly enable the org switch, verify the intended user's email, and
check only that user's desired cadence. Rerun the same window to check no resend.
This lane does not deploy or contact the LLM, mail provider, or live API.

| Environment flag | Default | Scope |
| --- | --- | --- |
| `DAILY_DIGEST_ENABLED` | `true` | Daily generation/delivery pass |
| `WEEKLY_DIGEST_ENABLED` | `true` | Weekly generation/delivery pass |
| `WEEKLY_DIGEST_DEFAULT_ON` | `false` | Fallback org email permission for both cadences; never personal opt-in |
| `WEEKLY_DIGEST_REQUIRE_PAID` | `true` | Existing paid check for both cadences |
| `WEEKLY_DIGEST_MAX_ORGS_PER_PASS` | `500` | Per-pass cap for either cadence |
| `MEETING_OPS_PUBLIC_URL` | Existing URL fallback chain | Email links now open `/digests` |

Existing Postmark configuration is reused; no new credentials are introduced.
