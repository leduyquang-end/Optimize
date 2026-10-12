# services/inventory_service.py
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
from core.events import EventType, DomainEvent, event_publisher

logger = logging.getLogger(__name__)

class InventoryService:
    def __init__(self):
        self._inventory: Dict[str, Dict[str, Any]] = {}
        self._initialize_inventory()
    
    def _initialize_inventory(self):
        self._inventory = {
            "prod1": {"quantity": 100, "warehouse": "WH-01", "last_updated": datetime.now()},
            "prod2": {"quantity": 50, "warehouse": "WH-01", "last_updated": datetime.now()},
            "prod3": {"quantity": 75, "warehouse": "WH-02", "last_updated": datetime.now()},
            "prod4": {"quantity": 30, "warehouse": "WH-01", "last_updated": datetime.now()},
            "prod5": {"quantity": 200, "warehouse": "WH-02", "last_updated": datetime.now()}
        }
        logger.info(f"📦 Inventory initialized with {len(self._inventory)} products")
    
    def get_stock(self, product_id: str) -> int:
        return self._inventory.get(product_id, {}).get("quantity", 0)
    
    def update_stock(self, product_id: str, quantity: int, warehouse: str = None) -> bool:
        if product_id not in self._inventory:
            self._inventory[product_id] = {
                "quantity": 0,
                "warehouse": warehouse or "WH-01",
                "last_updated": datetime.now()
            }
        
        self._inventory[product_id]["quantity"] = quantity
        self._inventory[product_id]["last_updated"] = datetime.now()
        if warehouse:
            self._inventory[product_id]["warehouse"] = warehouse
        
        event = DomainEvent(
            event_type=EventType.INVENTORY_UPDATED,
            aggregate_id=product_id,
            data={"product_id": product_id, "quantity": quantity}
        )
        event_publisher.publish(event)
        return True
    
    def get_all_inventory(self) -> Dict[str, Dict[str, Any]]:
        return self._inventory.copy()
    
    def get_warehouse_inventory(self, warehouse: str) -> Dict[str, int]:
        return {
            product_id: data["quantity"]
            for product_id, data in self._inventory.items()
            if data.get("warehouse") == warehouse
        }
    
    def get_warehouses(self) -> Dict[str, Dict[str, Any]]:
        return {
            "WH-01": {"name": "Main Warehouse", "location": "New York, USA"},
            "WH-02": {"name": "Secondary Warehouse", "location": "Los Angeles, USA"}
        }
    
    def get_low_stock_items(self, threshold: int = 10) -> List[Dict[str, Any]]:
        return [
            {"product_id": pid, "stock": data["quantity"]}
            for pid, data in self._inventory.items()
            if data["quantity"] < threshold
        ]