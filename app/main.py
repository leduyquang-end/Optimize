import os
import sys

# Cho phép chạy trực tiếp "python app/main.py" (sys.path[0] đang trỏ vào thư mục app/)
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router

app = FastAPI(
    title="System Optimization Platform (Modular Monolith)",
    description="API Gateway and Core Domain Modules for Lane A (Manual) & Lane B (Auto Discovery) Optimization System.",
    version="1.0.0"
)

app.include_router(api_router)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")


@app.get("/")
async def root():
    """Trang chủ = app chọn lane (redirect sang /ui)."""
    return RedirectResponse(url="/ui", status_code=307)


@app.get("/health")
async def health():
    return {
        "system": "Optimization Platform",
        "architecture": "Modular Monolith",
        "status": "running",
        "docs": "/docs",
        "ui": "/ui"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
