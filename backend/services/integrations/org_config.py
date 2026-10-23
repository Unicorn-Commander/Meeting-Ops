"""Per-org integration config resolution (v3.19.0).

Single source of truth for "what is integration X configured to do for
org Y?". Used by:

  - `api.integrations_org` (REST surface — GET/PUT/DELETE/test)
  - `services.brigade_client` / `services.brigade_writer`
  - `services.projectops_client` / `services.projectops_writer`
  - (future) Contact-Ops / Accounting-Ops / Stable consumers

Resolution order (caller-facing):

  1. If `Organization.integrations[<key>]` exists AND `enabled` is True
     -> use those values (decrypt api_key for actual upstream calls).
  2. If `Organization.integrations[<key>]` exists AND `enabled` is False
     -> the integration is OFF for this org. Writers no-op even if env
     vars are set. This is the "stop leaking creds across customer
     orgs" guarantee.
  3. If the integration block doesn't exist at all (or is missing
     fields) -> fall through to the legacy env-var defaults. This
     preserves backwards compatibility for existing orgs that haven't
     opted in yet.

The "doesn't exist" vs "explicitly disabled" distinction matters: a
brand-new customer org should keep working off env vars during rollout,
but an org admin who toggled Brigade OFF in the UI must NOT have their
data accidentally written to a globally-shared instance.

Secret handling: this module decrypts at the very edge (right before
returning to a caller that's about to make an HTTP call). The plaintext
key never leaves the resolver function — it's only ever returned inside
an ``IntegrationConfig`` and the caller passes it straight to
httpx.AsyncClient.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from secret_config import get_secret


logger = logging.getLogger(__name__)


# Canonical integration keys. These are the only valid values for the
# `{integration}` path parameter on the REST surface.
INTEGRATION_BRIGADE = "brigade"
INTEGRATION_PROJECT_OPS = "project_ops"
INTEGRATION_CONTACT_OPS = "contact_ops"
INTEGRATION_ACCOUNTING_OPS = "accounting_ops"
INTEGRATION_STABLE = "stable"

VALID_INTEGRATION_KEYS = (
    INTEGRATION_BRIGADE,
    INTEGRATION_PROJECT_OPS,
    INTEGRATION_CONTACT_OPS,
    INTEGRATION_ACCOUNTING_OPS,
    INTEGRATION_STABLE,
)

# Outbound Brigade exchanges that may carry a per-target workspace override
# under Organization.integrations[<key>].workspace_id. Inbound federation
# still binds exclusively on Organization.workspace_id.
_FEDERATION_WORKSPACE_TARGETS = frozenset(
    {INTEGRATION_PROJECT_OPS, INTEGRATION_CONTACT_OPS}
)


@dataclass(frozen=True)
class IntegrationConfig:
    """Resolved per-org integration config.

    ``source`` is one of:
      - "org_override"  -> values came from Organization.integrations
      - "env_default"   -> values came from env vars (legacy path)
      - "disabled"      -> the org explicitly turned this integration off

    Callers should branch on ``enabled``: when False they must short-
    circuit to a no-op regardless of whether ``api_key`` is populated.
    """

    enabled: bool
    api_base_url: Optional[str]
    api_key: Optional[str]  # cleartext, ready to put in an Authorization header
    extra: dict[str, Any]  # integration-specific fields (e.g. brigade tenancy_mode)
    source: str


# Default empty shape for a new integration block. Used when the UI asks
# for the current state of an integration that's never been touched.
def empty_integration_block(integration_key: str) -> dict[str, Any]:
    """Return the canonical empty shape for a given integration."""
    base: dict[str, Any] = {
        "enabled": False,
        "api_base_url": "",
        "api_key_encrypted": "",
    }
    if integration_key == INTEGRATION_BRIGADE:
        base["tenancy_mode"] = "shared"
        base["shared_agent_id"] = ""
    elif integration_key == INTEGRATION_PROJECT_OPS:
        base["default_project_number"] = ""
        # Auto-push of extracted action items to PO is opt-in (default
        # OFF) so model-flagged noise doesn't create task spam. Manual /
        # on-demand pushes are unaffected by this flag.
        base["auto_push_action_items"] = False
        # Per-target Brigade workspace for the MO -> Project-Ops exchange.
        # Empty -> fall through to Organization.workspace_id.
        base["workspace_id"] = ""
    elif integration_key == INTEGRATION_CONTACT_OPS:
        # Per-target Brigade workspace for the MO -> Contact-Ops exchange.
        # Empty -> fall through to Organization.workspace_id.
        base["workspace_id"] = ""
    return base


def _decrypt_or_none(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt a Fernet-encrypted secret. Returns None when input is
    empty or decryption fails (log + swallow — a malformed ciphertext
    must not crash the writer pipeline)."""
    if not ciphertext:
        return None
    try:
        # Lazy import so the cryptography module isn't a hard import-time
        # dependency for non-integration code paths.
        from services.providers.crypto import decrypt_api_key

        return decrypt_api_key(ciphertext)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "integrations.org_config: failed to decrypt api_key (corrupt "
            "ciphertext or wrong PROVIDER_ENCRYPTION_KEY?): %s",
            exc,
        )
        return None


