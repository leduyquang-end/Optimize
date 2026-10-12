# services/order_service.py
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import logging
from core.domain import Order, OrderItem, OrderStatus, PaymentStatus, Money, Address
from core.events import EventType, DomainEvent, event_publisher
from services.product_service import ProductService

logger = logging.getLogger(__name__)

class OrderService:
    def __init__(self, product_service: ProductService):
        self._product_service = product_service
        self._orders: Dict[str, Order] = {}
        self._customer_orders: Dict[str, List[str]] = {}
        self._order_number_counter = 1000
    
    def _generate_order_number(self) -> str:
        self._order_number_counter += 1
        return f"ORD-{self._order_number_counter:06d}"
    
    def _calculate_shipping(self, items: List[OrderItem], total: Money) -> float:
        try:
            from core.kernel import sales_kernel
            weight_kg = len(items) * 0.5
            result = sales_kernel.execute_plugin(
                "shipping.plugin",
                method="standard",
                weight_kg=weight_kg,
                order_total=total.amount,
                destination="domestic"
            )
            return result.get("cost", 5.99)
        except:
            return 5.99
    
    def create_order(self, customer_id: str, items: List[Dict[str, Any]], 
                    shipping_address: Dict[str, str]) -> Order:
        if not customer_id or not items:
            raise ValueError("Customer ID and items are required")
        
        # Create order items
        order_items = []
        total = Money(0)
        
        for item_data in items:
            product = self._product_service.get_product(item_data["product_id"])
            if not product:
                raise ValueError(f"Product not found: {item_data['product_id']}")
            
            if product.stock < item_data["quantity"]:
                raise ValueError(f"Insufficient stock for {product.name}")
            
            order_item = OrderItem(
                product_id=product.id,
                product_name=product.name,
                quantity=item_data["quantity"],
                price=product.price
            )
            
            order_items.append(order_item)
            total = total.add(order_item.subtotal)
        
        # Apply discount if using coupon plugin
        try:
            from core.kernel import sales_kernel
            discount_result = sales_kernel.execute_plugin(
                "discount.plugin",
                amount=total.amount,
                total_items=len(order_items)
            )
            if discount_result.get("discount_amount", 0) > 0:
                total = Money(discount_result["final_amount"])
        except:
            pass
        
        # Calculate shipping
        shipping_cost = self._calculate_shipping(order_items, total)
        total = Money(total.amount + shipping_cost)
        
        # Create order
        order_id = str(uuid.uuid4())
        address = Address(**shipping_address)
        
        order = Order(
            id=order_id,
            customer_id=customer_id,
            items=order_items,
            shipping_address=address,
            total=total,
            status=OrderStatus.PENDING,
            payment_status=PaymentStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self._orders[order_id] = order
        
        if customer_id not in self._customer_orders:
            self._customer_orders[customer_id] = []
        self._customer_orders[customer_id].append(order_id)
        
        # Reduce stock
        for item in order_items:
            self._product_service.reduce_stock(item.product_id, item.quantity)
        
        # Publish event
        event = DomainEvent(
            event_type=EventType.ORDER_CREATED,
            aggregate_id=order_id,
            data={
                "order": {
                    "id": order_id,
                    "customer_id": customer_id,
                    "total": total.amount,
                    "items": [
                        {
                            "product_id": item.product_id,
                            "product_name": item.product_name,
                            "quantity": item.quantity,
                            "price": item.price.amount
                        }
                        for item in order_items
                    ]
                }
            }
        )
        event_publisher.publish(event)
        
        logger.info(f"📋 Order created: {order_id}")
        return order
    
    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)
    
    def get_customer_orders(self, customer_id: str) -> List[Order]:
        order_ids = self._customer_orders.get(customer_id, [])
        return [self._orders[oid] for oid in order_ids if oid in self._orders]
    
    def get_all_orders(self) -> List[Order]:
        return list(self._orders.values())
    
    def update_order_status(self, order_id: str, status: OrderStatus) -> bool:
        order = self._orders.get(order_id)
        if not order:
            return False
        
        try:
            if status == OrderStatus.CONFIRMED:
                order.confirm()
            elif status == OrderStatus.PROCESSING:
                order.process()
            elif status == OrderStatus.SHIPPED:
                order.ship()
            elif status == OrderStatus.DELIVERED:
                order.deliver()
            elif status == OrderStatus.CANCELLED:
                order.cancel()
            
            event = DomainEvent(
                event_type=EventType.ORDER_CONFIRMED,
                aggregate_id=order_id,
                data={"order_id": order_id, "status": status.value}
            )
            event_publisher.publish(event)
            return True
        except ValueError as e:
            logger.error(f"Invalid status transition: {e}")
            return False
    
    def update_payment_status(self, order_id: str, status: PaymentStatus) -> bool:
        order = self._orders.get(order_id)
        if not order:
            return False
        
        order.payment_status = status
        
        event_type = EventType.PAYMENT_PROCESSED if status == PaymentStatus.SUCCESS else EventType.PAYMENT_FAILED
        event = DomainEvent(
            event_type=event_type,
            aggregate_id=order_id,
            data={"order_id": order_id, "status": status.value}
        )
        event_publisher.publish(event)
        return True
    
    def cancel_order(self, order_id: str, reason: str = None) -> bool:
        order = self._orders.get(order_id)
        if not order:
            return False
        
        try:
            order.cancel()
            
            # Restore stock
            for item in order.items:
                self._product_service.increase_stock(item.product_id, item.quantity)
            
            event = DomainEvent(
                event_type=EventType.ORDER_CANCELLED,
                aggregate_id=order_id,
                data={"order_id": order_id, "reason": reason}
            )
            event_publisher.publish(event)
            return True
        except ValueError as e:
            logger.error(f"Cannot cancel order: {e}")
            return False
    
    def get_order_statistics(self) -> Dict[str, Any]:
        total_orders = len(self._orders)
        if total_orders == 0:
            return {
                "total_orders": 0,
                "total_revenue": 0,
                "average_order_value": 0,
                "status_counts": {},
                "total_customers": 0
            }
        
        total_revenue = sum(order.total.amount for order in self._orders.values())
        unique_customers = set(order.customer_id for order in self._orders.values())
        
        status_counts = {}
        for order in self._orders.values():
            status_counts[order.status.value] = status_counts.get(order.status.value, 0) + 1
        
        return {
            "total_orders": total_orders,
            "total_revenue": round(total_revenue, 2),
            "average_order_value": round(total_revenue / total_orders, 2),
            "status_counts": status_counts,
            "total_customers": len(unique_customers)
        }