# client/streamlit_app.py
import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime
import plotly.express as px

BASE_URL = "http://localhost:8000/api"

st.set_page_config(
    page_title="Sales System",
    page_icon="🛒",
    layout="wide"
)

# Session state
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'products' not in st.session_state:
    st.session_state.products = []

# Sidebar
st.sidebar.title("🛒 Sales System")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "📋 Menu",
    ["📦 Products", "🛒 Cart", "📋 Orders", "📦 Inventory", "📊 Analytics", "⚙️ System"]
)

# Main content
st.title("🛒 Hệ Thống Bán Hàng Đa Kiến Trúc")

# Load products
def load_products():
    try:
        response = requests.get(f"{BASE_URL}/products", timeout=3)
        if response.status_code == 200:
            st.session_state.products = response.json()
            return st.session_state.products
    except:
        st.error("❌ Không thể kết nối đến server")
    return []

# --- Products Tab ---
if menu == "📦 Products":
    st.header("📦 Quản lý Sản Phẩm")
    
    # Search
    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("🔍 Tìm kiếm sản phẩm", placeholder="Nhập tên sản phẩm...")
    with col2:
        if st.button("🔄 Refresh"):
            load_products()
    
    products = load_products()
    
    if search:
        products = [p for p in products if search.lower() in p['name'].lower()]
    
    # Display products
    if products:
        df = pd.DataFrame(products)
        df['price'] = df['price'].apply(lambda x: f"${x:.2f}")
        
        # Add to cart button
        for idx, row in df.iterrows():
            cols = st.columns([2, 1, 1, 1, 1, 0.5])
            cols[0].write(f"**{row['name']}**")
            cols[1].write(f"${row['price']}")
            cols[2].write(f"Stock: {row['stock']}")
            cols[3].write(row['category'])
            
            if cols[4].button(f"🛒 Add", key=f"add_{row['id']}"):
                if row['stock'] > 0:
                    st.session_state.cart.append({
                        'product_id': row['id'],
                        'name': row['name'],
                        'price': float(row['price'].replace('$', '')),
                        'quantity': 1
                    })
                    st.success(f"✅ Added {row['name']} to cart")
                    st.rerun()
                else:
                    st.warning("⚠️ Out of stock")
        
        st.markdown("---")
        st.write(f"📊 Total products: {len(products)}")
    else:
        st.info("📦 No products found")
    
    # Add product
    with st.expander("➕ Add New Product"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name")
            price = st.number_input("Price", min_value=0.0, step=0.01)
            stock = st.number_input("Stock", min_value=0, step=1)
        with col2:
            description = st.text_area("Description")
            sku = st.text_input("SKU")
            category = st.text_input("Category")
        
        if st.button("✅ Create Product"):
            product_data = {
                "name": name,
                "description": description,
                "price": price,
                "stock": stock,
                "sku": sku,
                "category": category
            }
            try:
                response = requests.post(f"{BASE_URL}/products", json=product_data)
                if response.status_code == 201:
                    st.success("✅ Product created!")
                    load_products()
                    st.rerun()
                else:
                    st.error(f"❌ Failed: {response.text}")
            except Exception as e:
                st.error(f"❌ Error: {e}")

# --- Cart Tab ---
elif menu == "🛒 Cart":
    st.header("🛒 Giỏ Hàng")
    
    if not st.session_state.cart:
        st.info("🛒 Giỏ hàng trống")
    else:
        # Display cart
        cart_data = []
        total = 0
        for item in st.session_state.cart:
            subtotal = item['price'] * item['quantity']
            total += subtotal
            cart_data.append({
                'Product': item['name'],
                'Price': f"${item['price']:.2f}",
                'Quantity': item['quantity'],
                'Subtotal': f"${subtotal:.2f}"
            })
        
        df = pd.DataFrame(cart_data)
        st.dataframe(df, use_container_width=True)
        
        st.markdown(f"### 💰 **Tổng: ${total:.2f}**")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🧹 Clear Cart"):
                st.session_state.cart = []
                st.rerun()
        
        with col2:
            customer_id = st.text_input("Customer ID", value="customer_001")
        
        with col3:
            if st.button("💳 Checkout"):
                if st.session_state.cart:
                    order_data = {
                        'customer_id': customer_id,
                        'items': [
                            {
                                'product_id': item['product_id'],
                                'quantity': item['quantity']
                            }
                            for item in st.session_state.cart
                        ],
                        'shipping_address': {
                            'street': '123 Main St',
                            'city': 'New York',
                            'state': 'NY',
                            'zip_code': '10001',
                            'country': 'USA'
                        }
                    }
                    
                    try:
                        response = requests.post(f"{BASE_URL}/orders", json=order_data)
                        if response.status_code == 201:
                            order = response.json()
                            st.success(f"✅ Order created! ID: {order['id'][:8]}")
                            st.session_state.cart = []
                            st.rerun()
                        else:
                            st.error(f"❌ Failed: {response.text}")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

# --- Orders Tab ---
elif menu == "📋 Orders":
    st.header("📋 Quản lý Đơn Hàng")
    
    customer_id = st.text_input("Customer ID", value="customer_001")
    
    if st.button("📋 Load Orders"):
        try:
            response = requests.get(f"{BASE_URL}/orders/customer/{customer_id}")
            if response.status_code == 200:
                orders = response.json()
                
                if orders:
                    df = pd.DataFrame(orders)
                    st.dataframe(df, use_container_width=True)
                    
                    # Order details
                    st.subheader("📄 Order Details")
                    selected_order = st.selectbox(
                        "Select order",
                        options=[o['id'] for o in orders]
                    )
                    
                    if selected_order:
                        response = requests.get(f"{BASE_URL}/orders/{selected_order}")
                        if response.status_code == 200:
                            order_detail = response.json()
                            st.json(order_detail)
                else:
                    st.info("📋 No orders found")
            else:
                st.error(f"❌ Failed: {response.status_code}")
        except Exception as e:
            st.error(f"❌ Error: {e}")

# --- Inventory Tab ---
elif menu == "📦 Inventory":
    st.header("📦 Quản lý Kho Hàng")
    
    if st.button("🔄 Refresh"):
        st.rerun()
    
    try:
        response = requests.get(f"{BASE_URL}/inventory")
        if response.status_code == 200:
            inventory = response.json()
            
            if inventory:
                # Convert to dataframe
                data = []
                for product_id, info in inventory.items():
                    if isinstance(info, dict):
                        data.append({
                            'Product ID': product_id,
                            'Quantity': info.get('quantity', 0),
                            'Warehouse': info.get('warehouse', 'N/A'),
                            'Last Updated': info.get('last_updated', '')
                        })
                
                if data:
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True)
                    
                    # Stats
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Items", len(df))
                    with col2:
                        st.metric("Total Quantity", df['Quantity'].sum())
                    with col3:
                        low_stock = len(df[df['Quantity'] < 10])
                        st.metric("Low Stock Items", low_stock)
                    
                    # Show low stock
                    if low_stock > 0:
                        st.warning(f"⚠️ {low_stock} items have low stock (< 10)")
                        st.dataframe(df[df['Quantity'] < 10])
    
    except Exception as e:
        st.error(f"❌ Error: {e}")