def _block_for(organization: Any, integration_key: str) -> Optional[dict[str, Any]]:
    """Pull the raw config dict for ``integration_key`` off the org.
    Returns None when the org has nothing stored (= fall through to
    env defaults)."""
    raw = getattr(organization, "integrations", None) or {}
    if not isinstance(raw, dict):
        return None
    block = raw.get(integration_key)
    if not isinstance(block, dict):
        return None
    return block


def parse_federation_workspace_id(value: Any) -> Optional[str]:
    """Canonical UUID string, or None when empty / not a UUID.

    Used to validate ``integrations.<target>.workspace_id`` on write and
    to ignore a corrupt override on read. ``Organization.workspace_id``
    is not required to be a UUID (tests and some deploys use other
    strings), so the org-column fallback does not go through this.
    """
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError, TypeError):
        return None


def federation_workspace_for(org: Any, target: str) -> Optional[str]:
    """Workspace id for an outbound Brigade exchange to ``target``.

    Returns ``integrations.<target>.workspace_id`` when that override is
    a valid UUID, else ``Organization.workspace_id``, else None. Never
    falls back to another org or a global default. ``target`` is an
    integration key (``contact_ops`` / ``project_ops``). Unknown targets
    return None so a typo cannot silently send the org column.
    """
    if org is None:
        return None
    key = (target or "").strip()
    if key not in _FEDERATION_WORKSPACE_TARGETS:
        logger.debug(
            "federation_workspace_for: unknown target %r org=%s",
            target,
            getattr(org, "id", None),
        )
        return None
    block = _block_for(org, key)
    if block is not None:
        raw_override = block.get("workspace_id")
        if isinstance(raw_override, str) and raw_override.strip():
            override = parse_federation_workspace_id(raw_override)
            if override:
                return override
            logger.debug(
                "federation_workspace_for: ignoring invalid %s "
                "workspace_id override org=%s",
                key,
                getattr(org, "id", None),
            )
    org_ws = getattr(org, "workspace_id", None)
    if isinstance(org_ws, str) and org_ws.strip():
        return org_ws.strip()
    return None


def get_organization(db: Session, organization_id: int) -> Optional[Any]:
    """Convenience loader. Centralized so the import sites stay tidy."""
    from auth.models import Organization

    return (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )


# ---------------------------------------------------------------------------
# Per-integration resolvers. Each one knows its own env-var fallback shape
# so the writer can just call resolve_*(db, org_id) and branch on enabled.
# ---------------------------------------------------------------------------


