"""
Project Integration API — cross-app project linking.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from database.database import get_db
from auth.dependencies import get_current_organization, get_current_user
from auth.organization import ActiveOrganization
from auth.models import User

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])


class ProjectResponse(BaseModel):
    id: int
    name: str
    slug: str
    app: str


# Mock data for stubbing when upstream apps aren't reachable
MOCK_PROJECTS = {
    "project-ops": [
        ProjectResponse(id=1, name="Q2 Roadmap", slug="q2-roadmap", app="project-ops"),
        ProjectResponse(id=2, name="Product Launch", slug="product-launch", app="project-ops"),
        ProjectResponse(id=3, name="Website Redesign", slug="website-redesign", app="project-ops"),
    ],
    "crisis-ops": [
        ProjectResponse(id=1, name="Incident Response Plan", slug="incident-response", app="crisis-ops"),
        ProjectResponse(id=2, name="DR Drill Q2", slug="dr-drill-q2", app="crisis-ops"),
    ],
}


@router.get("/{app}/projects", response_model=list[ProjectResponse])
async def list_projects(
    app: str,
    organization_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    active_org: ActiveOrganization = Depends(get_current_organization),
):
    if app not in ("project-ops", "crisis-ops"):
        raise HTTPException(status_code=400, detail="App must be 'project-ops' or 'crisis-ops'")
    if organization_id != active_org.organization.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Cannot fetch projects for a different organization")

    if app in MOCK_PROJECTS:
        return MOCK_PROJECTS[app]

    return []
