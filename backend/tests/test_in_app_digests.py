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
        assert row.emailed_at is None
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
    from database.models import DigestDelivery, MeetingDigest
    opt_in(cohort)
    await store_scheduled_digests(period, date_str=date)
    cohort['sender'].assert_called_once()
    assert cohort['sender'].call_args.kwargs['recipient'].endswith('@meeting-ops.local')
    await store_scheduled_digests(period, date_str=date)
    cohort['sender'].assert_called_once()
    with SessionLocal() as db:
        rows = db.query(DigestDelivery).filter_by(organization_id=cohort['org']).all()
        assert len(rows) == 1 and rows[0].user_id == cohort['user'] and rows[0].sent_at
        assert db.query(MeetingDigest).filter_by(organization_id=cohort['org'], period=period, date=date).one().emailed_at


@pytest.mark.asyncio
async def test_repeated_nine_am_cron_start_uses_delivery_unique_key(cohort, monkeypatch):
    from database.database import SessionLocal
    from database.models import DigestDelivery
    from workers import weekly_digest_workers as worker

    opt_in(cohort)
    # 09:01 ET on 2026-08-13 covers the seeded 2026-08-12 daily window.
    start = datetime(2026, 8, 13, 13, 1, tzinfo=timezone.utc)

    class FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            return start

    monkeypatch.setattr(worker, "datetime", FrozenDateTime)
    first = await worker.daily_digest_cron({})
    second = await worker.daily_digest_cron({})

    assert first["date"] == second["date"] == "2026-08-12"
    cohort["sender"].assert_called_once()
    with SessionLocal() as db:
        assert db.query(DigestDelivery).filter_by(
            organization_id=cohort["org"], period="day", date="2026-08-12"
        ).count() == 1


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


@pytest.mark.asyncio
async def test_weekly_history_exposes_range_title_and_delivery_marker(client, cohort):
    from workers.weekly_digest_workers import store_scheduled_digests
    opt_in(cohort)
    await store_scheduled_digests('week', date_str='2026-08-10')
    response = client.get('/api/digests/history?period=week', headers=cohort['headers'])
    assert response.status_code == 200
    item = response.json()['items'][0]
    assert item['title'] == 'Weekly digest · Aug 10–Aug 16, 2026'
    assert item['week_range'] == 'Aug 10–Aug 16, 2026'
    assert item['delivery_status'] == 'emailed'
    detail = client.get(f"/api/digests/history/{item['id']}", headers=cohort['headers'])
    assert detail.json()['delivery_status'] == 'emailed'


def test_preferences_default_off_patch_only_self_and_kill_switch(client, cohort):
    headers = cohort['headers']
    before = client.get('/api/digests/preferences', headers=headers)
    assert before.status_code == 200
    assert not before.json()['email_daily_digest'] and not before.json()['email_weekly_digest']
    assert before.json()['weekly_digest_email'] is False
    changed = client.patch('/api/digests/preferences', json={'email_daily_digest': True}, headers=headers)
    assert changed.status_code == 200 and changed.json()['email_daily_digest']
    assert not changed.json()['email_weekly_digest']
    changed = client.patch('/api/digests/preferences', json={'weekly_digest_email': True}, headers=headers)
    assert changed.status_code == 200 and changed.json()['email_weekly_digest'] and changed.json()['weekly_digest_email']
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


@pytest.mark.asyncio
async def test_cap_prioritizes_unstored_orgs_and_dry_run_has_no_writes(cohort, monkeypatch):
    from workers.weekly_digest_workers import store_scheduled_digests
    from database.database import SessionLocal
    from database.models import MeetingDigest
    monkeypatch.setenv('WEEKLY_DIGEST_MAX_ORGS_PER_PASS', '1')
    dry = await store_scheduled_digests('day', date_str='2026-08-12', dry_run=True)
    assert dry['orgs_processed'] == 1
    cohort['llm'].chat.assert_not_awaited()
    cohort['sender'].assert_not_called()
    for _ in range(2):
        result = await store_scheduled_digests('day', date_str='2026-08-12')
        assert result['orgs_considered'] == 1 and result['generated'] == 1
    with SessionLocal() as db:
        assert db.query(MeetingDigest).filter(MeetingDigest.organization_id.in_([cohort['org'], cohort['other']])).count() == 2


@pytest.mark.asyncio
async def test_paid_gate_and_period_flag(cohort, monkeypatch):
    from auth.models import User, Organization
    from database.database import SessionLocal
    from workers.weekly_digest_workers import store_scheduled_digests
    with SessionLocal() as db:
        for oid in (cohort['org'], cohort['other']):
            db.get(Organization, oid).plan = 'free'
        for uid in (cohort['user'], cohort['second'], cohort['other_user']):
            db.get(User, uid).tier = 'free'
        db.commit()
    result = await store_scheduled_digests('day', date_str='2026-08-12')
    assert result['orgs_considered'] == 0
    cohort['llm'].chat.assert_not_awaited()
    monkeypatch.setenv('DAILY_DIGEST_ENABLED', 'false')
    assert await store_scheduled_digests('day') == {'enabled': False}


