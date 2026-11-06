"""Central router for API v1."""

from fastapi import APIRouter

from app.api.v1.absences import router as absences_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.preassigned import router as preassigned_router
from app.api.v1.quarters import router as quarters_router
from app.api.v1.staff import router as staff_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(staff_router)
api_v1_router.include_router(absences_router)
api_v1_router.include_router(preassigned_router)
api_v1_router.include_router(quarters_router)
