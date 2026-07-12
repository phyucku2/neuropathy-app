"""Top-level API router — mounts feature routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import emr, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(emr.router)

# Feature routers still to come: ingestion (lab upload, adl), capabilities (toggles),
# trajectory (AI), clinic. Domain logic already exists under app/ingestion, app/fhir,
# and app/services; those HTTP layers wire in once app auth + DB land.
