"""Top-level API router — mounts feature routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)

# Feature routers slot in here as they're built:
#   ingestion (labs, adl), emr (SMART on FHIR connect/pull), capabilities (toggles),
#   trajectory (AI), clinic. Domain logic for these already exists under app/ingestion,
#   app/emr, app/fhir, and app/services; the HTTP layer wires in once auth + DB land.
