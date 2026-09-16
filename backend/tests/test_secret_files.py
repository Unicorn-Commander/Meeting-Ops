"""Synthetic-only file relocation regressions; no external services contacted."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import secret_config

KEY = 'synthetic-meeting-key-for-file-relocation-0123456789'
NAMES = ('SECRET_KEY', 'BRIGADE_API_KEY', 'GARAGE_SECRET_KEY')


@pytest.fixture(autouse=True)
def clean_secret_inputs(monkeypatch):
    for name in (*NAMES, 'BRIGADE_ADMIN_KEY', 'FEDERATION_CURSOR_SIGNING_SECRET'):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name + '_FILE', raising=False)
    monkeypatch.setattr(secret_config, '_warned', set())


def secret_file(tmp_path, monkeypatch, name, value=KEY):
    path = tmp_path / name
    path.write_text(value + '\n')
    monkeypatch.setenv(name + '_FILE', str(path))
    return path


def fresh_module(relative, name):
    path = Path(__file__).resolve().parents[1] / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name', NAMES)
def test_file_wins_and_env_preserves_legacy_whitespace(name, tmp_path, monkeypatch):
    monkeypatch.setenv(name, '  legacy env  ')
    assert secret_config.get_secret(name) == '  legacy env  '
    assert secret_config.configured_secret_source(name) == 'env'
    secret_file(tmp_path, monkeypatch, name)
    assert secret_config.get_secret(name) == KEY
    assert secret_config.configured_secret_source(name) == 'file'


@pytest.mark.parametrize('failure', ['missing', 'empty', 'permission', 'invalid_utf8', 'invalid_path'])
def test_unusable_file_falls_back_without_disclosing_contents(failure, tmp_path, monkeypatch, caplog):
    path = secret_file(tmp_path, monkeypatch, 'SECRET_KEY')
    monkeypatch.setenv('SECRET_KEY', KEY)
    if failure == 'missing': path.unlink()
    elif failure == 'empty': path.write_text(' \n\t')
    elif failure == 'invalid_utf8': path.write_bytes(b'\xff')
    elif failure == 'invalid_path':
        path.unlink()
        path.mkdir()
    else:
        def denied(*args, **kwargs): raise PermissionError('sensitive path should not be logged')
        monkeypatch.setattr(Path, 'read_text', denied)
    assert secret_config.get_secret('SECRET_KEY') == KEY
    assert secret_config.configured_secret_source('SECRET_KEY') == 'env'
    assert KEY not in caplog.text and str(path) not in caplog.text
    assert 'sensitive path' not in caplog.text
    monkeypatch.delenv('SECRET_KEY')
    assert secret_config.get_secret('SECRET_KEY') is None
    assert secret_config.configured_secret_source('SECRET_KEY') == 'none'


def test_empty_env_distinct_from_unset(monkeypatch):
    assert secret_config.get_secret('SECRET_KEY', 'default') == 'default'
    monkeypatch.setenv('SECRET_KEY', '')
    assert secret_config.get_secret('SECRET_KEY', 'default') == ''


def test_auth_relocated_same_key_preserves_issued_jwt(tmp_path, monkeypatch):
    from auth import utils
    monkeypatch.setenv('ENVIRONMENT', 'production')
    monkeypatch.setenv('SECRET_KEY', KEY)
    old_config = fresh_module('auth/config.py', 'auth_config_env').auth_config
    monkeypatch.setattr(utils, 'auth_config', old_config)
    token = utils.create_access_token({'sub': 'synthetic-user'})
    secret_file(tmp_path, monkeypatch, 'SECRET_KEY')
    monkeypatch.delenv('SECRET_KEY')
    new_config = fresh_module('auth/config.py', 'auth_config_file').auth_config
    monkeypatch.setattr(utils, 'auth_config', new_config)
    assert utils.decode_token(token)['sub'] == 'synthetic-user'
    assert new_config.SECRET_KEY == old_config.SECRET_KEY
    docker_auth = fresh_module('auth_docker.py', 'docker_auth_file')
    import jwt
    assert jwt.decode(docker_auth.create_access_token({'sub': 'synthetic-user'}), KEY, algorithms=['HS256'])['sub'] == 'synthetic-user'


@pytest.mark.parametrize('weak', ['short', 'your-secret-key-change-this-in-production'])
def test_auth_file_retains_strict_strength_check(weak, tmp_path, monkeypatch):
    monkeypatch.setenv('ENVIRONMENT', 'production')
    monkeypatch.setenv('SECRET_KEY', KEY)
    secret_file(tmp_path, monkeypatch, 'SECRET_KEY', weak)
    with pytest.raises(RuntimeError, match='Refusing to boot'):
        fresh_module('auth/config.py', 'weak_auth_config')


def test_federation_same_key_cursor_and_explicit_precedence(tmp_path, monkeypatch):
    from api import federation_meetings as fm
    monkeypatch.setenv('SECRET_KEY', KEY)
    payload = {'v': 1, 'contact_key': fm._cursor_contact_key(['synthetic-contact']),
               'updated_since': None, 'snapshot_at': '2026-09-15T12:00:00+00:00',
               'last_updated_at': '2026-09-15T11:00:00+00:00', 'last_id': 7}
    token = fm._encode_cursor(payload)
    secret_file(tmp_path, monkeypatch, 'SECRET_KEY')
    monkeypatch.delenv('SECRET_KEY')
    assert fm._encode_cursor(payload) == token
    assert fm._decode_cursor(token, contact_ids=['synthetic-contact'], updated_since=None)['last_id'] == 7
    monkeypatch.setenv('FEDERATION_CURSOR_SIGNING_SECRET', 'explicit-federation-key')
    assert fm._cursor_signing_key() == b'explicit-federation-key'


def test_brigade_clients_use_file_key_on_request(tmp_path, monkeypatch):
    from services.agents.brigade import _brigade_api_key
    from services.brigade_client import BrigadeClient, _api_key
    secret_file(tmp_path, monkeypatch, 'BRIGADE_API_KEY')
    monkeypatch.setenv('BRIGADE_ADMIN_KEY', 'admin-fallback')
    assert _api_key() == _brigade_api_key() == KEY
    seen = []
    def respond(request):
        seen.append(request.headers['X-API-Key'])
        return httpx.Response(200, json={'ok': True})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await BrigadeClient(_client=client).upsert_entity(name='fixture', entity_type='test')
            assert result.ok
    asyncio.run(run())
    assert seen == [KEY]
    monkeypatch.delenv('BRIGADE_API_KEY_FILE')
    assert _api_key() == _brigade_api_key() == 'admin-fallback'


def test_brigade_org_override_and_disabled_win_over_file(tmp_path, monkeypatch):
    from services.integrations import org_config as oc
    secret_file(tmp_path, monkeypatch, 'BRIGADE_API_KEY')
    assert oc.resolve_brigade(None, None).api_key == KEY
    org = SimpleNamespace(integrations={'brigade': {'enabled': False}})
    monkeypatch.setattr(oc, 'get_organization', lambda *args: org)
    config = oc.resolve_brigade(None, 7)
    assert not config.enabled and config.api_key is None and config.source == 'disabled'
    org.integrations['brigade'] = {'enabled': True, 'api_key_encrypted': 'synthetic-ciphertext'}
    monkeypatch.setattr(oc, '_decrypt_or_none', lambda value: 'org-specific-key')
    assert oc.resolve_brigade(None, 7).api_key == 'org-specific-key'


@pytest.mark.parametrize('relative,client_name', [('services/attachment_storage.py', '_get_s3_client'), ('services/media_storage.py', '_client')])
def test_storage_clients_receive_file_key(relative, client_name, tmp_path, monkeypatch):
    import boto3
    secret_file(tmp_path, monkeypatch, 'GARAGE_SECRET_KEY')
    monkeypatch.setenv('GARAGE_SECRET_KEY', 'old-env')
    monkeypatch.setenv('GARAGE_ENDPOINT_URL', 'http://storage.invalid')
    monkeypatch.setenv('GARAGE_ACCESS_KEY', 'synthetic-access')
    monkeypatch.setenv('MEDIA_STORAGE_DISABLED', '0')
    calls = []
    def client(*args, **kwargs):
        calls.append(kwargs)
        return object()
    monkeypatch.setattr(boto3, 'client', client)
    storage = fresh_module(relative, 'synthetic_storage')
    assert getattr(storage, client_name)() is not None
    assert calls[0]['aws_secret_access_key'] == KEY
