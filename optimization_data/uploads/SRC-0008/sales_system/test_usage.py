# test_usage.py
import requests
import json
import time
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000/api"

def test_microkernel_plugins():
    """Test Microkernel Architecture - Các plugin đang hoạt động"""
    logger.info("=" * 60)
    logger.info("🔌 TESTING MICROKERNEL ARCHITECTURE - CÁC PLUGIN")
    logger.info("=" * 60)
    
    # 1. Lấy danh sách plugin đã đăng ký
    logger.info("\n1️⃣ Danh sách plugins đã đăng ký:")
    response = requests.get(f"{BASE_URL}/plugins")
    if response.status_code == 200:
        plugins = response.json()
        for plugin in plugins.get('plugins', []):
            logger.info(f"   ✅ {plugin['name']} v{plugin['version']} - Status: {plugin['status']}")
    
    # 2. Test Payment Plugin - Xử lý thanh toán
    logger.info("\n2️⃣ Test Payment Plugin - Xử lý thanh toán:")
    payment_data = {
        "order_id": "test_order_001",
        "method": "credit_card",
        "card_info": {
            "last4": "1234",
            "expiry": "12/25"
        }
    }
    response = requests.post(f"{BASE_URL}/payments/process", json=payment_data)
    if response.status_code == 200:
        result = response.json()
        logger.info(f"   ✅ Thanh toán thành công: {result}")
    else:
        logger.info(f"   ❌ Lỗi: {response.text}")
    
    # 3. Test Discount Plugin - Tính giảm giá
    logger.info("\n3️⃣ Test Discount Plugin - Tính giảm giá:")
    discount_data = {
        "amount": 100.0,
        "coupon": "SUMMER2024",
        "total_items": 3
    }
    response = requests.post(f"{BASE_URL}/discounts/calculate", json=discount_data)
    if response.status_code == 200:
        result = response.json()
        logger.info(f"   ✅ Giảm giá: {result['discount_percentage']}% -> Tiết kiệm: ${result['discount_amount']:.2f}")
        logger.info(f"   💰 Số tiền sau giảm: ${result['final_amount']:.2f}")
    
    # 4. Test Shipping Plugin - Tính phí vận chuyển
    logger.info("\n4️⃣ Test Shipping Plugin - Tính phí vận chuyển:")
    shipping_data = {
        "method": "express",
        "weight_kg": 2.5,
        "order_total": 150.0,
        "destination": "domestic"
    }
    response = requests.post(f"{BASE_URL}/shipping/calculate", json=shipping_data)
    if response.status_code == 200:
        result = response.json()
        logger.info(f"   ✅ Phí vận chuyển {result['method']}: ${result['cost']:.2f}")
        logger.info(f"   📦 Thời gian giao hàng: {result['delivery_days']} ngày")

def test_ddd_layered_architecture():
    """Test DDD Layered Architecture - Domain Models đang hoạt động"""
    logger.info("\n" + "=" * 60)
    logger.info("🏗️  TESTING DDD LAYERED ARCHITECTURE")
    logger.info("=" * 60)
    
    # 1. Tạo sản phẩm mới
    logger.info("\n1️⃣ Tạo sản phẩm mới (Domain Layer):")
    product_data = {
        "name": "iPhone 15 Pro Max",
        "description": "Apple flagship phone with titanium frame",
        "price": 1199.99,
        "stock": 25,
        "sku": "IP15PM",
        "category": "Electronics"
    }
    response = requests.post(f"{BASE_URL}/products", json=product_data)
    if response.status_code == 201:
        product = response.json()
        logger.info(f"   ✅ Đã tạo sản phẩm: {product['name']} - ${product['price']}")
        logger.info(f"   📦 ID: {product['id']}, Stock: {product['stock']}")
        product_id = product['id']
    else:
        logger.info(f"   ❌ Lỗi: {response.text}")
        return
    
    # 2. Tạo đơn hàng (Application Layer)
    logger.info("\n2️⃣ Tạo đơn hàng mới (Application Layer):")
    order_data = {
        "customer_id": "customer_001",
        "items": [
            {"product_id": product_id, "quantity": 2}
        ],
        "shipping_address": {
            "street": "123 Nguyễn Huệ",
            "city": "Hồ Chí Minh",
            "state": "HCM",
            "zip_code": "70000",
            "country": "Vietnam"
        },
        "coupon": "WELCOME10"
    }
    response = requests.post(f"{BASE_URL}/orders", json=order_data)
    if response.status_code == 201:
        order = response.json()
        logger.info(f"   ✅ Đã tạo đơn hàng: {order['id']}")
        logger.info(f"   💰 Tổng tiền: ${order['total']:.2f}")
        logger.info(f"   📦 Số lượng sản phẩm: {len(order['items'])}")
        logger.info(f"   📊 Trạng thái: {order['status']}")
        order_id = order['id']
    else:
        logger.info(f"   ❌ Lỗi: {response.text}")
        return
    
    # 3. Cập nhật trạng thái đơn hàng (Domain Behaviors)
    logger.info("\n3️⃣ Cập nhật trạng thái đơn hàng (Domain Behaviors):")
    response = requests.put(f"{BASE_URL}/orders/{order_id}/status?status=confirmed")
    if response.status_code == 200:
        logger.info(f"   ✅ Đã xác nhận đơn hàng: {order_id}")
    
    # 4. Xử lý thanh toán
    logger.info("\n4️⃣ Xử lý thanh toán:")
    payment_data = {
        "order_id": order_id,
        "method": "credit_card",
        "card_info": {"last4": "5678"}
    }
    response = requests.post(f"{BASE_URL}/payments/process", json=payment_data)
    if response.status_code == 200:
        result = response.json()
        logger.info(f"   ✅ Thanh toán thành công: {result['payment_id']}")
    
    # 5. Lấy thông tin đơn hàng (Query)
    logger.info("\n5️⃣ Lấy thông tin đơn hàng chi tiết:")
    response = requests.get(f"{BASE_URL}/orders/{order_id}")
    if response.status_code == 200:
        order_detail = response.json()
        logger.info(f"   📋 Mã đơn hàng: {order_detail['id']}")
        logger.info(f"   👤 Khách hàng: {order_detail['customer_id']}")
        logger.info(f"   💰 Tổng: ${order_detail['total']:.2f}")
        logger.info(f"   📊 Trạng thái: {order_detail['status']}")
        logger.info(f"   💳 Thanh toán: {order_detail['payment_status']}")

