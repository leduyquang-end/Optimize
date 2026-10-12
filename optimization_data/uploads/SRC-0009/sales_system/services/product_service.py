# services/product_service.py
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import logging
from core.domain import Product, Money
from core.events import EventType, DomainEvent, event_publisher

logger = logging.getLogger(__name__)

class ProductService:
    def __init__(self):
        self._products: Dict[str, Product] = {}
        self._categories: Dict[str, List[str]] = {}
        self._initialize_sample_data()
    
    def _initialize_sample_data(self):
        sample_products = [
            Product(
                id=str(uuid.uuid4()),
                name="MacBook Pro 16",
                description="Apple MacBook Pro with M2 chip",
                price=Money(2499.99),
                stock=15,
                sku="MBP16M2",
                category="Electronics"
            ),
            Product(
                id=str(uuid.uuid4()),
                name="Samsung Galaxy S24",
                description="Latest Samsung flagship phone",
                price=Money(1199.99),
                stock=30,
                sku="SGS24",
                category="Electronics"
            ),
            Product(
                id=str(uuid.uuid4()),
                name="Sony WH-1000XM5",
                description="Premium noise-canceling headphones",
                price=Money(399.99),
                stock=25,
                sku="SONYXM5",
                category="Audio"
            ),
            Product(
                id=str(uuid.uuid4()),
                name="Dell XPS 15",
                description="High-end Windows laptop",
                price=Money(1899.99),
                stock=12,
                sku="DELLXPS15",
                category="Electronics"
            ),
            Product(
                id=str(uuid.uuid4()),
                name="Logitech MX Master 3S",
                description="Advanced wireless mouse",
                price=Money(99.99),
                stock=40,
                sku="LOGIMX3S",
                category="Accessories"
            )
        ]
        
        for product in sample_products:
            self._products[product.id] = product
            if product.category not in self._categories:
                self._categories[product.category] = []
            self._categories[product.category].append(product.id)
        
        logger.info(f"📦 Initialized {len(self._products)} products")
    
    def get_all_products(self) -> List[Product]:
        return list(self._products.values())
    
    def get_product(self, product_id: str) -> Optional[Product]:
        return self._products.get(product_id)
    
    def get_products_by_category(self, category: str) -> List[Product]:
        product_ids = self._categories.get(category, [])
        return [self._products[pid] for pid in product_ids if pid in self._products]
    
    def create_product(self, name: str, description: str, price: float, 
                      stock: int, sku: str, category: str) -> Product:
        product_id = str(uuid.uuid4())
        product = Product(
            id=product_id,
            name=name,
            description=description,
            price=Money(price),
            stock=stock,
            sku=sku,
            category=category
        )
        
        self._products[product_id] = product
        
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(product_id)
        
        event = DomainEvent(
            event_type=EventType.PRODUCT_CREATED,
            aggregate_id=product_id,
            data={"product": {"id": product_id, "name": name, "price": price}}
        )
        event_publisher.publish(event)
        
        return product
    
    def update_product_stock(self, product_id: str, quantity: int) -> bool:
        product = self._products.get(product_id)
        if not product:
            return False
        
        product.stock = quantity
        return True
    
    def reduce_stock(self, product_id: str, quantity: int) -> bool:
        product = self._products.get(product_id)
        if not product:
            return False
        
        if product.stock < quantity:
            raise ValueError(f"Insufficient stock")
        
        product.stock -= quantity
        return True
    
    def increase_stock(self, product_id: str, quantity: int) -> bool:
        product = self._products.get(product_id)
        if not product:
            return False
        
        product.stock += quantity
        return True
    
    def search_products(self, query: str) -> List[Product]:
        query = query.lower()
        return [
            p for p in self._products.values()
            if query in p.name.lower() or query in p.description.lower()
        ]
    
    def get_categories(self) -> List[str]:
        return list(self._categories.keys())
    
    def get_total_products(self) -> int:
        return len(self._products)