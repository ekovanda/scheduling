"""Main entry point for the Dienstplan FastAPI application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.auth import validate_auth_config
from app.api.v1.router import api_v1_router
from app.release_info import CURRENT_VERSION


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    validate_auth_config()
    api_app = FastAPI(
        title="Dienstplan Scheduling Platform API",
        description=(
            "Unified backend API for veterinary clinic quarterly shift scheduling "
            "and lifecycle tracking."
        ),
        version=CURRENT_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Allow local development and Firebase Hosting frontend origins
    api_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_app.include_router(api_v1_router)

    # Mount compiled React SPA at root if frontend/dist exists
    frontend_dist = Path("frontend/dist")
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        api_app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")

    return api_app


app = create_app()