# --- Analytics Tab ---
elif menu == "📊 Analytics":
    st.header("📊 Phân Tích & Thống Kê")
    
    tab1, tab2, tab3 = st.tabs(["📊 Metrics", "📈 Sales Report", "🎯 Funnel"])
    
    with tab1:
        try:
            response = requests.get(f"{BASE_URL}/analytics/metrics")
            if response.status_code == 200:
                metrics = response.json()
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📦 Orders", metrics.get('total_orders', 0))
                with col2:
                    st.metric("💰 Revenue", f"${metrics.get('total_revenue', 0):.2f}")
                with col3:
                    st.metric("👤 Customers", metrics.get('total_customers', 0))
                with col4:
                    st.metric("💳 Avg Order", f"${metrics.get('average_order_value', 0):.2f}")
                
                # Daily orders chart
                daily_orders = metrics.get('daily_orders', {})
                if daily_orders:
                    df = pd.DataFrame([
                        {'Date': k, 'Orders': v}
                        for k, v in daily_orders.items()
                    ])
                    fig = px.bar(df, x='Date', y='Orders', title='Daily Orders')
                    st.plotly_chart(fig, use_container_width=True)
        
        except Exception as e:
            st.error(f"❌ Error: {e}")
    
    with tab2:
        days = st.slider("Days", 1, 30, 7)
        try:
            response = requests.get(f"{BASE_URL}/analytics/sales?days={days}")
            if response.status_code == 200:
                report = response.json()
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Orders", report.get('total_orders', 0))
                with col2:
                    st.metric("Total Revenue", f"${report.get('total_revenue', 0):.2f}")
                with col3:
                    st.metric("Daily Avg", f"${report.get('average_daily_revenue', 0):.2f}")
                
                # Daily chart
                daily_orders = report.get('daily_orders', {})
                daily_revenue = report.get('daily_revenue', {})
                
                if daily_orders:
                    df = pd.DataFrame([
                        {'Date': k, 'Orders': v, 'Revenue': daily_revenue.get(k, 0)}
                        for k, v in daily_orders.items()
                    ])
                    fig = px.line(df, x='Date', y=['Orders', 'Revenue'], title='Daily Performance')
                    st.plotly_chart(fig, use_container_width=True)
        
        except Exception as e:
            st.error(f"❌ Error: {e}")
    
    with tab3:
        try:
            response = requests.get(f"{BASE_URL}/analytics/funnel")
            if response.status_code == 200:
                funnel = response.json()
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📝 Orders Created", funnel.get('orders_created', 0))
                with col2:
                    st.metric("💳 Payments Success", funnel.get('payments_success', 0))
                with col3:
                    st.metric("🎯 Conversion Rate", f"{funnel.get('conversion_rate', 0)}%")
                
                # Funnel chart
                steps = ['Orders Created', 'Payments Success']
                values = [funnel.get('orders_created', 0), funnel.get('payments_success', 0)]
                df = pd.DataFrame({'Step': steps, 'Count': values})
                fig = px.bar(df, x='Step', y='Count', title='Conversion Funnel')
                st.plotly_chart(fig, use_container_width=True)
        
        except Exception as e:
            st.error(f"❌ Error: {e}")

