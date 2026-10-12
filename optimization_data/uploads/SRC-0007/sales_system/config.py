# config.py
import os
from typing import Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    """Application configuration"""
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///sales.db")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Email
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    
    # Payment
    PAYMENT_GATEWAY_URL: str = os.getenv("PAYMENT_GATEWAY_URL", "https://payment-gateway.com")
    PAYMENT_API_KEY: str = os.getenv("PAYMENT_API_KEY", "")
    
    # Inventory
    LOW_STOCK_THRESHOLD: int = int(os.getenv("LOW_STOCK_THRESHOLD", 10))
    
    # Analytics
    ANALYTICS_RETENTION_DAYS: int = int(os.getenv("ANALYTICS_RETENTION_DAYS", 90))
    
    # Plugins
    PLUGIN_CONFIG: Dict[str, Any] = {
        "payment.plugin": {
            "gateway_url": PAYMENT_GATEWAY_URL,
            "api_key": PAYMENT_API_KEY,
            "supported_methods": ["credit_card", "paypal", "bank_transfer"]
        },
        "inventory.plugin": {
            "low_stock_threshold": LOW_STOCK_THRESHOLD
        },
        "discount.plugin": {
            "discounts": {
                "SUMMER2024": 0.20,
                "WELCOME10": 0.10,
                "FLASH50": 0.50,
                "BULK10": 0.15
            }
        },
        "shipping.plugin": {
            "rates": {
                "standard": {"base": 5.99, "per_kg": 1.0},
                "express": {"base": 14.99, "per_kg": 2.0},
                "overnight": {"base": 29.99, "per_kg": 3.0}
            },
            "free_shipping_threshold": 100.0
        }
    }
    
    @classmethod
    def get_plugin_config(cls, plugin_id: str) -> Dict[str, Any]:
        """Get plugin configuration"""
        return cls.PLUGIN_CONFIG.get(plugin_id, {})

config = Config()