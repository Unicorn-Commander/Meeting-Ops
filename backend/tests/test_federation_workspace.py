"""Per-org, per-target federation workspace map (L5).

Covers:
  * federation_workspace_for override / fallback / None
  * never another org or a global default
  * auto-push env fallback must not enable unconfigured tenants
  * inbound org_for_workspace_id still binds Organization.workspace_id
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from services.integrations.org_config import (
    INTEGRATION_CONTACT_OPS,
    INTEGRATION_PROJECT_OPS,
    federation_workspace_for,
    parse_federation_workspace_id,
    resolve_project_ops,
)

MO_WS = "0190a000-7e57-7000-8000-00000000c007"
CO_WS = "019ec30c-7dbb-7d29-be7e-47b08b6ec59e"
PO_WS = "019e50a3-d995-723f-ab66-0f765f92c0f4"


def _org(**kwargs):
    defaults = {
        "id": 1,
        "workspace_id": MO_WS,
        "integrations": {},
        "settings": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Override resolution
# ---------------------------------------------------------------------------


def test_parse_federation_workspace_id_accepts_uuid_and_rejects_garbage():
    assert parse_federation_workspace_id(CO_WS) == CO_WS
    assert parse_federation_workspace_id(CO_WS.upper()) == CO_WS
    assert parse_federation_workspace_id("") is None
    assert parse_federation_workspace_id("  ") is None
    assert parse_federation_workspace_id(None) is None
    assert parse_federation_workspace_id("not-a-uuid") is None
    assert parse_federation_workspace_id("ws-tenant-1") is None


def test_override_beats_org_workspace_per_target():
    org = _org(
        integrations={
            INTEGRATION_CONTACT_OPS: {"workspace_id": CO_WS},
            INTEGRATION_PROJECT_OPS: {"workspace_id": PO_WS},
        }
    )
    assert federation_workspace_for(org, INTEGRATION_CONTACT_OPS) == CO_WS
    assert federation_workspace_for(org, INTEGRATION_PROJECT_OPS) == PO_WS


def test_falls_back_to_org_workspace_when_override_absent():
    org = _org(integrations={})
    assert federation_workspace_for(org, INTEGRATION_CONTACT_OPS) == MO_WS
    assert federation_workspace_for(org, INTEGRATION_PROJECT_OPS) == MO_WS


def test_invalid_override_falls_back_to_org_workspace():
    org = _org(
        integrations={INTEGRATION_CONTACT_OPS: {"workspace_id": "not-a-uuid"}}
    )
    assert federation_workspace_for(org, INTEGRATION_CONTACT_OPS) == MO_WS


def test_returns_none_when_neither_override_nor_org_workspace():
    org = _org(workspace_id=None, integrations={})
    assert federation_workspace_for(org, INTEGRATION_CONTACT_OPS) is None
    assert federation_workspace_for(org, INTEGRATION_PROJECT_OPS) is None
    assert federation_workspace_for(None, INTEGRATION_CONTACT_OPS) is None


def test_unknown_target_returns_none():
    org = _org()
    assert federation_workspace_for(org, "brigade") is None
    assert federation_workspace_for(org, "") is None


def test_never_uses_another_orgs_workspace():
    org_a = _org(
        id=1,
        workspace_id=MO_WS,
        integrations={INTEGRATION_CONTACT_OPS: {"workspace_id": CO_WS}},
    )
    org_b = _org(id=2, workspace_id=None, integrations={})
    assert federation_workspace_for(org_a, INTEGRATION_CONTACT_OPS) == CO_WS
    assert federation_workspace_for(org_b, INTEGRATION_CONTACT_OPS) is None
    assert federation_workspace_for(org_b, INTEGRATION_PROJECT_OPS) is None


# ---------------------------------------------------------------------------
# Auto-push env fallback (prod multi-tenant safety)
# ---------------------------------------------------------------------------


def test_auto_push_env_fallback_off_does_not_enable_orgs_without_block(
    monkeypatch,
):
    """PROJECTOPS_AUTO_PUSH_ACTION_ITEMS must not turn pushing on for an
    org that never opted in when the env fallback is off (prod)."""
    monkeypatch.setenv("PROJECTOPS_AUTO_PUSH_ACTION_ITEMS", "true")
    monkeypatch.setenv("PROJECTOPS_AUTO_PUSH_ENV_FALLBACK", "false")
    org = _org(integrations={})
    monkeypatch.setattr(
        "services.integrations.org_config.get_organization",
        lambda *_a, **_k: org,
    )
    cfg = resolve_project_ops(None, org.id)
    assert cfg.source == "env_default"
    assert cfg.extra["auto_push_action_items"] is False


def test_auto_push_env_fallback_on_inherits_env_flag(monkeypatch):
    """Dogfood: orgs without a block still inherit the deploy env flag."""
    monkeypatch.setenv("PROJECTOPS_AUTO_PUSH_ACTION_ITEMS", "true")
    monkeypatch.setenv("PROJECTOPS_AUTO_PUSH_ENV_FALLBACK", "true")
    org = _org(integrations={})
    monkeypatch.setattr(
        "services.integrations.org_config.get_organization",
        lambda *_a, **_k: org,
    )
    cfg = resolve_project_ops(None, org.id)
    assert cfg.source == "env_default"
    assert cfg.extra["auto_push_action_items"] is True


def test_auto_push_org_block_opt_in_wins_when_fallback_off(monkeypatch):
    monkeypatch.setenv("PROJECTOPS_AUTO_PUSH_ACTION_ITEMS", "false")
    monkeypatch.setenv("PROJECTOPS_AUTO_PUSH_ENV_FALLBACK", "false")
    org = _org(
        integrations={
            INTEGRATION_PROJECT_OPS: {
                "enabled": True,
                "auto_push_action_items": True,
            }
        }
    )
    monkeypatch.setattr(
        "services.integrations.org_config.get_organization",
        lambda *_a, **_k: org,
    )
    cfg = resolve_project_ops(None, org.id)
    assert cfg.source == "org_override"
    assert cfg.enabled is True
    assert cfg.extra["auto_push_action_items"] is True


def test_auto_push_explicitly_disabled_org_stays_off_when_env_on(monkeypatch):
    monkeypatch.setenv("PROJECTOPS_AUTO_PUSH_ACTION_ITEMS", "true")
    monkeypatch.setenv("PROJECTOPS_AUTO_PUSH_ENV_FALLBACK", "true")
    org = _org(
        integrations={
            INTEGRATION_PROJECT_OPS: {
                "enabled": False,
                "auto_push_action_items": True,
            }
        }
    )
    monkeypatch.setattr(
        "services.integrations.org_config.get_organization",
        lambda *_a, **_k: org,
    )
    cfg = resolve_project_ops(None, org.id)
    assert cfg.source == "disabled"
    assert cfg.enabled is False
    assert cfg.extra["auto_push_action_items"] is False


# ---------------------------------------------------------------------------
# Inbound binding is unchanged
# ---------------------------------------------------------------------------


def test_inbound_org_for_workspace_id_ignores_integration_override(
    canonical_db_schema,
):
    """Customer-Ops still binds on Organization.workspace_id, never the
    outbound contact_ops / project_ops override."""
    from auth.models import Organization
    from database.database import SessionLocal
    from api.federation_meetings import org_for_workspace_id

    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:8]
        inbound = str(uuid.uuid4())
        co_override = str(uuid.uuid4())
        po_override = str(uuid.uuid4())
        org = Organization(
            name=f"Inbound {suffix}",
            slug=f"inbound-ws-{suffix}",
            is_active=True,
            workspace_id=inbound,
            integrations={
                INTEGRATION_CONTACT_OPS: {"workspace_id": co_override},
                INTEGRATION_PROJECT_OPS: {"workspace_id": po_override},
            },
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        assert org_for_workspace_id(db, inbound).id == org.id
        assert org_for_workspace_id(db, co_override) is None
        assert org_for_workspace_id(db, po_override) is None
        assert federation_workspace_for(org, INTEGRATION_CONTACT_OPS) == co_override
        assert federation_workspace_for(org, INTEGRATION_PROJECT_OPS) == po_override
    finally:
        db.close()
