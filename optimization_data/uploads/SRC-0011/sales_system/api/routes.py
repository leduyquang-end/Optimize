# api/routes.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime
import logging
from pydantic import BaseModel

from services.product_service import ProductService
from services.order_service import OrderService
from services.inventory_service import InventoryService
from services.notification_service import NotificationService
from services.analytics_service import AnalyticsService
from core.kernel import sales_kernel
from core.domain import OrderStatus
# THÊM DÒNG NÀY:
from core.events import event_publisher, EventType

logger = logging.getLogger(__name__)

# --- Pydantic Models ---
class ProductCreateRequest(BaseModel):
    name: str
    description: str
    price: float
    stock: int
    sku: str
    category: str

class ProductResponse(BaseModel):
    id: str
    name: str
    description: str
    price: float
    stock: int
    sku: str
    category: str
    created_at: datetime

class OrderItemRequest(BaseModel):
    product_id: str
    quantity: int

class AddressRequest(BaseModel):
    street: str
    city: str
    state: str
    zip_code: str
    country: str

class OrderCreateRequest(BaseModel):
    customer_id: str
    items: List[OrderItemRequest]
    shipping_address: AddressRequest

class OrderResponse(BaseModel):
    id: str
    customer_id: str
    items: List[dict]
    total: float
    status: str
    payment_status: str
    created_at: datetime

class PaymentRequest(BaseModel):
    order_id: str
    method: str = "credit_card"
    card_info: Optional[dict] = None

class UpdateStockRequest(BaseModel):
    quantity: int
    warehouse: Optional[str] = None

class DiscountRequest(BaseModel):
    amount: float
    coupon: Optional[str] = None
    total_items: int = 0

class ShippingRequest(BaseModel):
    method: str = "standard"
    weight_kg: float = 1.0
    order_total: float = 0
    destination: str = "domestic"

