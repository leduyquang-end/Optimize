# api/gateway.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class APIGateway:
    def __init__(self, app: FastAPI):
        self.app = app
        self._setup_middleware()
        self._setup_error_handlers()
    
    def _setup_middleware(self):
        """Thiết lập middleware cho gateway"""
        
        # 1️⃣ LOGGING MIDDLEWARE
        @self.app.middleware("http")
        async def log_requests(request: Request, call_next):
            start_time = time.time()
            logger.info(f"➡️ {request.method} {request.url.path}")
            response = await call_next(request)
            duration = time.time() - start_time
            logger.info(f"⬅️ {response.status_code} - {duration:.3f}s")
            return response
        
        # 2️⃣ HEADERS MIDDLEWARE
        @self.app.middleware("http")
        async def add_headers(request: Request, call_next):
            response = await call_next(request)
            response.headers["X-API-Version"] = "1.0.0"
            response.headers["X-Response-Time"] = str(time.time())
            return response
        
        # 3️⃣ CORS MIDDLEWARE (nếu chưa có ở routes)
        @self.app.middleware("http")
        async def add_cors(request: Request, call_next):
            response = await call_next(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return response
    
    def _setup_error_handlers(self):
        """Thiết lập xử lý lỗi tập trung"""
        
        @self.app.exception_handler(Exception)
        async def handle_error(request: Request, exc: Exception):
            logger.error(f"Error: {exc}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": str(exc),
                    "timestamp": datetime.now().isoformat()
                }
            )
        
        @self.app.exception_handler(ValueError)
        async def handle_value_error(request: Request, exc: ValueError):
            logger.warning(f"ValueError: {exc}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Bad Request",
                    "message": str(exc),
                    "timestamp": datetime.now().isoformat()
                }
            )

def create_gateway_app():
    """Tạo app với API Gateway"""
    from api.routes import create_app
    
    app = create_app()
    gateway = APIGateway(app)
    return gateway.app