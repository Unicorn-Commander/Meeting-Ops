from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from auth.models import Organization, User, UserOrganization

DEFAULT_ORG_SLUG = "magic-unicorn"
DEFAULT_ORG_NAME = "Magic Unicorn"
ORG_HEADER_NAME = "X-MeetingOps-Org"
ORG_QUERY_PARAM_NAMES = ("org", "org_slug")

GLOBAL_ADMIN_GROUPS = {
    "admin",
    "meeting-ops-admins",
    "meetingops-admin",
    "uc-admins",
    "app:meeting-ops-admin",
    "app:meetingops-admin",
    "app:meetingops:admin",
    "app:meeting-ops:admin",
}

ORG_ADMIN_PATTERN = re.compile(r"^app:meetingops:(?P<slug>[a-z0-9-]+):admin$")
NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


@dataclass
class ActiveOrganization:
    organization: Organization
    membership: Optional[UserOrganization]
    role: str


def normalize_group_name(group: str) -> str:
    normalized = group.strip().lower()
    if normalized.startswith("role:"):
        normalized = normalized[5:]
    return normalized


def normalize_org_slug(value: str) -> str:
    slug = NON_SLUG_CHARS.sub("-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("Organization slug cannot be empty")
    return slug


def display_name_from_slug(slug: str) -> str:
    return slug.replace("-", " ").title()


def parse_group_list(groups: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for group in groups:
        normalized = normalize_group_name(group)
        if normalized and normalized not in seen:
            seen.append(normalized)
    return seen


def is_global_admin(groups: Iterable[str]) -> bool:
    normalized = set(parse_group_list(groups))
    return bool(normalized & GLOBAL_ADMIN_GROUPS)


def extract_org_roles(groups: Iterable[str]) -> dict[str, str]:
    roles_by_slug: dict[str, str] = {}

    for group in parse_group_list(groups):
        if group.startswith("org:"):
            slug = normalize_org_slug(group.split(":", 1)[1])
            roles_by_slug.setdefault(slug, "user")
            continue

        match = ORG_ADMIN_PATTERN.match(group)
        if match:
            slug = normalize_org_slug(match.group("slug"))
            roles_by_slug[slug] = "admin"

    return roles_by_slug


def ensure_organization(
    db: Session,
    slug: str,
    *,
    name: Optional[str] = None,
) -> Organization:
    normalized_slug = normalize_org_slug(slug)
    organization = (
        db.query(Organization)
        .filter(Organization.slug == normalized_slug)
        .first()
    )
    if organization:
        return organization

    organization = Organization(
        name=name or display_name_from_slug(normalized_slug),
        slug=normalized_slug,
        is_active=True,
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def ensure_default_organization(db: Session) -> Organization:
    return ensure_organization(db, DEFAULT_ORG_SLUG, name=DEFAULT_ORG_NAME)


def sync_user_organizations(
    db: Session,
    user: User,
    groups: Iterable[str],
) -> list[UserOrganization]:
    org_roles = extract_org_roles(groups)

    # If we have NO group claims to act on, treat this as a "passive" sync —
    # do not touch the user's existing memberships. The empty-groups case
    # happens both for genuinely-new users AND for any code path that calls
    # this without forwarding the Keycloak groups header (api/auth/me through
    # forward-auth, internal helpers, tests). Wiping existing memberships in
    # the latter case is destructive.
    existing_memberships = (
        db.query(UserOrganization)
        .filter(UserOrganization.user_id == user.id)
        .all()
    )

    if not org_roles:
        if existing_memberships:
            # Already a member of at least one org. Leave them alone.
            return existing_memberships
        # Brand-new user, no group claims. Provision a private personal org
        # instead of dumping them into the platform default workspace where
        # they would see another tenant's sessions.
        personal_slug = f"{user.username}-personal"
        existing_org = (
            db.query(Organization)
            .filter(Organization.slug == personal_slug)
            .first()
        )
        if not existing_org:
            display = user.full_name or user.email or user.username
            ensure_organization(
                db,
                personal_slug,
                name=f"{display} (personal)",
            )
        org_roles = {personal_slug: "admin"}

    desired_roles: dict[int, str] = {}
    for slug, role in org_roles.items():
        organization = ensure_organization(db, slug)
        desired_roles[organization.id] = role

    existing_by_org_id = {
        membership.organization_id: membership
        for membership in existing_memberships
    }

    changed = False

    # Sync is additive: Keycloak group claims grant + refresh memberships,
    # they do NOT prune. Manual DB-level grants (set by admins outside the
    # group-claim flow) survive subsequent logins. To remove a membership,
    # delete the row directly or build an explicit admin endpoint — don't
    # rely on "absent claim" as the deletion signal.
    for organization_id, role in desired_roles.items():
        membership = existing_by_org_id.get(organization_id)
        if membership:
            if membership.role != role:
                membership.role = role
                changed = True
            continue

        db.add(
            UserOrganization(
                user_id=user.id,
                organization_id=organization_id,
                role=role,
            )
        )
        changed = True

    if changed:
        db.commit()

    db.refresh(user)
    return (
        db.query(UserOrganization)
        .filter(UserOrganization.user_id == user.id)
        .all()
    )


def get_requested_org_slug(request: Request) -> Optional[str]:
    header_value = request.headers.get(ORG_HEADER_NAME)
    if header_value:
        return normalize_org_slug(header_value)

    # Browser WebSockets and media tags cannot set custom headers, so allow
    # an explicit query-string selector for those transports.
    for name in ORG_QUERY_PARAM_NAMES:
        query_value = request.query_params.get(name)
        if query_value:
            return normalize_org_slug(query_value)

    return None


def resolve_active_organization(
    db: Session,
    request: Request,
    current_user: User,
) -> ActiveOrganization:
    requested_slug = get_requested_org_slug(request)

    if requested_slug:
        organization = (
            db.query(Organization)
            .filter(Organization.slug == requested_slug)
            .first()
        )
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )
    elif current_user.organizations:
        # User has at least one org membership. Pick the first as the implicit
        # active org when the frontend does not send an explicit slug. This
        # prevents 403s for users whose memberships do not include the platform
        # default (e.g. GFL/shafen-khan users). The frontend can override by
        # passing the X-Organization or ?org= selector.
        organization = current_user.organizations[0].organization
    else:
        # User has no memberships yet; auto-provision into the platform default.
        organization = ensure_default_organization(db)

    membership = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == current_user.id,
            UserOrganization.organization_id == organization.id,
        )
        .first()
    )

    if not membership and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this organization",
        )

    role = "superuser" if current_user.is_superuser else (membership.role if membership else "viewer")
    return ActiveOrganization(
        organization=organization,
        membership=membership,
        role=role,
    )
