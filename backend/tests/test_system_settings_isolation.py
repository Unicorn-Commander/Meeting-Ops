"""The suite must not rewrite the tracked system settings file.

POST /api/simple/settings with an empty body validates as AllSettings() and
saves model defaults (aiProvider ollama, hostname meeting-ops, public DNS,
wifi off, npuPowerMode balanced, empty authentik fields) over
backend/config/system_settings.json. Saves go to SYSTEM_SETTINGS_FILE, and
conftest points that at tmp_path. The session fixture asserts the tracked
bytes are unchanged after the run.
"""
from pathlib import Path

from models.system_settings import AllSettings
from services.system_service import SystemService, settings_path

TRACKED = Path(__file__).resolve().parents[1] / "config" / "system_settings.json"


def test_save_settings_writes_tmp_path_not_the_tracked_file(tmp_path, monkeypatch):
    target = tmp_path / "system_settings.json"
    monkeypatch.setenv("SYSTEM_SETTINGS_FILE", str(target))
    before = TRACKED.read_bytes()

    assert SystemService.save_settings(AllSettings()) is True

    assert settings_path() == target
    assert target.is_file()
    assert TRACKED.read_bytes() == before
    written = target.read_text()
    assert '"aiProvider": "ollama"' in written
    assert '"hostname": "meeting-ops"' in written
