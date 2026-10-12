# core/events.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional
from enum import Enum
import uuid
import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class EventType(Enum):
    ORDER_CREATED = "order.created"
    ORDER_CONFIRMED = "order.confirmed"
    ORDER_PROCESSED = "order.processed"
    ORDER_SHIPPED = "order.shipped"
    ORDER_DELIVERED = "order.delivered"
    ORDER_CANCELLED = "order.cancelled"

    PAYMENT_PROCESSED = "payment.processed"
    PAYMENT_FAILED = "payment.failed"

    INVENTORY_UPDATED = "inventory.updated"
    INVENTORY_LOW = "inventory.low"
    STOCK_OUT = "stock.out"

    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    
    NOTIFICATION_SENT = "notification.sent"

@dataclass
class DomainEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = None
    aggregate_id: str = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    user_id: Optional[str] = None

class EventPublisher:
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._event_store: List[DomainEvent] = []
        self._async_subscribers: Dict[EventType, List[Callable]] = defaultdict(list)
        
    def subscribe(self, event_type: EventType, callback: Callable, async_mode: bool = False):
        if async_mode:
            self._async_subscribers[event_type].append(callback)
        else:
            self._subscribers[event_type].append(callback)
    
    def publish(self, event: DomainEvent):
        """Sync publish"""
        self._event_store.append(event)
        logger.info(f"Publishing event: {event.event_type.value} - {event.event_id}")
        
        # Sync subscribers
        if event.event_type in self._subscribers:
            for callback in self._subscribers[event.event_type]:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error in subscriber: {e}")
        
        # Async subscribers
        if event.event_type in self._async_subscribers:
            for callback in self._async_subscribers[event.event_type]:
                try:
                    asyncio.create_task(self._run_async_callback(callback, event))
                except Exception as e:
                    logger.error(f"Error creating async task: {e}")
    
    async def _run_async_callback(self, callback, event):
        try:
            await callback(event)
        except Exception as e:
            logger.error(f"Error in async subscriber: {e}")
    
    def get_events(self, event_type: Optional[EventType] = None) -> List[DomainEvent]:
        if event_type:
            return [e for e in self._event_store if e.event_type == event_type]
        return self._event_store.copy()

# Global event publisher
event_publisher = EventPublisher()