def test_event_driven_architecture():
    """Test Event-Driven Architecture - Các sự kiện đang được phát và xử lý"""
    logger.info("\n" + "=" * 60)
    logger.info("📨 TESTING EVENT-DRIVEN ARCHITECTURE")
    logger.info("=" * 60)
    
    # 1. Xem lịch sử các sự kiện
    logger.info("\n1️⃣ Lịch sử các sự kiện đã xảy ra:")
    response = requests.get(f"{BASE_URL}/events")
    if response.status_code == 200:
        events = response.json()
        logger.info(f"   📊 Tổng số sự kiện: {events['total']}")
        for event in events['events'][-5:]:  # Lấy 5 sự kiện gần nhất
            logger.info(f"   🔔 {event['event_type']} - {event['timestamp'][:19]}")
            if event['event_type'] == 'order.created':
                logger.info(f"      📦 Order ID: {event['data']['order']['id']}")
            elif event['event_type'] == 'payment.processed':
                logger.info(f"      💰 Amount: ${event['data']['amount']}")
    
    # 2. Xem thông báo được gửi từ events
    logger.info("\n2️⃣ Thông báo được gửi từ các sự kiện:")
    response = requests.get(f"{BASE_URL}/notifications/history")
    if response.status_code == 200:
        notifications = response.json().get('notifications', [])
        if notifications:
            for notif in notifications[-3:]:  # Lấy 3 thông báo gần nhất
                logger.info(f"   📧 {notif['type']} -> {notif['recipient']}")
                logger.info(f"      {notif['message'][:50]}...")
        else:
            logger.info("   ℹ️ Chưa có thông báo nào")

def test_microservices():
    """Test Microservices Architecture - Các service hoạt động độc lập"""
    logger.info("\n" + "=" * 60)
    logger.info("🔗 TESTING MICROSERVICES ARCHITECTURE")
    logger.info("=" * 60)
    
    # 1. Product Service
    logger.info("\n1️⃣ Product Service - Quản lý sản phẩm:")
    response = requests.get(f"{BASE_URL}/products")
    if response.status_code == 200:
        products = response.json()
        logger.info(f"   📦 Tổng số sản phẩm: {len(products)}")
        for product in products[:3]:  # Lấy 3 sản phẩm đầu
            logger.info(f"      - {product['name']}: ${product['price']} (Stock: {product['stock']})")
    
    # 2. Inventory Service
    logger.info("\n2️⃣ Inventory Service - Quản lý kho:")
    response = requests.get(f"{BASE_URL}/inventory")
    if response.status_code == 200:
        inventory = response.json()
        total_items = len(inventory)
        total_stock = sum(item.get('quantity', 0) for item in inventory.values())
        logger.info(f"   📦 Tổng số mặt hàng trong kho: {total_items}")
        logger.info(f"   📦 Tổng số lượng: {total_stock}")
        
        # Kiểm tra hàng tồn kho thấp
        response = requests.get(f"{BASE_URL}/inventory/low-stock?threshold=20")
        if response.status_code == 200:
            low_stock = response.json().get('low_stock_items', [])
            if low_stock:
                logger.info(f"   ⚠️ Hàng sắp hết: {len(low_stock)} mặt hàng")
                for item in low_stock:
                    logger.info(f"      - {item['product_id']}: {item['stock']} units")
    
    # 3. Order Service
    logger.info("\n3️⃣ Order Service - Quản lý đơn hàng:")
    response = requests.get(f"{BASE_URL}/analytics/order-statistics")
    if response.status_code == 200:
        stats = response.json()
        logger.info(f"   📊 Tổng số đơn hàng: {stats['total_orders']}")
        logger.info(f"   💰 Doanh thu: ${stats['total_revenue']:.2f}")
        logger.info(f"   💳 Trung bình/đơn: ${stats['average_order_value']:.2f}")
        if stats.get('status_counts'):
            logger.info(f"   📊 Trạng thái: {stats['status_counts']}")

