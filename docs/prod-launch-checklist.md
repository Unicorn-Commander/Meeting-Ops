# Prod launch checklist — `meeting-ops.unicorncommander.ai`

Status as of 2026-05-30 (v3.20.0 shipped):

- ✅ Infrastructure stood up (TLS, DNS, Postgres, Garage, backend, frontend, worker, MCP)
- ✅ Landing page live at `/`
- ✅ Aaron + Shafen seeded as enterprise/admin users for internal testing
- ✅ Stripe products + webhook live in the Magic Unicorn Stripe account
- ⏳ Stripe env vars NOT set on VPS (intentional — invite-only mode)
- ⏳ `ALLOW_REGISTRATION=false` (intentional — invite-only mode)
- ⏳ Postmark token NOT set on VPS (no signup verification emails)
- ⏳ Landing CTA still goes to `/api/landing/invite-request` form, not `/signup`

When you're ready to open up the prod URL to real paying customers, work
this checklist top to bottom. Each step is reversible until you push the
public marketing announcement.

---

## Pre-flight: confirm dev parity

Things that should ALREADY be working on `meetingops.magicunicorn.dev`
before flipping prod. If any of these are broken on dev, fix dev first.

- [ ] You + Shafen can subscribe with the **DEV_TEST_2026** coupon
      end-to-end (webhook fires → tier flips → UI updates)
- [ ] Subscription cancel + resume works (Customer Portal)
- [ ] Mobile recording shows the Free-tier upgrade prompt (no audio
      uploads from a free phone — moat verified)
- [ ] Founders 100 mechanic stamps `is_founder=true` on first signup
- [ ] At least one full meeting recorded → finalized → summarized →
      played back on dev within the last week

If any of these are broken, the prod flip will surface them publicly.

---

## Phase 1 — Stripe live mode on prod (30 min)

You already created live products + the bigboy dev webhook. Now you
add a second webhook endpoint for prod and paste the env vars.

### 1a. Create prod webhook

```bash
export STRIPE_KEY='REMOVED'
curl -s -u "$STRIPE_KEY:" https://api.stripe.com/v1/webhook_endpoints \
  -d "url=https://meeting-ops.unicorncommander.ai/api/stripe/webhook" \
  -d "description=Meeting-Ops VPS prod" \
  -d "enabled_events[]=customer.subscription.created" \
  -d "enabled_events[]=customer.subscription.updated" \
  -d "enabled_events[]=customer.subscription.deleted" \
  -d "enabled_events[]=customer.created" \
  -d "enabled_events[]=checkout.session.completed" \
  -d "metadata[environment]=vps-prod" \
  | python3 -m json.tool
```

Note the `secret` from the response → that becomes
`STRIPE_WEBHOOK_SECRET` below.

### 1b. Paste env vars on VPS

```bash
ssh centerdeep
cd /home/muut/UC-Meeting-Ops
# Append Stripe live config to the env file:
cat >> deploy/unicorncommander/.env.unicorncommander <<EOF

# Stripe live mode — added at customer launch <date>
STRIPE_API_KEY=REMOVED
STRIPE_PUBLISHABLE_KEY=REMOVED
STRIPE_WEBHOOK_SECRET=<paste from step 1a>
STRIPE_PRO_PRICE_ID=price_1TcbE0Dzk9HqAZnHO3cv6mWN
STRIPE_SUITE_PRICE_ID=price_1TcbE1Dzk9HqAZnH9HVigcpm
STRIPE_ENTERPRISE_PRICE_ID=
STRIPE_ALLOW_LIVE=1
# Promo codes off on prod — Founders 100 is access-only, no discount.
STRIPE_ALLOW_PROMO_CODES=
EOF
```

### 1c. Restart backend (no rebuild needed)

```bash
docker compose --env-file deploy/unicorncommander/.env.unicorncommander \
  -f deploy/unicorncommander/docker-compose.unicorncommander.yml \
  up -d --force-recreate meet-backend meet-bulk-import-worker
```

### 1d. Verify Stripe is live on prod

```bash
docker exec meet-backend python3 -c "
import os
print('STRIPE_API_KEY set:', bool(os.getenv('STRIPE_API_KEY')))
print('STRIPE_ALLOW_LIVE:', os.getenv('STRIPE_ALLOW_LIVE'))
print('STRIPE_PRO_PRICE_ID:', os.getenv('STRIPE_PRO_PRICE_ID'))
"
```

`/api/billing/subscription` for an authenticated free user should now
return a real subscription state (or `None`), not 503.

---

## Phase 2 — Email verification (15 min)

Self-serve signup writes a User row, then sends a verification email.
Without Postmark, signups go through but the user never gets the email
and can't verify. Add the Postmark token.