def resolve_brigade(
    db: Session, organization_id: Optional[int]
) -> IntegrationConfig:
    """Resolve Brigade config for an org.

    Org overrides win when present; otherwise we honor the existing env
    vars (BRIGADE_API_BASE_URL, BRIGADE_API_KEY, BRIGADE_TENANCY_MODE,
    BRIGADE_SHARED_AGENT_ID) so unmigrated deployments keep working.

    Disabled: when the org has an integrations.brigade block with
    enabled=False, we return enabled=False even if BRIGADE_API_KEY is
    set in env. That's the "no cross-org leakage" guarantee — an org
    that opted out cannot accidentally write to a shared Brigade.
    """
    block: Optional[dict[str, Any]] = None
    if organization_id is not None:
        org = get_organization(db, organization_id)
        if org is not None:
            block = _block_for(org, INTEGRATION_BRIGADE)

    if block is not None:
        enabled = bool(block.get("enabled"))
        if not enabled:
            return IntegrationConfig(
                enabled=False,
                api_base_url=None,
                api_key=None,
                extra={},
                source="disabled",
            )
        api_base_url = (block.get("api_base_url") or "").strip() or None
        api_key = _decrypt_or_none(block.get("api_key_encrypted"))
        tenancy_mode = (block.get("tenancy_mode") or "shared").strip() or "shared"
        shared_agent_id = (block.get("shared_agent_id") or "").strip() or None
        return IntegrationConfig(
            enabled=True,
            api_base_url=api_base_url,
            api_key=api_key,
            extra={
                "tenancy_mode": tenancy_mode,
                "shared_agent_id": shared_agent_id,
            },
            source="org_override",
        )

    # Fall through to env defaults — preserves pre-v3.19 behavior.
    env_key = get_secret("BRIGADE_API_KEY") or os.getenv("BRIGADE_ADMIN_KEY")
    env_url = os.getenv("BRIGADE_API_BASE_URL")
    env_tenancy = os.getenv("BRIGADE_TENANCY_MODE", "shared")
    env_shared_agent = os.getenv("BRIGADE_SHARED_AGENT_ID")
    # In the env-default path "enabled" tracks whether an API key is
    # actually configured. With no key the brigade_client is already in
    # log-only mode anyway; surfacing enabled=False here keeps the
    # writer's branch logic simple.
    return IntegrationConfig(
        enabled=bool(env_key),
        api_base_url=env_url,
        api_key=env_key,
        extra={
            "tenancy_mode": env_tenancy,
            "shared_agent_id": env_shared_agent,
        },
        source="env_default",
    )


def resolve_project_ops(
    db: Session, organization_id: Optional[int]
) -> IntegrationConfig:
    """Resolve Project-Ops config for an org. Same disabled / override /
    env-default semantics as ``resolve_brigade``.

    ``extra["default_project_number"]`` is the per-org default project the
    writer targets when neither the session->PO link nor a per-meeting
    override is set. This is the v3.19 home for the value that v3.17 put
    in ``Organization.settings.projectops_default_project_number`` — the
    writer falls back to that legacy field if the new one is absent.

    ``extra["auto_push_action_items"]`` gates the AUTOMATIC outbound push
    of extracted action items to PO on meeting completion. It defaults OFF
    so model-flagged items don't create task noise; an org admin opts in
    per-org. For orgs on the env-default path (no integration block) the
    default comes from the ``PROJECTOPS_AUTO_PUSH_ACTION_ITEMS`` deploy
    flag (also OFF by default) **only when**
    ``PROJECTOPS_AUTO_PUSH_ENV_FALLBACK`` is true (dogfood default). When
    that fallback is false (prod multi-tenant compose), orgs that never
    set a project_ops block never inherit the env flag — pushing happens
    only when the org's own ``integrations.project_ops`` says enabled +
    auto_push. This flag does NOT affect extraction, storage, in-app
    display, read-only lifecycle reconciliation, or any future explicit
    review-then-push — only the auto-push. Meeting-Ops never writes
    Project-Ops Task status.
    """
    block: Optional[dict[str, Any]] = None
    legacy_default: Optional[str] = None
    if organization_id is not None:
        org = get_organization(db, organization_id)
        if org is not None:
            block = _block_for(org, INTEGRATION_PROJECT_OPS)
            # Legacy field from the v3.17 action-item bridge — kept readable
            # so we don't break orgs that set it before v3.19 shipped.
            settings = getattr(org, "settings", None) or {}
            if isinstance(settings, dict):
                v = settings.get("projectops_default_project_number")
                if isinstance(v, str) and v.strip():
                    legacy_default = v.strip()

    if block is not None:
        enabled = bool(block.get("enabled"))
        if not enabled:
            return IntegrationConfig(
                enabled=False,
                api_base_url=None,
                api_key=None,
                extra={
                    "default_project_number": None,
                    "auto_push_action_items": False,
                },
                source="disabled",
            )
        api_base_url = (block.get("api_base_url") or "").strip() or None
        api_key = _decrypt_or_none(block.get("api_key_encrypted"))
        default_project = (block.get("default_project_number") or "").strip() or None
        if not default_project and legacy_default:
            default_project = legacy_default
        # Per-org opt-in for the automatic action-item push. Absent key ->
        # default OFF (matches empty_integration_block); explicit per-org
        # value always wins over the deploy-level default.
        auto_push = bool(block.get("auto_push_action_items", False))
        return IntegrationConfig(
            enabled=True,
            api_base_url=api_base_url,
            api_key=api_key,
            extra={
                "default_project_number": default_project,
                "auto_push_action_items": auto_push,
            },
            source="org_override",
        )

    # Env-default fallback. Orgs without an integration block inherit the
    # deploy-level auto-push default (PROJECTOPS_AUTO_PUSH_ACTION_ITEMS,
    # itself OFF by default) only when PROJECTOPS_AUTO_PUSH_ENV_FALLBACK
    # is on. Prod compose turns the fallback off so a global env cannot
    # enable push for every tenant.
    from config.features import (
        projectops_auto_push_action_items,
        projectops_auto_push_env_fallback,
    )

    env_key = os.getenv("PROJECTOPS_API_KEY")
    env_url = os.getenv("PROJECTOPS_BASE_URL") or os.getenv(
        "PROJECTOPS_API_BASE_URL"
    )
    env_auto_push = False
    if projectops_auto_push_env_fallback():
        env_auto_push = projectops_auto_push_action_items()
    return IntegrationConfig(
        enabled=bool(env_key),
        api_base_url=env_url,
        api_key=env_key,
        extra={
            "default_project_number": legacy_default,
            "auto_push_action_items": bool(env_auto_push),
        },
        source="env_default",
    )


