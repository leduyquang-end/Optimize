# services/analytics_service.py
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime, timedelta
import logging
from core.events import EventType, DomainEvent, event_publisher

logger = logging.getLogger(__name__)

class AnalyticsService:
    def __init__(self):
        self._metrics = {
            "total_orders": 0,
            "total_revenue": 0.0,
            "customers": set(),
            "daily_orders": defaultdict(int),
            "daily_revenue": defaultdict(float)
        }
        self._start_time = datetime.now()
        self._setup_event_listeners()
        logger.info("📊 Analytics service initialized")
    
    def _setup_event_listeners(self):
        event_publisher.subscribe(EventType.ORDER_CREATED, self._track_order)
        event_publisher.subscribe(EventType.PAYMENT_PROCESSED, self._track_payment)
    
    def _track_order(self, event: DomainEvent):
        order_data = event.data.get("order", {})
        customer_id = order_data.get("customer_id")
        
        self._metrics["total_orders"] += 1
        if customer_id:
            self._metrics["customers"].add(customer_id)
        
        today = datetime.now().strftime("%Y-%m-%d")
        self._metrics["daily_orders"][today] += 1
    
    def _track_payment(self, event: DomainEvent):
        amount = event.data.get("amount", 0)
        self._metrics["total_revenue"] += amount
        
        today = datetime.now().strftime("%Y-%m-%d")
        self._metrics["daily_revenue"][today] += amount
    
    def get_metrics(self) -> Dict[str, Any]:
        total_orders = self._metrics["total_orders"]
        total_revenue = self._metrics["total_revenue"]
        
        return {
            "total_orders": total_orders,
            "total_revenue": round(total_revenue, 2),
            "total_customers": len(self._metrics["customers"]),
            "average_order_value": round(total_revenue / total_orders if total_orders > 0 else 0, 2),
            "daily_orders": dict(self._metrics["daily_orders"]),
            "daily_revenue": dict(self._metrics["daily_revenue"]),
            "uptime": str(datetime.now() - self._start_time)
        }
    
    def get_sales_report(self, days: int = 7) -> Dict[str, Any]:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        daily_orders = {date: count for date, count in self._metrics["daily_orders"].items() if date >= cutoff}
        daily_revenue = {date: amount for date, amount in self._metrics["daily_revenue"].items() if date >= cutoff}
        
        total_orders = sum(daily_orders.values())
        total_revenue = sum(daily_revenue.values())
        
        return {
            "period": f"Last {days} days",
            "total_orders": total_orders,
            "total_revenue": round(total_revenue, 2),
            "daily_orders": daily_orders,
            "daily_revenue": daily_revenue,
            "average_daily_orders": round(total_orders / days, 2) if days > 0 else 0,
            "average_daily_revenue": round(total_revenue / days, 2) if days > 0 else 0
        }
    
    def get_customer_analytics(self) -> Dict[str, Any]:
        return {
            "total_customers": len(self._metrics["customers"]),
            "total_orders": self._metrics["total_orders"],
            "total_revenue": round(self._metrics["total_revenue"], 2)
        }
    
    def get_conversion_funnel(self) -> Dict[str, Any]:
        orders_created = len([e for e in event_publisher.get_events() if e.event_type == EventType.ORDER_CREATED])
        payments_success = len([e for e in event_publisher.get_events() if e.event_type == EventType.PAYMENT_PROCESSED])
        
        return {
            "orders_created": orders_created,
            "payments_success": payments_success,
            "conversion_rate": round((payments_success / orders_created * 100) if orders_created > 0 else 0, 2)
        }
    
    def get_time_series_data(self, metric: str = "orders", days: int = 30) -> List[Dict[str, Any]]:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        if metric == "orders":
            data = self._metrics["daily_orders"]
        elif metric == "revenue":
            data = self._metrics["daily_revenue"]
        else:
            return []
        
        filtered = {date: value for date, value in data.items() if date >= cutoff}
        return [{"date": date, "value": value} for date, value in sorted(filtered.items())]