# --- Create App ---
def create_app():
    app = FastAPI(
        title="Sales System API",
        description="Multi-architecture sales system",
        version="1.0.0"
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Services
    product_service = ProductService()
    inventory_service = InventoryService()
    notification_service = NotificationService()
    analytics_service = AnalyticsService()
    order_service = OrderService(product_service)
    
    # --- Product Endpoints ---
    @app.get("/api/products", response_model=List[ProductResponse])
    async def get_products():
        products = product_service.get_all_products()
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": p.price.amount,
                "stock": p.stock,
                "sku": p.sku,
                "category": p.category,
                "created_at": p.created_at
            }
            for p in products
        ]
    
    @app.get("/api/products/{product_id}", response_model=ProductResponse)
    async def get_product(product_id: str):
        product = product_service.get_product(product_id)
        if not product:
            raise HTTPException(404, "Product not found")
        return {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price.amount,
            "stock": product.stock,
            "sku": product.sku,
            "category": product.category,
            "created_at": product.created_at
        }
    
    @app.post("/api/products", response_model=ProductResponse, status_code=201)
    async def create_product(request: ProductCreateRequest):
        try:
            product = product_service.create_product(
                name=request.name,
                description=request.description,
                price=request.price,
                stock=request.stock,
                sku=request.sku,
                category=request.category
            )
            return {
                "id": product.id,
                "name": product.name,
                "description": product.description,
                "price": product.price.amount,
                "stock": product.stock,
                "sku": product.sku,
                "category": product.category,
                "created_at": product.created_at
            }
        except ValueError as e:
            raise HTTPException(400, str(e))
    
    @app.get("/api/products/search")
    async def search_products(q: str = Query(..., min_length=1)):
        products = product_service.search_products(q)
        return [
            {"id": p.id, "name": p.name, "price": p.price.amount, "stock": p.stock}
            for p in products
        ]
    
    @app.get("/api/products/categories")
    async def get_categories():
        return {"categories": product_service.get_categories()}
    
    # --- Order Endpoints ---
    @app.post("/api/orders", response_model=OrderResponse, status_code=201)
    async def create_order(request: OrderCreateRequest):
        try:
            items = [{"product_id": item.product_id, "quantity": item.quantity} for item in request.items]
            order = order_service.create_order(
                customer_id=request.customer_id,
                items=items,
                shipping_address=request.shipping_address.dict()
            )
            return {
                "id": order.id,
                "customer_id": order.customer_id,
                "items": [
                    {
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "price": item.price.amount,
                        "subtotal": item.subtotal.amount
                    }
                    for item in order.items
                ],
                "total": order.total.amount,
                "status": order.status.value,
                "payment_status": order.payment_status.value,
                "created_at": order.created_at
            }
        except ValueError as e:
            raise HTTPException(400, str(e))
    
    @app.get("/api/orders/{order_id}", response_model=OrderResponse)
    async def get_order(order_id: str):
        order = order_service.get_order(order_id)
        if not order:
            raise HTTPException(404, "Order not found")
        return {
            "id": order.id,
            "customer_id": order.customer_id,
            "items": [
                {
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "price": item.price.amount,
                    "subtotal": item.subtotal.amount
                }
                for item in order.items
            ],
            "total": order.total.amount,
            "status": order.status.value,
            "payment_status": order.payment_status.value,
            "created_at": order.created_at
        }
    
    @app.get("/api/orders/customer/{customer_id}")
    async def get_customer_orders(customer_id: str):
        orders = order_service.get_customer_orders(customer_id)
        return [
            {
                "id": o.id,
                "total": o.total.amount,
                "status": o.status.value,
                "created_at": o.created_at
            }
            for o in orders
        ]
    
    @app.put("/api/orders/{order_id}/status")
    async def update_order_status(order_id: str, status: str):
        try:
            status_enum = OrderStatus(status)
            success = order_service.update_order_status(order_id, status_enum)
            if not success:
                raise HTTPException(404, "Order not found")
            return {"message": f"Order status updated to {status}"}
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")
    
    @app.post("/api/orders/{order_id}/cancel")
    async def cancel_order(order_id: str, reason: Optional[str] = None):
        success = order_service.cancel_order(order_id, reason)
        if not success:
            raise HTTPException(404, "Order not found or cannot be cancelled")
        return {"message": "Order cancelled"}
    
    # --- Inventory Endpoints ---
    @app.get("/api/inventory")
    async def get_inventory():
        return inventory_service.get_all_inventory()
    
    @app.get("/api/inventory/{product_id}")
    async def get_product_inventory(product_id: str):
        stock = inventory_service.get_stock(product_id)
        return {"product_id": product_id, "stock": stock}
    
    @app.put("/api/inventory/{product_id}")
    async def update_inventory(product_id: str, request: UpdateStockRequest):
        success = inventory_service.update_stock(product_id, request.quantity, request.warehouse)
        if not success:
            raise HTTPException(400, "Failed to update inventory")
        return {"message": "Inventory updated"}
    
    @app.get("/api/inventory/warehouses")
    async def get_warehouses():
        return {"warehouses": inventory_service.get_warehouses()}
    
    @app.get("/api/inventory/low-stock")
    async def get_low_stock(threshold: Optional[int] = 10):
        return {"low_stock_items": inventory_service.get_low_stock_items(threshold)}
    
    # --- Payment Endpoints ---
    @app.post("/api/payments/process")
    async def process_payment(request: PaymentRequest):
        try:
            order = order_service.get_order(request.order_id)
            if not order:
                raise HTTPException(404, "Order not found")
            
            result = sales_kernel.execute_plugin(
                "payment.plugin",
                method=request.method,
                amount=order.total.amount,
                currency=order.total.currency
            )
            
            if result.get("success"):
                order_service.update_payment_status(request.order_id, OrderStatus.CONFIRMED)
                return {
                    "success": True,
                    "payment_id": result["payment_id"],
                    "order_id": request.order_id,
                    "amount": result["amount"]
                }
            else:
                return {"success": False, "message": "Payment failed"}
        except Exception as e:
            raise HTTPException(500, f"Payment processing failed: {str(e)}")
    
    # --- Discount Endpoints ---
    @app.post("/api/discounts/calculate")
    async def calculate_discount(request: DiscountRequest):
        try:
            result = sales_kernel.execute_plugin(
                "discount.plugin",
                amount=request.amount,
                coupon=request.coupon,
                total_items=request.total_items
            )
            return result
        except Exception as e:
            raise HTTPException(500, f"Discount calculation failed: {str(e)}")
    
    # --- Shipping Endpoints ---
    @app.post("/api/shipping/calculate")
    async def calculate_shipping(request: ShippingRequest):
        try:
            result = sales_kernel.execute_plugin(
                "shipping.plugin",
                method=request.method,
                weight_kg=request.weight_kg,
                order_total=request.order_total,
                destination=request.destination
            )
            return result
        except Exception as e:
            raise HTTPException(500, f"Shipping calculation failed: {str(e)}")
    
    # --- Analytics Endpoints ---
    @app.get("/api/analytics/metrics")
    async def get_metrics():
        return analytics_service.get_metrics()
    
    @app.get("/api/analytics/sales")
    async def get_sales_report(days: int = 7):
        return analytics_service.get_sales_report(days)
    
    @app.get("/api/analytics/order-statistics")
    async def get_order_statistics():
        return order_service.get_order_statistics()
    
    @app.get("/api/analytics/customers")
    async def get_customer_analytics():
        return analytics_service.get_customer_analytics()
    
    @app.get("/api/analytics/funnel")
    async def get_conversion_funnel():
        return analytics_service.get_conversion_funnel()
    
    @app.get("/api/analytics/timeseries")
    async def get_time_series(metric: str = "orders", days: int = 30):
        return analytics_service.get_time_series_data(metric, days)
    
    # --- Notification Endpoints ---
    @app.get("/api/notifications/history")
    async def get_notification_history(recipient: Optional[str] = None, limit: int = 100):
        return {"notifications": notification_service.get_notification_history(recipient, limit)}
    
    # --- Plugin Endpoints ---
    @app.get("/api/plugins")
    async def list_plugins():
        return {"plugins": sales_kernel.list_plugins()}
    
    @app.get("/api/plugins/{plugin_id}")
    async def get_plugin(plugin_id: str):
        context = sales_kernel.get_plugin_context(plugin_id)
        if not context:
            raise HTTPException(404, "Plugin not found")
        return {
            "id": plugin_id,
            "status": context.status.value,
            "config": context.config
        }
    
    # --- Events Endpoints ---
    @app.get("/api/events")
    async def get_events(event_type: Optional[str] = None):
        # Đã import event_publisher và EventType ở đầu file
        if event_type:
            try:
                event_enum = EventType(event_type)
                events = event_publisher.get_events(event_enum)
            except ValueError:
                raise HTTPException(400, f"Invalid event type: {event_type}")
        else:
            events = event_publisher.get_events()
        
        return {
            "total": len(events),
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type.value,
                    "aggregate_id": e.aggregate_id,
                    "data": e.data,
                    "timestamp": e.timestamp.isoformat()
                }
                for e in events[-50:]
            ]
        }
    
    # --- Health Check ---
    @app.get("/api/health")
    async def health_check():
        try:
            events_count = len(event_publisher.get_events())
        except:
            events_count = 0
            
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "plugins": len(sales_kernel.list_plugins()),
            "products": product_service.get_total_products(),
            "orders": len(order_service.get_all_orders()),
            "events": events_count,  # THÊM DÒNG NÀY
            "version": "1.0.0"
        }
        
    return app