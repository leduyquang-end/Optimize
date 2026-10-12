# app.py
import sys
import os

# Thêm đường dẫn hiện tại vào sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
import logging
from api.gateway import create_gateway_app
from services.product_service import ProductService
from services.order_service import OrderService
from services.inventory_service import InventoryService
from services.notification_service import NotificationService
from services.analytics_service import AnalyticsService
from core.kernel import sales_kernel
from core.plugins import PaymentPlugin, InventoryPlugin, DiscountPlugin, ShippingPlugin
from core.events import event_publisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def initialize_system():
    """Initialize the entire system"""
    logger.info("🚀 Initializing Sales System...")
    
    # Initialize services
    product_service = ProductService()
    inventory_service = InventoryService()
    notification_service = NotificationService()
    analytics_service = AnalyticsService()
    order_service = OrderService(product_service)
    
    # Register plugins
    logger.info("Registering plugins...")
    sales_kernel.register_plugin(PaymentPlugin())
    sales_kernel.register_plugin(InventoryPlugin())
    sales_kernel.register_plugin(DiscountPlugin())
    sales_kernel.register_plugin(ShippingPlugin())
    
    logger.info("✅ System initialized successfully!")
    
    return {
        "product_service": product_service,
        "order_service": order_service,
        "inventory_service": inventory_service,
        "notification_service": notification_service,
        "analytics_service": analytics_service
    }

def main():
    """Main entry point"""
    # Initialize system
    services = initialize_system()
    
    # Start API server
    app = create_gateway_app()
    
    logger.info("🌐 Starting API server at http://localhost:8000")
    logger.info("📚 API Documentation available at http://localhost:8000/docs")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

if __name__ == "__main__":
    main()