def _resolve_simple(
    db: Session,
    organization_id: Optional[int],
    integration_key: str,
    env_key_var: str,
    env_url_var: str,
) -> IntegrationConfig:
    """Shared resolver shape for the not-yet-implemented-writer
    integrations (Contact-Ops / Accounting-Ops / Stable). Keeps a
    consistent disabled / override / env-default branching pattern so
    when their writers land, they slot into the same protocol."""
    block: Optional[dict[str, Any]] = None
    if organization_id is not None:
        org = get_organization(db, organization_id)
        if org is not None:
            block = _block_for(org, integration_key)
    if block is not None:
        enabled = bool(block.get("enabled"))
        if not enabled:
            return IntegrationConfig(
                enabled=False, api_base_url=None, api_key=None, extra={}, source="disabled"
            )
        return IntegrationConfig(
            enabled=True,
            api_base_url=(block.get("api_base_url") or "").strip() or None,
            api_key=_decrypt_or_none(block.get("api_key_encrypted")),
            extra={},
            source="org_override",
        )
    env_key = os.getenv(env_key_var)
    return IntegrationConfig(
        enabled=bool(env_key),
        api_base_url=os.getenv(env_url_var),
        api_key=env_key,
        extra={},
        source="env_default",
    )


def resolve_contact_ops(
    db: Session, organization_id: Optional[int]
) -> IntegrationConfig:
    return _resolve_simple(
        db,
        organization_id,
        INTEGRATION_CONTACT_OPS,
        "CONTACTOPS_API_KEY",
        "CONTACTOPS_BASE_URL",
    )


def resolve_accounting_ops(
    db: Session, organization_id: Optional[int]
) -> IntegrationConfig:
    return _resolve_simple(
        db,
        organization_id,
        INTEGRATION_ACCOUNTING_OPS,
        "ACCOUNTINGOPS_API_KEY",
        "ACCOUNTINGOPS_BASE_URL",
    )


def resolve_stable(
    db: Session, organization_id: Optional[int]
) -> IntegrationConfig:
    return _resolve_simple(
        db,
        organization_id,
        INTEGRATION_STABLE,
        "STABLE_API_KEY",
        "STABLE_BASE_URL",
    )


__all__ = [
    "IntegrationConfig",
    "INTEGRATION_BRIGADE",
    "INTEGRATION_PROJECT_OPS",
    "INTEGRATION_CONTACT_OPS",
    "INTEGRATION_ACCOUNTING_OPS",
    "INTEGRATION_STABLE",
    "VALID_INTEGRATION_KEYS",
    "empty_integration_block",
    "parse_federation_workspace_id",
    "federation_workspace_for",
    "resolve_brigade",
    "resolve_project_ops",
    "resolve_contact_ops",
    "resolve_accounting_ops",
    "resolve_stable",
    "get_organization",
]
