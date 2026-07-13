"""Top-level API router — mounts feature routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, emr, health, ingestion, trajectory

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(emr.router)
api_router.include_router(ingestion.router)
api_router.include_router(trajectory.router)

# Feature routers still to come: capabilities (toggles), clinic. Domain logic already
# exists under app/fhir and app/services.
