# api/__init__.py
from api.routes import create_app
from api.gateway import create_gateway_app

__all__ = ['create_app', 'create_gateway_app']