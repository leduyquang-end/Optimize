# core/plugins.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class PluginStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"

@dataclass
class PluginContext:
    plugin_id: str
    status: PluginStatus = PluginStatus.INACTIVE
    config: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)

class Plugin(ABC):
    """Base plugin interface"""
    
    @abstractmethod
    def get_id(self) -> str:
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        pass
    
    @abstractmethod
    def get_version(self) -> str:
        pass
    
    def get_default_config(self) -> Dict[str, Any]:
        """Override to provide default configuration"""
        return {}
    
    @abstractmethod
    def initialize(self, context: PluginContext):
        """Initialize the plugin"""
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute plugin operation"""
        pass
    
    @abstractmethod
    def destroy(self):
        """Cleanup plugin resources"""
        pass

class PaymentPlugin(Plugin):
    """Payment processing plugin"""
    
    def get_id(self) -> str:
        return "payment.plugin"
    
    def get_name(self) -> str:
        return "Payment Processing Plugin"
    
    def get_version(self) -> str:
        return "1.0.0"
    
    def get_default_config(self) -> Dict[str, Any]:
        return {
            "gateway_url": "https://payment-gateway.com",
            "api_key": "",
            "supported_methods": ["credit_card", "paypal", "bank_transfer"]
        }
    
    def initialize(self, context: PluginContext):
        logger.info(f"Initializing payment plugin: {context.config.get('gateway_url', 'default')}")
        if not context.config.get("api_key"):
            logger.warning("Payment API key not configured")
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        method = kwargs.get("method", "credit_card")
        amount = kwargs.get("amount", 0)
        currency = kwargs.get("currency", "USD")
        customer_id = kwargs.get("customer_id", "")
        card_info = kwargs.get("card_info", {})
        
        # Simulate payment processing
        payment_id = f"pay_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Processing {method} payment of {amount} {currency}")
        
        # Simulate success (in real system, would call payment gateway)
        return {
            "success": True,
            "payment_id": payment_id,
            "amount": amount,
            "currency": currency,
            "method": method,
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        }
    
    def destroy(self):
        logger.info("Payment plugin destroyed")

class InventoryPlugin(Plugin):
    """Inventory management plugin"""
    
    def __init__(self):
        self._stock: Dict[str, int] = {}
        self._reservations: Dict[str, Dict[str, int]] = {}
    
    def get_id(self) -> str:
        return "inventory.plugin"
    
    def get_name(self) -> str:
        return "Inventory Management Plugin"
    
    def get_version(self) -> str:
        return "1.0.0"
    
    def get_default_config(self) -> Dict[str, Any]:
        return {
            "low_stock_threshold": 10,
            "warehouses": ["WH-01", "WH-02"]
        }
    
    def initialize(self, context: PluginContext):
        # Initialize with sample stock
        self._stock = {
            "prod1": 100,
            "prod2": 50,
            "prod3": 75,
            "prod4": 30,
            "prod5": 200
        }
        context.data["stock"] = self._stock
        logger.info(f"Inventory plugin initialized with {len(self._stock)} products")
    
    def execute(self, **kwargs) -> Any:
        action = kwargs.get("action", "check")
        
        if action == "check":
            product_id = kwargs.get("product_id")
            return self._check_stock(product_id)
        elif action == "update":
            product_id = kwargs.get("product_id")
            quantity = kwargs.get("quantity", 0)
            return self._update_stock(product_id, quantity)
        elif action == "reserve":
            product_id = kwargs.get("product_id")
            quantity = kwargs.get("quantity", 0)
            return self._reserve_stock(product_id, quantity)
        elif action == "list":
            return self._list_stock()
        elif action == "low_stock":
            threshold = kwargs.get("threshold", 10)
            return self._get_low_stock(threshold)
        
        return None
    
    def _check_stock(self, product_id: str) -> int:
        """Check stock for a product"""
        return self._stock.get(product_id, 0)
    
    def _update_stock(self, product_id: str, quantity: int) -> Dict[str, Any]:
        """Update stock for a product"""
        old_quantity = self._stock.get(product_id, 0)
        self._stock[product_id] = max(0, quantity)
        
        return {
            "product_id": product_id,
            "old_quantity": old_quantity,
            "new_quantity": self._stock[product_id]
        }
    
    def _reserve_stock(self, product_id: str, quantity: int) -> Optional[str]:
        """Reserve stock for an order"""
        current = self._check_stock(product_id)
        if current < quantity:
            return None
        
        # Create reservation
        if product_id not in self._reservations:
            self._reservations[product_id] = {}
        
        reservation_id = f"res_{uuid.uuid4().hex[:8]}"
        self._reservations[product_id][reservation_id] = quantity
        
        # Update stock
        self._update_stock(product_id, current - quantity)
        
        return reservation_id
    
    def _list_stock(self) -> Dict[str, int]:
        """List all stock"""
        return self._stock.copy()
    
    def _get_low_stock(self, threshold: int) -> List[Dict[str, Any]]:
        """Get products with low stock"""
        result = []
        for product_id, stock in self._stock.items():
            if stock < threshold:
                result.append({
                    "product_id": product_id,
                    "stock": stock
                })
        return result
    
    def destroy(self):
        logger.info("Inventory plugin destroyed")

class DiscountPlugin(Plugin):
    """Discount calculation plugin"""
    
    def __init__(self):
        self._kernel = None
    
    def set_kernel(self, kernel):
        """Set kernel reference"""
        self._kernel = kernel
    
    def get_id(self) -> str:
        return "discount.plugin"
    
    def get_name(self) -> str:
        return "Discount Calculation Plugin"
    
    def get_version(self) -> str:
        return "1.0.0"
    
    def get_default_config(self) -> Dict[str, Any]:
        return {
            "discounts": {
                "SUMMER2024": 0.20,
                "WELCOME10": 0.10,
                "FLASH50": 0.50,
                "BULK10": 0.15,
                "VIP20": 0.20,
                "NEWYEAR2024": 0.25
            },
            "bulk_discount_threshold": 5,
            "bulk_discount_rate": 0.10
        }
    
    def initialize(self, context: PluginContext):
        logger.info(f"Discount plugin initialized with {len(context.config.get('discounts', {}))} discounts")
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        amount = kwargs.get("amount", 0)
        coupon = kwargs.get("coupon", "")
        total_items = kwargs.get("total_items", 0)
        
        # Get config from context (passed during registration)
        # We'll use the context stored in the plugin system
        discount_percentage = self._get_discount_rate(coupon, total_items)
        
        discount_amount = amount * discount_percentage
        
        return {
            "original_amount": amount,
            "discount_percentage": discount_percentage * 100,
            "discount_amount": discount_amount,
            "final_amount": round(amount - discount_amount, 2),
            "coupon_applied": coupon if discount_percentage > 0 else None
        }
    
    def _get_discount_rate(self, coupon: str, total_items: int) -> float:
        """Get discount rate based on coupon and items"""
        config = self.get_default_config()
        
        # Check coupon
        if coupon and coupon in config.get("discounts", {}):
            return config["discounts"][coupon]
        
        # Bulk discount
        threshold = config.get("bulk_discount_threshold", 5)
        if total_items >= threshold:
            return config.get("bulk_discount_rate", 0.10)
        
        return 0.0
    
    def destroy(self):
        logger.info("Discount plugin destroyed")

class ShippingPlugin(Plugin):
    """Shipping calculation plugin"""
    
    def __init__(self):
        self._kernel = None
    
    def set_kernel(self, kernel):
        """Set kernel reference"""
        self._kernel = kernel
    
    def get_id(self) -> str:
        return "shipping.plugin"
    
    def get_name(self) -> str:
        return "Shipping Calculation Plugin"
    
    def get_version(self) -> str:
        return "1.0.0"
    
    def get_default_config(self) -> Dict[str, Any]:
        return {
            "rates": {
                "standard": {"base": 5.99, "per_kg": 1.0, "days": "5-7"},
                "express": {"base": 14.99, "per_kg": 2.0, "days": "2-3"},
                "overnight": {"base": 29.99, "per_kg": 3.0, "days": "1"},
                "international": {"base": 39.99, "per_kg": 5.0, "days": "7-14"}
            },
            "free_shipping_threshold": 100.0,
            "international_surcharge": 2.0
        }
    
    def initialize(self, context: PluginContext):
        logger.info(f"Shipping plugin initialized with {len(context.config.get('rates', {}))} shipping methods")
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        method = kwargs.get("method", "standard")
        weight_kg = kwargs.get("weight_kg", 1.0)
        order_total = kwargs.get("order_total", 0)
        destination = kwargs.get("destination", "domestic")
        
        config = self.get_default_config()
        
        # Check free shipping
        free_threshold = config.get("free_shipping_threshold", 100.0)
        if order_total >= free_threshold:
            return {
                "method": "free",
                "cost": 0,
                "delivery_days": "5-7",
                "weight": weight_kg,
                "destination": destination
            }
        
        # Calculate shipping cost
        rates = config.get("rates", {})
        
        if method not in rates:
            method = "standard"
        
        rate = rates[method]
        cost = rate["base"] + (rate["per_kg"] * weight_kg)
        
        # International shipping
        if destination == "international":
            surcharge = config.get("international_surcharge", 2.0)
            cost = cost * surcharge
        
        return {
            "method": method,
            "cost": round(cost, 2),
            "delivery_days": rate.get("days", "5-7"),
            "weight": weight_kg,
            "destination": destination
        }
    
    def destroy(self):
        logger.info("Shipping plugin destroyed")