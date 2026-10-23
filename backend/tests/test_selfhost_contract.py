"""Static contract checks for the public self-host path.

Docker is intentionally not required for this test. Runtime health, login, and
PAT behavior belong to the clean-room acceptance run described by the lane.
"""

# Assertions are the pytest contract language for this static artifact test.
# ruff: noqa: S101

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SELFHOST_FILES = (
    ROOT / "README.md",
    ROOT / "INSTALL.md",
    ROOT / "install-meeting-ops.sh",
    ROOT / "docker-compose.selfhost.yml",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_selfhost_files_exist() -> None:
    assert all(path.is_file() for path in SELFHOST_FILES)


def test_quickstart_is_the_clone_and_installer_path() -> None:
    readme = _text(ROOT / "README.md")
    assert (
        "git clone https://github.com/Unicorn-Commander/meeting-ops-community.git"
        in readme
    )
    assert "./install-meeting-ops.sh" in readme
    assert "docker-compose-full-stack.yml" not in readme
    assert "start-backend.sh" not in readme


def test_selfhost_does_not_publish_fixed_bootstrap_credentials() -> None:
    forbidden = (
        "meetingops" + "123",
        "admin" + "123",
        "change" + "me123",
        "gpt-oss-20b",
        "auth." + "unicorncommander.ai",
    )
    for path in SELFHOST_FILES:
        content = _text(path).lower()
        for value in forbidden:
            assert value not in content, f"{value!r} leaked into {path}"


def test_compose_is_loopback_and_core_only_by_default() -> None:
    compose = _text(ROOT / "docker-compose.selfhost.yml")
    assert "postgres:" in compose
    assert "redis:" in compose
    assert "backend:" in compose
    assert "web:" in compose
    assert '"127.0.0.1:${MEETING_OPS_POSTGRES_PORT:-5434}:5432"' in compose
    assert '"127.0.0.1:${MEETING_OPS_REDIS_PORT:-6381}:6379"' in compose
    assert '"127.0.0.1:${MEETING_OPS_API_PORT:-9050}:9050"' in compose
    assert '"127.0.0.1:${MEETING_OPS_WEB_PORT:-7777}:7777"' in compose
    assert "context: ./backend" in compose
    assert "dockerfile: Dockerfile" in compose
    assert "POSTGRES_PASSWORD" in compose
    assert "REDIS_PASSWORD" in compose
    assert "SECRET_KEY" in compose
    assert "gpt-oss-20b" not in compose.lower()
    assert "external: true" not in compose.lower()
    assert "profiles:" not in compose


def test_admin_and_pat_contract_is_documented() -> None:
    readme = _text(ROOT / "README.md")
    installer = _text(ROOT / "install-meeting-ops.sh")
    assert "/api/auth/login" in readme
    assert "/api/auth/pats" in readme
    assert "mops_pat_" in readme
    assert "MEETING_OPS_ADMIN_PASSWORD" in installer
    assert "personal_org=True" in installer


def test_installer_generates_database_and_admin_credentials() -> None:
    installer = _text(ROOT / "install-meeting-ops.sh")
    assert "POSTGRES_PASSWORD=$(generate_secret)" in installer
    assert "REDIS_PASSWORD=$(generate_secret)" in installer
    assert "SECRET_KEY=$(generate_secret)" in installer
    assert 'admin_username="$(generate_admin_username)"' in installer
    assert "MEETING_OPS_ADMIN_USERNAME=${admin_username}" in installer
    assert "MEETING_OPS_ADMIN_PASSWORD=$(generate_admin_password)" in installer
    assert 'chmod 600 "$ENV_FILE"' in installer
