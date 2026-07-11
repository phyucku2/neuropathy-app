"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings

app = FastAPI(
    title="neuropathy-app backend",
    version="0.1.0",
    debug=settings.app_debug,
)
app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "neuropathy-app backend", "env": settings.app_env}