@pytest.mark.asyncio
async def test_detail_drops_sources_moved_to_another_org_and_legacy_api_stays_compatible(client, cohort):
    from database.database import SessionLocal
    from database.models import RecordingSession
    from auth.models import User, Organization
    from workers.weekly_digest_workers import store_scheduled_digests
    await store_scheduled_digests('day', date_str='2026-08-12')
    with SessionLocal() as db:
        db.get(RecordingSession, cohort['sid']).organization_id = cohort['other']
        db.get(User, cohort['user']).tier = 'free'
        db.get(Organization, cohort['org']).plan = 'free'
        db.commit()
    cached = client.get('/api/digests?period=day&date=2026-08-12', headers=cohort['headers'])
    assert cached.status_code == 200
    assert set(cached.json()) == {'id', 'period', 'date', 'project_id', 'content', 'meeting_count', 'cached'}
    assert cached.json()['cached'] is True
    detail = client.get(f"/api/digests/history/{cached.json()['id']}", headers=cohort['headers']).json()
    assert detail['source_meetings'] == [] and detail['sources_recorded']
    assert client.get('/api/digests?period=day&date=2026-08-12&force=true', headers=cohort['headers']).status_code == 403


def test_additive_migration_preserves_rows_defaults_off_and_unique_recipient_window():
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.exc import IntegrityError
    path = Path(__file__).parents[1] / 'alembic/versions/063_in_app_digests.py'
    spec = importlib.util.spec_from_file_location('digest_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        conn.execute(sa.text('CREATE TABLE organizations (id INTEGER PRIMARY KEY)'))
        conn.execute(sa.text('CREATE TABLE meeting_digest (id INTEGER PRIMARY KEY, content TEXT, emailed_at DATETIME)'))
        conn.execute(sa.text('INSERT INTO users VALUES (1)'))
        conn.execute(sa.text('INSERT INTO organizations VALUES (1)'))
        conn.execute(sa.text("INSERT INTO meeting_digest VALUES (1, 'Legacy digest', '2026-08-01')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert tuple(conn.execute(sa.text('SELECT email_daily_digest, email_weekly_digest FROM users')).one()) == (0, 0)
        assert tuple(conn.execute(sa.text('SELECT content, source_meeting_ids, generated_at FROM meeting_digest')).one()) == ('Legacy digest', None, None)
        statement = sa.text("INSERT INTO digest_delivery (digest_id, organization_id, user_id, period, date, claimed_at) VALUES (1, 1, 1, 'day', '2026-08-01', '2026-08-02')")
        conn.execute(statement)
        with pytest.raises(IntegrityError):
            conn.execute(statement)
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert conn.execute(sa.text('SELECT content FROM meeting_digest')).scalar() == 'Legacy digest'
        assert 'digest_delivery' not in sa.inspect(conn).get_table_names()


def test_legacy_weekly_subscribers_are_backfilled():
    import importlib.util
    from pathlib import Path
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1] / 'alembic/versions/064_backfill_legacy_weekly_digest_email.py'
    spec = importlib.util.spec_from_file_location('legacy_digest_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, email_weekly_digest BOOLEAN NOT NULL DEFAULT 0)'))
        conn.execute(sa.text('CREATE TABLE organizations (id INTEGER PRIMARY KEY, settings JSON)'))
        conn.execute(sa.text('CREATE TABLE user_organizations (user_id INTEGER, organization_id INTEGER, role TEXT)'))
        conn.execute(sa.text("INSERT INTO users VALUES (1, 'admin@example.com', 0), (2, 'other@example.com', 0)"))
        conn.execute(sa.text("INSERT INTO organizations VALUES (1, '{\"weekly_digest\": {\"enabled\": true}}')"))
        conn.execute(sa.text("INSERT INTO user_organizations VALUES (1, 1, 'admin'), (2, 1, 'user')"))
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert conn.execute(sa.text('SELECT email_weekly_digest FROM users WHERE id = 1')).scalar() == 1
        assert conn.execute(sa.text('SELECT email_weekly_digest FROM users WHERE id = 2')).scalar() == 0


@pytest.mark.parametrize('strict', [False, True])
def test_email_transport_error_is_only_raised_for_claimed_digest_delivery(monkeypatch, strict):
    from auth import email
    import httpx
    monkeypatch.setattr(email, '_postmark_token', lambda: 'test-only-placeholder')
    monkeypatch.setattr(email, '_postmark_sender', lambda: 'test@example.com')
    transport = MagicMock()
    transport.__enter__.return_value = transport
    transport.post.side_effect = httpx.ReadTimeout('unknown delivery outcome')
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: transport)
    if strict:
        with pytest.raises(httpx.ReadTimeout):
            email._send('test@example.com', 'Digest', 'body', 'body', raise_on_transport_error=True)
    else:
        assert email._send('test@example.com', 'Auth', 'body', 'body') is False
