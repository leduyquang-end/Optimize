# core/domain.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import uuid

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class PaymentStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

@dataclass
class Address:
    street: str
    city: str
    state: str
    zip_code: str
    country: str

@dataclass
class Money:
    amount: float
    currency: str = "USD"
    
    def add(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")
        return Money(self.amount + other.amount, self.currency)
    
    def subtract(self, other: 'Money') -> 'Money':
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")
        return Money(self.amount - other.amount, self.currency)

@dataclass
class Product:
    id: str
    name: str
    description: str
    price: Money
    stock: int
    sku: str
    category: str
    created_at: datetime = field(default_factory=datetime.now)
    
    def reduce_stock(self, quantity: int):
        if self.stock < quantity:
            raise ValueError(f"Insufficient stock. Available: {self.stock}")
        self.stock -= quantity
    
    def increase_stock(self, quantity: int):
        self.stock += quantity

@dataclass
class OrderItem:
    product_id: str
    product_name: str
    quantity: int
    price: Money
    
    @property
    def subtotal(self) -> Money:
        return Money(self.price.amount * self.quantity, self.price.currency)

@dataclass
class Order:
    id: str
    customer_id: str
    items: List[OrderItem]
    shipping_address: Address
    total: Money
    status: OrderStatus
    payment_status: PaymentStatus
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def confirm(self):
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"Cannot confirm order with status {self.status}")
        self.status = OrderStatus.CONFIRMED
        self.updated_at = datetime.now()
    
    def process(self):
        if self.status != OrderStatus.CONFIRMED:
            raise ValueError(f"Cannot process order with status {self.status}")
        self.status = OrderStatus.PROCESSING
        self.updated_at = datetime.now()
    
    def ship(self):
        if self.status != OrderStatus.PROCESSING:
            raise ValueError(f"Cannot ship order with status {self.status}")
        self.status = OrderStatus.SHIPPED
        self.updated_at = datetime.now()
    
    def deliver(self):
        if self.status != OrderStatus.SHIPPED:
            raise ValueError(f"Cannot deliver order with status {self.status}")
        self.status = OrderStatus.DELIVERED
        self.updated_at = datetime.now()
    
    def cancel(self):
        if self.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED]:
            raise ValueError(f"Cannot cancel order with status {self.status}")
        self.status = OrderStatus.CANCELLED
        self.updated_at = datetime.now()