```bash
ssh centerdeep
cd /home/muut/UC-Meeting-Ops
# Add Postmark token (use the same one bigboy uses, or mint a new one):
echo "POSTMARK_API_TOKEN=<your-token>" >> deploy/unicorncommander/.env.unicorncommander
echo "POSTMARK_SERVER_TOKEN=<your-token>" >> deploy/unicorncommander/.env.unicorncommander
docker compose --env-file deploy/unicorncommander/.env.unicorncommander \
  -f deploy/unicorncommander/docker-compose.unicorncommander.yml \
  up -d --force-recreate meet-backend
```

Verify by manually triggering an email from inside the container:
```bash
docker exec meet-backend python3 -c "
from auth.email import send_verification_email
send_verification_email('aaron@magicunicorn.tech', 'test-verification-link')
"
```
Should land in your inbox within a minute.

---

## Phase 3 — Flip `ALLOW_REGISTRATION` (5 min)

```bash
ssh centerdeep
cd /home/muut/UC-Meeting-Ops
sed -i 's/^ALLOW_REGISTRATION=false/ALLOW_REGISTRATION=true/' \
  deploy/unicorncommander/.env.unicorncommander
docker compose --env-file deploy/unicorncommander/.env.unicorncommander \
  -f deploy/unicorncommander/docker-compose.unicorncommander.yml \
  up -d --force-recreate meet-backend
```

Now POST `/api/auth/register` accepts anonymous calls with
`{"username":"...", "email":"...", "password":"..."}`.

---

## Phase 4 — Landing CTA wiring (45 min frontend work)

Currently the Landing page form posts to `/api/landing/invite-request`
which writes a row to `invite_requests` for you to follow up manually.

For the public launch, the form should:
1. Take the email
2. Pre-fill it into `/signup`
3. New user completes signup → email verification → onboarding → pricing

Two paths:

**Quick path (no code change):** keep the invite-request flow, manually
approve invites by sending each requester a "create your account at
`/signup` with this email" reply. Works for the first ~100 users.

**Full path (code change):** swap the form action so it redirects to
`/signup?email={value}`. ~30 lines of frontend. Worth doing before HN
launch, optional for soft launch.

For the soft launch, I'd lean **quick path** — gives you a manual gate
on early users without rushing the wiring.

---

## Phase 5 — Smoke test as a customer (30 min)

In a private browser window (NOT logged in as you):

1. Visit `https://meeting-ops.unicorncommander.ai/` → see Landing page
2. Click "Request an invite" (or `/signup` if Phase 4-full is done)
3. Enter a brand new email (use `<your-email>person1@example.com` or similar
   — Postmark + Gmail will treat plus-addressing as a unique address)
4. Verify the email arrives
5. Click the verify link → land on `/dashboard` as a free user
6. Hit `/pricing` → see Free / Pro $12 / Suite $25 / Enterprise tiers
7. Click "Subscribe" on Pro → Stripe Checkout (LIVE — real card)
8. Use your real card (you can refund yourself after) → complete checkout
9. Webhook fires → backend processes → your tier flips to `pro`
10. Verify in DB: `SELECT username, tier FROM users WHERE email = '...';`
11. Refresh the app → UpgradeBanner gone, full features available
12. Refund the subscription in Stripe Dashboard so you don't get charged
    on the next monthly cycle

If this end-to-end passes, you're ready for the public flip.

---

## Phase 6 — Public flip + launch (your call)

When you're ready to announce:

1. Replace the landing's "Request an invite" copy with "Get started" /
   "Try free" CTAs pointing at `/signup` (if you didn't do Phase 4-full)
2. Post on Hacker News / Product Hunt / Twitter / LinkedIn
3. Monitor `/health` and Grafana for any spike-driven failures
4. Watch the Stripe Dashboard for the first paying customer

---

## Rollback at any phase

Each phase is reversible:

- **Phase 1**: clear Stripe env vars + restart → billing endpoints 503
  again, no charges fire
- **Phase 2**: clear Postmark token → email sends become inert (no error,
  just no email)
- **Phase 3**: `sed -i 's/ALLOW_REGISTRATION=true/ALLOW_REGISTRATION=false/'`
  + restart → registration returns 403
- **Phase 4**: revert the frontend commit + redeploy
- **Phase 5**: signups can be deleted directly from `users` table
- **Phase 6**: take down the marketing post, flip Phase 3 back

---

## Out of scope for this checklist (future work)

- **oauth2-proxy SSO on VPS** — would unify identity with the rest of
  the UC ecosystem (commander apps). Today the VPS uses native email/
  password auth, which is fine for SaaS customers but doesn't share
  session with `unicorncommander.ai`. Add when Suite tier really
  starts mattering and customers need cross-app SSO.
- **Live diarization on prod** — server-live transcript requires the
  Sortformer streaming service. Today it stays OFF (per v3.18.0
  decision). Promote later when OOM-on-real-meetings is solved.
- **Per-org integration creds UI** — the Settings → Workspace →
  Integrations panel exists (v3.19) but customers can't store provider
  API keys yet because the Provider Settings encrypted-cred flow
  needs UI for end users. Today it's admin-only via the DB.
- **Landing→signup CTA wiring** — Phase 4-full above. Manual invite
  approval is fine for the first 100 users.