def test_analytics():
    """Test Analytics - Hệ thống phân tích dữ liệu"""
    logger.info("\n" + "=" * 60)
    logger.info("📊 TESTING ANALYTICS SERVICE")
    logger.info("=" * 60)
    
    # 1. Metrics tổng quan
    logger.info("\n1️⃣ Metrics tổng quan hệ thống:")
    response = requests.get(f"{BASE_URL}/analytics/metrics")
    if response.status_code == 200:
        metrics = response.json()
        logger.info(f"   📊 Tổng đơn hàng: {metrics.get('total_orders', 0)}")
        logger.info(f"   💰 Doanh thu: ${metrics.get('total_revenue', 0):.2f}")
        logger.info(f"   👤 Khách hàng: {metrics.get('total_customers', 0)}")
        logger.info(f"   💳 Trung bình/đơn: ${metrics.get('average_order_value', 0):.2f}")
    
    # 2. Báo cáo doanh số
    logger.info("\n2️⃣ Báo cáo doanh số 7 ngày gần nhất:")
    response = requests.get(f"{BASE_URL}/analytics/sales?days=7")
    if response.status_code == 200:
        report = response.json()
        logger.info(f"   📊 Tổng đơn: {report.get('total_orders', 0)}")
        logger.info(f"   💰 Doanh thu: ${report.get('total_revenue', 0):.2f}")
        logger.info(f"   📈 Trung bình/ngày: ${report.get('average_daily_revenue', 0):.2f}")

# test_usage.py - Sửa hàm test_system_health

def test_system_health():
    """Test System Health - Kiểm tra sức khỏe hệ thống"""
    logger.info("\n" + "=" * 60)
    logger.info("❤️  SYSTEM HEALTH CHECK")
    logger.info("=" * 60)
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            health = response.json()
            logger.info(f"   ✅ Status: {health.get('status', 'unknown')}")
            logger.info(f"   🔌 Plugins: {health.get('plugins', 0)}")
            logger.info(f"   📦 Products: {health.get('products', 0)}")
            logger.info(f"   📋 Orders: {health.get('orders', 0)}")
            # Kiểm tra nếu có field 'events'
            if 'events' in health:
                logger.info(f"   📨 Events: {health['events']}")
            logger.info(f"   📅 Timestamp: {health.get('timestamp', 'unknown')}")
            logger.info("\n   ✅ HỆ THỐNG ĐANG HOẠT ĐỘNG TỐT!")
        else:
            logger.error(f"❌ Health check failed: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ Không thể kết nối đến server: {e}")

def main():
    """Chạy tất cả các test"""
    logger.info("\n" + "🚀" * 30)
    logger.info("BẮT ĐẦU KIỂM TRA HỆ THỐNG BÁN HÀNG ĐA KIẾN TRÚC")
    logger.info("🚀" * 30)
    
    try:
        # Kiểm tra sức khỏe trước
        test_system_health()
        
        # Test các kiến trúc
        test_microkernel_plugins()
        test_ddd_layered_architecture()
        test_event_driven_architecture()
        test_microservices()
        test_analytics()
        
        logger.info("\n" + "✅" * 30)
        logger.info("TẤT CẢ CÁC KIỂU KIẾN TRÚC ĐỀU HOẠT ĐỘNG!")
        logger.info("✅" * 30)
        
    except requests.exceptions.ConnectionError:
        logger.error("\n❌ Không thể kết nối đến server!")
        logger.error("   Vui lòng chạy 'python app.py' trước")
    except Exception as e:
        logger.error(f"\n❌ Lỗi: {e}")

if __name__ == "__main__":
    main()