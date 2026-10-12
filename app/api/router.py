from fastapi import APIRouter
from app.api.v1.lane_a_router import router as lane_a_router
from app.api.v1.lane_b_router import router as lane_b_router
from app.api.v1.optimize_router import router as optimize_router
from app.api.v1.verification_router import router as verification_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(lane_a_router)
api_router.include_router(lane_b_router)
api_router.include_router(optimize_router)
api_router.include_router(verification_router)
