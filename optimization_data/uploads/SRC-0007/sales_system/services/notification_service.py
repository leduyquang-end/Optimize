# services/notification_service.py
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import uuid
from core.events import EventType, DomainEvent, event_publisher

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        self._notifications: List[Dict[str, Any]] = []
        self._setup_event_listeners()
        logger.info("📧 Notification service initialized")
    
    def _setup_event_listeners(self):
        event_publisher.subscribe(EventType.ORDER_CREATED, self._handle_order_created)
        event_publisher.subscribe(EventType.ORDER_CONFIRMED, self._handle_order_confirmed)
        event_publisher.subscribe(EventType.ORDER_CANCELLED, self._handle_order_cancelled)
        event_publisher.subscribe(EventType.PAYMENT_PROCESSED, self._handle_payment_success)
        event_publisher.subscribe(EventType.PAYMENT_FAILED, self._handle_payment_failed)
    
    def _handle_order_created(self, event: DomainEvent):
        order_data = event.data.get("order", {})
        message = f"✅ Order created: {order_data.get('id')} - Total: ${order_data.get('total', 0)}"
        self.send_notification(order_data.get("customer_id", "customer"), message, "order_created")
    
    def _handle_order_confirmed(self, event: DomainEvent):
        order_id = event.data.get("order_id")
        message = f"📋 Order {order_id} confirmed"
        self.send_notification("customer", message, "order_confirmed")
    
    def _handle_order_cancelled(self, event: DomainEvent):
        order_id = event.data.get("order_id")
        reason = event.data.get("reason", "No reason provided")
        message = f"❌ Order {order_id} cancelled. Reason: {reason}"
        self.send_notification("customer", message, "order_cancelled")
    
    def _handle_payment_success(self, event: DomainEvent):
        order_id = event.data.get("order_id")
        message = f"💳 Payment successful for order {order_id}"
        self.send_notification("customer", message, "payment_success")
    
    def _handle_payment_failed(self, event: DomainEvent):
        order_id = event.data.get("order_id")
        message = f"❌ Payment failed for order {order_id}"
        self.send_notification("customer", message, "payment_failed")
    
    def send_notification(self, recipient: str, message: str, notification_type: str):
        notification = {
            "id": str(uuid.uuid4()),
            "recipient": recipient,
            "message": message,
            "type": notification_type,
            "timestamp": datetime.now().isoformat(),
            "status": "sent"
        }
        self._notifications.append(notification)
        logger.info(f"📧 Notification to {recipient}: {message}")
    
    def get_notification_history(self, recipient: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        history = self._notifications
        if recipient:
            history = [n for n in history if n["recipient"] == recipient]
        return history[-limit:]