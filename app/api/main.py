"""Main entry point for the Dienstplan FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.release_info import CURRENT_VERSION


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
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

    return api_app


app = create_app()
