"""In-app scheduling, personal delivery, and tenant-isolated history.

Uses the repository SQLite/client fixtures. LLM and Postmark are always mocked.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_digest_job_flow import _seed_user, _seed_completed_session, _login


@pytest.fixture
def client(canonical_db_schema):
    # Real auth/org dependencies without unrelated media-service startup.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.digests import router
    from auth.routes import router as auth_router
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def cohort(client, monkeypatch):
    from auth.models import Organization, User, UserOrganization
    from database.database import SessionLocal
    from database.models import RecordingSession
    from workers import weekly_digest_workers as worker
    suffix = uuid.uuid4().hex[:8]
    org_id, slug, user_id = _seed_user(f"digest-a-{suffix}", f"digest_a_{suffix}", "pro")
    other_id, other_slug, other_user_id = _seed_user(f"digest-b-{suffix}", f"digest_b_{suffix}", "pro")
    with SessionLocal() as db:
        second = User(email=f"second-{suffix}@example.com", username=f"second-{suffix}",
                      hashed_password="unused", is_active=True, is_verified=True, tier="pro")
        db.add(second); db.flush()
        db.add(UserOrganization(user_id=second.id, organization_id=org_id, role="user"))
        db.query(Organization).filter(Organization.id.in_([org_id, other_id])).update(
            {Organization.settings: {"weekly_digest": {"enabled": True, "recipients": ["legacy@example.com"]}}},
            synchronize_session=False,
        )
        db.commit()
        second_id = second.id
    sid = _seed_completed_session(org_id, user_id)
    other_sid = _seed_completed_session(other_id, other_user_id)
    with SessionLocal() as db:
        db.query(RecordingSession).filter(RecordingSession.id.in_([sid, other_sid])).update(
            {RecordingSession.created_at: datetime(2026, 8, 12, 10, tzinfo=timezone.utc)}, synchronize_session=False,
        ); db.commit()
    llm = MagicMock(chat=AsyncMock(return_value="Stored summary from meetings."))
    registry = MagicMock(get_llm=MagicMock(return_value=llm))
    monkeypatch.setattr("api.digests.get_provider_registry", lambda db: registry)
    sender = MagicMock(return_value=True)
    monkeypatch.setattr(worker, "_send_digest_email", sender)
    monkeypatch.setenv("WEEKLY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("DAILY_DIGEST_ENABLED", "true")
    monkeypatch.setenv("WEEKLY_DIGEST_REQUIRE_PAID", "true")
    monkeypatch.setenv("WEEKLY_DIGEST_DEFAULT_ON", "false")
    monkeypatch.setenv("WEEKLY_DIGEST_MAX_ORGS_PER_PASS", "500")
    yield dict(org=org_id, other=other_id, user=user_id, second=second_id,
                other_user=other_user_id, sid=sid, other_sid=other_sid, slug=slug,
                headers=_login(client, f"digest_a_{suffix}", slug),
                other_headers=_login(client, f"digest_b_{suffix}", other_slug),
                sender=sender, llm=llm)
    with SessionLocal() as db:
        for oid in (org_id, other_id):
            db.get(Organization, oid).is_active = False
        db.commit()


def opt_in(cohort, daily=True, weekly=True, kill=False):
    from auth.models import User, Organization
    from database.database import SessionLocal
    with SessionLocal() as db:
        user = db.get(User, cohort['user'])
        user.email_daily_digest = daily
        user.email_weekly_digest = weekly
        if kill:
            db.get(Organization, cohort['org']).settings = {"weekly_digest": {"enabled": False}}
        db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize('period,date', [('day', '2026-08-12'), ('week', '2026-08-10')])
async def test_scheduled_store_without_email_and_cached_rerun(cohort, period, date):
    from workers.weekly_digest_workers import store_scheduled_digests
    from database.database import SessionLocal
    from database.models import MeetingDigest
    result = await store_scheduled_digests(period, date_str=date)
    assert result['errors'] == 0
    with SessionLocal() as db:
        row = db.query(MeetingDigest).filter_by(organization_id=cohort['org'], period=period, date=date).one()
        assert row.content == 'Stored summary from meetings.'
        assert row.source_meeting_ids == [cohort['sid']]
        assert row.generated_at is not None
    cohort['sender'].assert_not_called()
    calls = cohort['llm'].chat.await_count
    await store_scheduled_digests(period, date_str=date)
    assert cohort['llm'].chat.await_count == calls
    cohort['sender'].assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('period,date', [('day', '2026-08-12'), ('week', '2026-08-10')])
async def test_only_personally_opted_in_and_idempotent(cohort, period, date):
    from workers.weekly_digest_workers import store_scheduled_digests
    from database.database import SessionLocal
    from database.models import DigestDelivery
    opt_in(cohort)
    await store_scheduled_digests(period, date_str=date)
    cohort['sender'].assert_called_once()
    assert cohort['sender'].call_args.kwargs['recipient'].endswith('@meeting-ops.local')
    await store_scheduled_digests(period, date_str=date)
    cohort['sender'].assert_called_once()
    with SessionLocal() as db:
        rows = db.query(DigestDelivery).filter_by(organization_id=cohort['org']).all()
        assert len(rows) == 1 and rows[0].user_id == cohort['user'] and rows[0].sent_at


@pytest.mark.asyncio
async def test_org_kill_switch_wins_but_still_stores(cohort):
    from workers.weekly_digest_workers import store_scheduled_digests
    opt_in(cohort, kill=True)
    result = await store_scheduled_digests('day', date_str='2026-08-12')
    assert result['errors'] == 0 and result['generated'] > 0
    cohort['sender'].assert_not_called()


@pytest.mark.asyncio
async def test_failure_retries_only_unsent_recipient(cohort):
    from auth.models import User
    from database.database import SessionLocal
    from workers.weekly_digest_workers import store_scheduled_digests
    opt_in(cohort)
    with SessionLocal() as db:
        db.get(User, cohort['second']).email_daily_digest = True
        db.commit()
    cohort['sender'].side_effect = [True, False, True]
    await store_scheduled_digests('day', date_str='2026-08-12')
    await store_scheduled_digests('day', date_str='2026-08-12')
    assert cohort['sender'].call_count == 3
    assert cohort['sender'].call_args_list[1].kwargs['recipient'] == cohort['sender'].call_args_list[2].kwargs['recipient']


@pytest.mark.asyncio
async def test_ambiguous_send_is_not_retried(cohort):
    from workers.weekly_digest_workers import store_scheduled_digests
    opt_in(cohort)
    cohort['sender'].side_effect = TimeoutError('unknown outcome')
    await store_scheduled_digests('day', date_str='2026-08-12')
    await store_scheduled_digests('day', date_str='2026-08-12')
    cohort['sender'].assert_called_once()


@pytest.mark.asyncio
async def test_history_scoping_detail_sources_and_personal_delivery(client, cohort):
    from workers.weekly_digest_workers import store_scheduled_digests
    opt_in(cohort)
    await store_scheduled_digests('day', date_str='2026-08-12')
    response = client.get('/api/digests/history?period=day&from=2026-08-01&to=2026-08-31', headers=cohort['headers'])
    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1 and items[0]['emailed_to_you'] is True
    detail = client.get(f"/api/digests/history/{items[0]['id']}", headers=cohort['headers'])
    assert detail.status_code == 200
    assert [s['id'] for s in detail.json()['source_meetings']] == [cohort['sid']]
    assert client.get(f"/api/digests/history/{items[0]['id']}", headers=cohort['other_headers']).status_code == 404
    other = client.get('/api/digests/history?period=day', headers=cohort['other_headers']).json()['items']
    assert len(other) == 1 and other[0]['id'] != items[0]['id'] and not other[0]['emailed_to_you']
    # Org selector is not authorization: a non-member cannot cross tenants.
    forged = {**cohort['other_headers'], 'X-MeetingOps-Org': cohort['slug']}
    fallback = client.get('/api/digests/history?period=day', headers=forged)
    assert fallback.status_code == 200  # Existing resolver falls back to an accessible org.
    assert [row['id'] for row in fallback.json()['items']] == [row['id'] for row in other]
    assert client.get('/api/digests/history?period=day').status_code == 401


def test_preferences_default_off_patch_only_self_and_kill_switch(client, cohort):
    headers = cohort['headers']
    before = client.get('/api/digests/preferences', headers=headers)
    assert before.status_code == 200
    assert not before.json()['email_daily_digest'] and not before.json()['email_weekly_digest']
    changed = client.patch('/api/digests/preferences', json={'email_daily_digest': True}, headers=headers)
    assert changed.status_code == 200 and changed.json()['email_daily_digest']
    assert not changed.json()['email_weekly_digest']
    assert not client.get('/api/digests/preferences', headers=cohort['other_headers']).json()['email_daily_digest']
    opt_in(cohort, kill=True)
    assert not client.get('/api/digests/preferences', headers=headers).json()['organization_email_enabled']
    assert client.patch('/api/digests/preferences', json={'email_daily_digest': None}, headers=headers).status_code == 422


def test_history_pagination_validation_and_free_cached_read(client, cohort):
    from database.database import SessionLocal
    from database.models import MeetingDigest
    from auth.models import User, Organization
    with SessionLocal() as db:
        db.get(User, cohort['user']).tier = 'free'
        db.get(Organization, cohort['org']).plan = 'free'
        for day in ['2026-07-01', '2026-07-02', '2026-07-03']:
            db.add(MeetingDigest(organization_id=cohort['org'], period='day', date=day, content=day, meeting_count=1))
        db.commit()
    first = client.get('/api/digests/history?period=day&limit=2', headers=cohort['headers'])
    assert first.status_code == 200
    assert [r['date'] for r in first.json()['items']] == ['2026-07-03', '2026-07-02']
    second = client.get('/api/digests/history', params={'period': 'day', 'limit': 2, 'cursor': first.json()['next_cursor']}, headers=cohort['headers'])
    assert [r['date'] for r in second.json()['items']] == ['2026-07-01']
    assert second.json()['next_cursor'] is None
    for query in ['cursor=bad', 'from=not-a-date', 'from=2026-08-01&to=2026-07-01']:
        assert client.get(f'/api/digests/history?{query}', headers=cohort['headers']).status_code == 400
    assert client.get('/api/digests/history?period=year', headers=cohort['headers']).status_code == 422