# --- System Tab ---
elif menu == "⚙️ System":
    st.header("⚙️ Quản lý Hệ Thống")
    
    tab1, tab2, tab3 = st.tabs(["ℹ️ Info", "🔌 Plugins", "📨 Events"])
    
    with tab1:
        try:
            response = requests.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                health = response.json()
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Status", health.get('status', 'N/A'))
                with col2:
                    st.metric("Version", health.get('version', 'N/A'))
                with col3:
                    st.metric("Plugins", health.get('plugins', 0))
                with col4:
                    st.metric("Events", health.get('events', 0))
                
                st.json(health)
        except Exception as e:
            st.error(f"❌ Error: {e}")
    
    with tab2:
        try:
            response = requests.get(f"{BASE_URL}/plugins")
            if response.status_code == 200:
                plugins = response.json().get('plugins', [])
                
                for plugin in plugins:
                    with st.expander(f"🔌 {plugin['name']}"):
                        st.write(f"**ID:** {plugin['id']}")
                        st.write(f"**Version:** {plugin['version']}")
                        st.write(f"**Status:** {plugin['status']}")
        except Exception as e:
            st.error(f"❌ Error: {e}")
    
    with tab3:
        try:
            response = requests.get(f"{BASE_URL}/events")
            if response.status_code == 200:
                events = response.json().get('events', [])
                
                if events:
                    df = pd.DataFrame(events)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("📨 No events")
        except Exception as e:
            st.error(f"❌ Error: {e}")