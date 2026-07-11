"""Top-level API router — mounts feature routers."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health

api_router = APIRouter()
api_router.include_router(health.router)

# Feature routers slot in here as they're built:
#   ingestion (biomech / labs / adl), capabilities (toggles), trajectory (AI), clinic.
