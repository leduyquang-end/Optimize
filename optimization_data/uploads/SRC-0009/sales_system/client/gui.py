# client/gui.py
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext
import requests
import json
from typing import List, Dict, Any
from datetime import datetime
import threading
import time

class SalesClient:
    """GUI Client for Sales System"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("🛒 Hệ Thống Bán Hàng - Multi-Architecture")
        self.root.geometry("1400x800")
        self.root.configure(bg='#f0f0f0')
        
        self.base_url = "http://localhost:8000/api"
        self.products = []
        self.cart = []
        self.orders = []
        self.current_order = None
        
        self.setup_menu()
        self.setup_ui()
        self.load_products()
        self.load_inventory()
        self.load_metrics()
        self.update_status("✅ Hệ thống sẵn sàng")
    
    def setup_menu(self):
        """Setup menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="📁 File", menu=file_menu)
        file_menu.add_command(label="🔄 Refresh", command=self.refresh_all)
        file_menu.add_separator()
        file_menu.add_command(label="🚪 Exit", command=self.root.quit)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="👁️ View", menu=view_menu)
        view_menu.add_command(label="📦 Products", command=self.show_products)
        view_menu.add_command(label="📋 Orders", command=self.view_orders)
        view_menu.add_command(label="📊 Analytics", command=self.show_analytics)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="🔧 Tools", menu=tools_menu)
        tools_menu.add_command(label="🔌 Plugins", command=self.show_plugins)
        tools_menu.add_command(label="📨 Events", command=self.show_events)
        tools_menu.add_command(label="📊 Inventory Report", command=self.inventory_report)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="❓ Help", menu=help_menu)
        help_menu.add_command(label="📖 Documentation", command=self.show_docs)
        help_menu.add_command(label="ℹ️ About", command=self.show_about)
    
    def setup_ui(self):
        """Setup the user interface"""
        # Main container
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Title bar
        title_frame = ttk.Frame(main_container)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = tk.Label(
            title_frame,
            text="🛒 Hệ Thống Bán Hàng Đa Kiến Trúc",
            font=("Arial", 24, "bold"),
            fg="#2c3e50"
        )
        title_label.pack(side=tk.LEFT)
        
        # Status indicator
        self.status_indicator = tk.Label(
            title_frame,
            text="🟢 Online",
            font=("Arial", 10, "bold"),
            fg="green"
        )
        self.status_indicator.pack(side=tk.RIGHT, padx=10)
        
        # Notebook (Tabs)
        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Products
        self.products_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.products_tab, text="📦 Sản Phẩm")
        self.setup_products_tab()
        
        # Tab 2: Cart
        self.cart_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.cart_tab, text="🛒 Giỏ Hàng")
        self.setup_cart_tab()
        
        # Tab 3: Orders
        self.orders_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.orders_tab, text="📋 Đơn Hàng")
        self.setup_orders_tab()
        
        # Tab 4: Inventory
        self.inventory_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.inventory_tab, text="📦 Kho Hàng")
        self.setup_inventory_tab()
        
        # Tab 5: Analytics
        self.analytics_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.analytics_tab, text="📊 Thống Kê")
        self.setup_analytics_tab()
        
        # Tab 6: System
        self.system_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.system_tab, text="⚙️ Hệ Thống")
        self.setup_system_tab()
        
        # Status bar
        status_frame = ttk.Frame(main_container)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_bar = tk.Label(
            status_frame,
            text="✅ Ready",
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=("Arial", 9)
        )
        self.status_bar.pack(fill=tk.X)
    
    def setup_products_tab(self):
        """Setup products tab"""
        # Toolbar
        toolbar = ttk.Frame(self.products_tab)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Label(toolbar, text="🔍 Tìm kiếm:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.search_products())
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(toolbar, text="🔄 Refresh", command=self.load_products).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="➕ Thêm Sản Phẩm", command=self.add_product_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="🛒 Thêm vào Giỏ", command=self.add_to_cart).pack(side=tk.LEFT, padx=5)
        
        # Product tree
        columns = ("ID", "Tên", "Giá", "Tồn Kho", "Danh Mục", "SKU")
        self.product_tree = ttk.Treeview(self.products_tab, columns=columns, show="headings", height=20)
        
        col_widths = [80, 200, 100, 80, 120, 100]
        for col, width in zip(columns, col_widths):
            self.product_tree.heading(col, text=col)
            self.product_tree.column(col, width=width)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.products_tab, orient=tk.VERTICAL, command=self.product_tree.yview)
        self.product_tree.configure(yscrollcommand=scrollbar.set)
        
        self.product_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def setup_cart_tab(self):
        """Setup cart tab"""
        # Cart list
        self.cart_listbox = tk.Listbox(self.cart_tab, height=20, font=("Courier", 10))
        self.cart_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Cart controls
        controls = ttk.Frame(self.cart_tab)
        controls.pack(fill=tk.X, pady=5)
        
        self.total_label = ttk.Label(controls, text="💰 Tổng: $0.00", font=("Arial", 14, "bold"))
        self.total_label.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(controls, text="❌ Xóa", command=self.remove_from_cart).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="🧹 Xóa Hết", command=self.clear_cart).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="💳 Thanh Toán", command=self.checkout, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
    
    def setup_orders_tab(self):
        """Setup orders tab"""
        # Toolbar
        toolbar = ttk.Frame(self.orders_tab)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Label(toolbar, text="Customer ID:").pack(side=tk.LEFT, padx=5)
        self.customer_id_var = tk.StringVar(value="customer_001")
        ttk.Entry(toolbar, textvariable=self.customer_id_var, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="📋 Xem Đơn Hàng", command=self.view_customer_orders).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="🔄 Refresh", command=self.load_orders).pack(side=tk.LEFT, padx=5)
        
        # Orders tree
        columns = ("ID", "Khách Hàng", "Tổng", "Trạng Thái", "Thanh Toán", "Ngày Tạo")
        self.orders_tree = ttk.Treeview(self.orders_tab, columns=columns, show="headings", height=15)
        
        col_widths = [150, 120, 100, 100, 100, 150]
        for col, width in zip(columns, col_widths):
            self.orders_tree.heading(col, text=col)
            self.orders_tree.column(col, width=width)
        
        scrollbar = ttk.Scrollbar(self.orders_tab, orient=tk.VERTICAL, command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=scrollbar.set)
        
        self.orders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Order detail
        detail_frame = ttk.LabelFrame(self.orders_tab, text="Chi Tiết Đơn Hàng", padding="10")
        detail_frame.pack(fill=tk.X, pady=10)
        
        self.order_detail_text = scrolledtext.ScrolledText(detail_frame, height=8)
        self.order_detail_text.pack(fill=tk.X)
        
        # Bind selection
        self.orders_tree.bind('<<TreeviewSelect>>', self.on_order_select)
    
    def setup_inventory_tab(self):
        """Setup inventory tab"""
        # Inventory tree
        columns = ("Sản Phẩm", "Số Lượng", "Kho", "Cập Nhật")
        self.inventory_tree = ttk.Treeview(self.inventory_tab, columns=columns, show="headings", height=15)
        
        col_widths = [200, 100, 100, 150]
        for col, width in zip(columns, col_widths):
            self.inventory_tree.heading(col, text=col)
            self.inventory_tree.column(col, width=width)
        
        scrollbar = ttk.Scrollbar(self.inventory_tab, orient=tk.VERTICAL, command=self.inventory_tree.yview)
        self.inventory_tree.configure(yscrollcommand=scrollbar.set)
        
        self.inventory_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Controls
        controls = ttk.Frame(self.inventory_tab)
        controls.pack(fill=tk.X, pady=5)
        
        ttk.Button(controls, text="🔄 Refresh", command=self.load_inventory).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="📊 Báo Cáo Kho", command=self.inventory_report).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="⚠️ Hàng Tồn Thấp", command=self.show_low_stock).pack(side=tk.LEFT, padx=5)
    
    def setup_analytics_tab(self):
        """Setup analytics tab"""
        # Metrics frame
        metrics_frame = ttk.LabelFrame(self.analytics_tab, text="📊 Metrics", padding="10")
        metrics_frame.pack(fill=tk.X, pady=5)
        
        self.metrics_text = scrolledtext.ScrolledText(metrics_frame, height=8)
        self.metrics_text.pack(fill=tk.X)
        
        # Buttons
        btn_frame = ttk.Frame(self.analytics_tab)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="🔄 Refresh Metrics", command=self.load_metrics).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📊 Sales Report", command=self.show_sales_report).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📈 Funnel", command=self.show_funnel).pack(side=tk.LEFT, padx=5)
    
    def setup_system_tab(self):
        """Setup system tab"""
        # System info
        info_frame = ttk.LabelFrame(self.system_tab, text="ℹ️ Thông Tin Hệ Thống", padding="10")
        info_frame.pack(fill=tk.X, pady=5)
        
        self.system_info_text = scrolledtext.ScrolledText(info_frame, height=8)
        self.system_info_text.pack(fill=tk.X)
        
        # Plugin info
        plugin_frame = ttk.LabelFrame(self.system_tab, text="🔌 Plugins", padding="10")
        plugin_frame.pack(fill=tk.X, pady=5)
        
        self.plugin_text = scrolledtext.ScrolledText(plugin_frame, height=6)
        self.plugin_text.pack(fill=tk.X)
        
        # Buttons
        btn_frame = ttk.Frame(self.system_tab)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="🔄 Refresh", command=self.load_system_info).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📨 Events", command=self.show_events).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔌 Plugins", command=self.show_plugins).pack(side=tk.LEFT, padx=5)
    
    # --- Business Logic ---
    
    def update_status(self, message: str):
        """Update status bar"""
        self.status_bar.config(text=f"⏳ {message}")
        self.root.update()
    
    def refresh_all(self):
        """Refresh all data"""
        self.update_status("Đang refresh...")
        self.load_products()
        self.load_inventory()
        self.load_metrics()
        self.load_orders()
        self.load_system_info()
        self.update_status("✅ Đã refresh")
    
    def load_products(self):
        """Load products from API"""
        try:
            response = requests.get(f"{self.base_url}/products", timeout=3)
            if response.status_code == 200:
                self.products = response.json()
                self.update_product_table()
                self.update_status(f"✅ Đã tải {len(self.products)} sản phẩm")
            else:
                self.update_status(f"❌ Lỗi tải sản phẩm: {response.status_code}")
        except Exception as e:
            self.update_status(f"❌ Lỗi: {str(e)}")
    
    def update_product_table(self):
        """Update product table"""
        for item in self.product_tree.get_children():
            self.product_tree.delete(item)
        
        for product in self.products:
            self.product_tree.insert("", "end", values=(
                product['id'][:8],
                product['name'],
                f"${product['price']:.2f}",
                product['stock'],
                product['category'],
                product['sku']
            ))
    
    def search_products(self):
        """Search products"""
        query = self.search_var.get().strip()
        if not query:
            self.update_product_table()
            return
        
        filtered = [p for p in self.products if query.lower() in p['name'].lower()]
        
        for item in self.product_tree.get_children():
            self.product_tree.delete(item)
        
        for product in filtered:
            self.product_tree.insert("", "end", values=(
                product['id'][:8],
                product['name'],
                f"${product['price']:.2f}",
                product['stock'],
                product['category'],
                product['sku']
            ))
    
    def add_to_cart(self):
        """Add selected product to cart"""
        selection = self.product_tree.selection()
        if not selection:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn sản phẩm")
            return
        
        item = self.product_tree.item(selection[0])
        product_id = item['values'][0]
        product = next((p for p in self.products if p['id'].startswith(product_id)), None)
        
        if product:
            quantity = simpledialog.askinteger(
                "Số lượng",
                f"Nhập số lượng cho {product['name']}:",
                minvalue=1,
                maxvalue=product['stock']
            )
            if quantity:
                self.cart.append({
                    'product_id': product['id'],
                    'name': product['name'],
                    'price': product['price'],
                    'quantity': quantity
                })
                self.update_cart_display()
                self.update_status(f"✅ Đã thêm {quantity} x {product['name']}")
    
    def update_cart_display(self):
        """Update cart display"""
        self.cart_listbox.delete(0, tk.END)
        total = 0
        
        for i, item in enumerate(self.cart):
            subtotal = item['price'] * item['quantity']
            total += subtotal
            self.cart_listbox.insert(
                tk.END,
                f"{i+1}. {item['name']} x {item['quantity']} = ${subtotal:.2f}"
            )
        
        self.cart_listbox.insert(tk.END, "-" * 50)
        self.cart_listbox.insert(tk.END, f"💰 TỔNG: ${total:.2f}")
        self.total_label.config(text=f"💰 Tổng: ${total:.2f}")
    
    def remove_from_cart(self):
        """Remove selected item from cart"""
        selection = self.cart_listbox.curselection()
        if selection and selection[0] < len(self.cart):
            removed = self.cart.pop(selection[0])
            self.update_cart_display()
            self.update_status(f"✅ Đã xóa {removed['name']}")
    
    def clear_cart(self):
        """Clear cart"""
        if self.cart:
            self.cart = []
            self.update_cart_display()
            self.update_status("🧹 Đã xóa giỏ hàng")
    
    def checkout(self):
        """Checkout"""
        if not self.cart:
            messagebox.showwarning("Cảnh báo", "Giỏ hàng trống!")
            return
        
        customer_id = simpledialog.askstring(
            "Khách hàng",
            "Nhập Customer ID:",
            initialvalue="customer_001"
        )
        if not customer_id:
            return
        
        try:
            order_data = {
                'customer_id': customer_id,
                'items': [
                    {
                        'product_id': item['product_id'],
                        'quantity': item['quantity']
                    }
                    for item in self.cart
                ],
                'shipping_address': {
                    'street': '123 Main St',
                    'city': 'New York',
                    'state': 'NY',
                    'zip_code': '10001',
                    'country': 'USA'
                }
            }
            
            response = requests.post(f"{self.base_url}/orders", json=order_data, timeout=5)
            if response.status_code == 201:
                order = response.json()
                messagebox.showinfo(
                    "Thành công",
                    f"✅ Đơn hàng đã được tạo!\n\n"
                    f"Order ID: {order['id'][:8]}\n"
                    f"Tổng: ${order['total']:.2f}\n"
                    f"Trạng thái: {order['status']}"
                )
                self.cart = []
                self.update_cart_display()
                self.load_orders()
                self.load_metrics()
                self.update_status("✅ Checkout thành công")
            else:
                messagebox.showerror("Lỗi", f"Checkout thất bại: {response.text}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Lỗi: {str(e)}")
    
    def load_orders(self):
        """Load orders"""
        try:
            customer_id = self.customer_id_var.get()
            response = requests.get(
                f"{self.base_url}/orders/customer/{customer_id}",
                timeout=3
            )
            if response.status_code == 200:
                self.orders = response.json()
                self.update_orders_table()
        except Exception as e:
            self.update_status(f"❌ Lỗi tải đơn hàng: {str(e)}")
    
    def view_customer_orders(self):
        """View customer orders"""
        self.load_orders()
    
    def update_orders_table(self):
        """Update orders table"""
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)
        
        for order in self.orders:
            self.orders_tree.insert("", "end", values=(
                order['id'][:8],
                order.get('customer_id', 'N/A'),
                f"${order['total']:.2f}",
                order.get('status', 'N/A'),
                order.get('payment_status', 'N/A'),
                order.get('created_at', '')[:19]
            ))
    
    def on_order_select(self, event):
        """Handle order selection"""
        selection = self.orders_tree.selection()
        if not selection:
            return
        
        item = self.orders_tree.item(selection[0])
        order_id = item['values'][0]
        
        try:
            response = requests.get(f"{self.base_url}/orders/{order_id}", timeout=3)
            if response.status_code == 200:
                order = response.json()
                self.order_detail_text.delete(1.0, tk.END)
                self.order_detail_text.insert(1.0, json.dumps(order, indent=2, ensure_ascii=False))
        except Exception as e:
            self.order_detail_text.delete(1.0, tk.END)
            self.order_detail_text.insert(1.0, f"Lỗi: {str(e)}")
    
    def load_inventory(self):
        """Load inventory"""
        try:
            response = requests.get(f"{self.base_url}/inventory", timeout=3)
            if response.status_code == 200:
                inventory = response.json()
                self.update_inventory_table(inventory)
        except Exception as e:
            self.update_status(f"❌ Lỗi tải kho: {str(e)}")
    
    def update_inventory_table(self, inventory):
        """Update inventory table"""
        for item in self.inventory_tree.get_children():
            self.inventory_tree.delete(item)
        
        for product_id, data in inventory.items():
            if isinstance(data, dict):
                self.inventory_tree.insert("", "end", values=(
                    product_id,
                    data.get('quantity', 0),
                    data.get('warehouse', 'N/A'),
                    data.get('last_updated', '')[:19]
                ))
    
    def show_low_stock(self):
        """Show low stock items"""
        try:
            response = requests.get(f"{self.base_url}/inventory/low-stock?threshold=10", timeout=3)
            if response.status_code == 200:
                data = response.json()
                low_stock = data.get('low_stock_items', [])
                
                if low_stock:
                    msg = "⚠️ HÀNG TỒN THẤP:\n\n"
                    for item in low_stock:
                        msg += f"  - {item['product_id']}: {item['stock']} units\n"
                    messagebox.showwarning("Hàng tồn thấp", msg)
                else:
                    messagebox.showinfo("Thông báo", "✅ Không có hàng tồn thấp")
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
    
    def load_metrics(self):
        """Load analytics metrics"""
        try:
            response = requests.get(f"{self.base_url}/analytics/metrics", timeout=3)
            if response.status_code == 200:
                metrics = response.json()
                self.display_metrics(metrics)
        except Exception as e:
            self.update_status(f"❌ Lỗi tải metrics: {str(e)}")
    
    def display_metrics(self, metrics):
        """Display metrics in text widget"""
        self.metrics_text.delete(1.0, tk.END)
        
        lines = [
            "📊 SYSTEM METRICS",
            "=" * 40,
            f"📦 Tổng đơn hàng: {metrics.get('total_orders', 0)}",
            f"💰 Doanh thu: ${metrics.get('total_revenue', 0):.2f}",
            f"👤 Khách hàng: {metrics.get('total_customers', 0)}",
            f"💳 Trung bình/đơn: ${metrics.get('average_order_value', 0):.2f}",
            "",
            "📅 Daily Orders:",
        ]
        
        daily_orders = metrics.get('daily_orders', {})
        for date, count in list(daily_orders.items())[-7:]:
            lines.append(f"  {date}: {count} đơn")
        
        lines.append("")
        lines.append(f"⏱️ Uptime: {metrics.get('uptime', 'N/A')}")
        
        self.metrics_text.insert(1.0, "\n".join(lines))
    
    def load_system_info(self):
        """Load system info"""
        try:
            # Health check
            response = requests.get(f"{self.base_url}/health", timeout=3)
            if response.status_code == 200:
                health = response.json()
                
                self.system_info_text.delete(1.0, tk.END)
                lines = [
                    "ℹ️ SYSTEM INFORMATION",
                    "=" * 40,
                    f"Status: {health.get('status', 'N/A')}",
                    f"Version: {health.get('version', 'N/A')}",
                    f"Plugins: {health.get('plugins', 0)}",
                    f"Products: {health.get('products', 0)}",
                    f"Orders: {health.get('orders', 0)}",
                    f"Events: {health.get('events', 0)}",
                    f"Timestamp: {health.get('timestamp', 'N/A')}"
                ]
                self.system_info_text.insert(1.0, "\n".join(lines))
            
            # Load plugins
            self.load_plugins()
            
        except Exception as e:
            self.update_status(f"❌ Lỗi: {str(e)}")
    
    def load_plugins(self):
        """Load plugins info"""
        try:
            response = requests.get(f"{self.base_url}/plugins", timeout=3)
            if response.status_code == 200:
                data = response.json()
                plugins = data.get('plugins', [])
                
                self.plugin_text.delete(1.0, tk.END)
                lines = ["🔌 PLUGINS", "=" * 30]
                for plugin in plugins:
                    status_icon = "✅" if plugin['status'] == 'active' else "❌"
                    lines.append(f"{status_icon} {plugin['name']} v{plugin['version']}")
                self.plugin_text.insert(1.0, "\n".join(lines))
                
        except Exception as e:
            self.plugin_text.delete(1.0, tk.END)
            self.plugin_text.insert(1.0, f"Lỗi: {str(e)}")
    
    def show_products(self):
        """Switch to products tab"""
        self.notebook.select(self.products_tab)
    
    def view_orders(self):
        """Switch to orders tab"""
        self.notebook.select(self.orders_tab)
        self.load_orders()
    
    def show_analytics(self):
        """Switch to analytics tab"""
        self.notebook.select(self.analytics_tab)
        self.load_metrics()
    
    def show_plugins(self):
        """Show plugins"""
        self.notebook.select(self.system_tab)
        self.load_system_info()
    
    def show_events(self):
        """Show events"""
        try:
            response = requests.get(f"{self.base_url}/events", timeout=3)
            if response.status_code == 200:
                data = response.json()
                events = data.get('events', [])
                
                msg = "📨 LỊCH SỬ SỰ KIỆN\n"
                msg += "=" * 40 + "\n"
                for event in events[-20:]:
                    msg += f"🔔 {event.get('event_type', 'N/A')}\n"
                    msg += f"   📅 {event.get('timestamp', '')[:19]}\n"
                    msg += f"   📦 {event.get('aggregate_id', '')[:8]}\n\n"
                
                # Show in new window
                self.show_text_window("Events", msg)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
    
    def inventory_report(self):
        """Show inventory report"""
        try:
            response = requests.get(f"{self.base_url}/inventory/warehouses", timeout=3)
            if response.status_code == 200:
                data = response.json()
                warehouses = data.get('warehouses', {})
                
                msg = "🏭 BÁO CÁO KHO HÀNG\n"
                msg += "=" * 40 + "\n"
                for wh_id, wh_data in warehouses.items():
                    msg += f"\n📍 {wh_data.get('name', wh_id)}\n"
                    msg += f"   Vị trí: {wh_data.get('location', 'N/A')}\n"
                
                self.show_text_window("Inventory Report", msg)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
    
    def show_sales_report(self):
        """Show sales report"""
        try:
            response = requests.get(f"{self.base_url}/analytics/sales?days=7", timeout=3)
            if response.status_code == 200:
                report = response.json()
                
                msg = "📊 BÁO CÁO DOANH SỐ (7 ngày)\n"
                msg += "=" * 40 + "\n"
                msg += f"📦 Tổng đơn: {report.get('total_orders', 0)}\n"
                msg += f"💰 Doanh thu: ${report.get('total_revenue', 0):.2f}\n"
                msg += f"📈 Trung bình/ngày: ${report.get('average_daily_revenue', 0):.2f}\n\n"
                msg += "📅 Chi tiết theo ngày:\n"
                
                daily = report.get('daily_orders', {})
                for date, count in daily.items():
                    revenue = report.get('daily_revenue', {}).get(date, 0)
                    msg += f"  {date}: {count} đơn - ${revenue:.2f}\n"
                
                self.show_text_window("Sales Report", msg)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
    
    def show_funnel(self):
        """Show conversion funnel"""
        try:
            response = requests.get(f"{self.base_url}/analytics/funnel", timeout=3)
            if response.status_code == 200:
                funnel = response.json()
                
                msg = "📈 CONVERSION FUNNEL\n"
                msg += "=" * 40 + "\n"
                msg += f"📝 Orders Created: {funnel.get('orders_created', 0)}\n"
                msg += f"💳 Payments Success: {funnel.get('payments_success', 0)}\n"
                msg += f"🎯 Conversion Rate: {funnel.get('conversion_rate', 0)}%\n"
                
                self.show_text_window("Funnel", msg)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
    
    def show_text_window(self, title: str, content: str):
        """Show text in a new window"""
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("600x400")
        
        text = scrolledtext.ScrolledText(window, wrap=tk.WORD, font=("Courier", 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert(1.0, content)
        text.config(state=tk.DISABLED)
    
    def add_product_dialog(self):
        """Add product dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Thêm Sản Phẩm Mới")
        dialog.geometry("400x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        fields = {}
        labels = ["Tên", "Mô tả", "Giá", "Tồn kho", "SKU", "Danh mục"]
        
        for i, label in enumerate(labels):
            ttk.Label(dialog, text=f"{label}:").grid(row=i, column=0, padx=5, pady=5, sticky=tk.W)
            entry = ttk.Entry(dialog, width=30)
            entry.grid(row=i, column=1, padx=5, pady=5)
            fields[label.lower()] = entry
        
        def submit():
            try:
                product = {
                    'name': fields['tên'].get(),
                    'description': fields['mô tả'].get() or "No description",
                    'price': float(fields['giá'].get()),
                    'stock': int(fields['tồn kho'].get()),
                    'sku': fields['sku'].get(),
                    'category': fields['danh mục'].get() or "General"
                }
                
                response = requests.post(f"{self.base_url}/products", json=product, timeout=5)
                if response.status_code == 201:
                    messagebox.showinfo("Thành công", "✅ Đã thêm sản phẩm!")
                    dialog.destroy()
                    self.load_products()
                else:
                    messagebox.showerror("Lỗi", f"Thất bại: {response.text}")
            except ValueError:
                messagebox.showerror("Lỗi", "Vui lòng nhập đúng định dạng số")
            except Exception as e:
                messagebox.showerror("Lỗi", str(e))
        
        ttk.Button(dialog, text="✅ Thêm", command=submit).grid(row=len(labels), column=0, columnspan=2, pady=20)
        ttk.Button(dialog, text="❌ Hủy", command=dialog.destroy).grid(row=len(labels)+1, column=0, columnspan=2)
    
    def show_docs(self):
        """Show documentation"""
        msg = """
📖 HƯỚNG DẪN SỬ DỤNG

1. 📦 Sản phẩm:
   - Xem danh sách sản phẩm
   - Tìm kiếm sản phẩm
   - Thêm sản phẩm mới
   - Thêm vào giỏ hàng

2. 🛒 Giỏ hàng:
   - Xem các sản phẩm đã chọn
   - Xóa sản phẩm khỏi giỏ
   - Thanh toán đơn hàng

3. 📋 Đơn hàng:
   - Xem lịch sử đơn hàng
   - Xem chi tiết đơn hàng

4. 📦 Kho hàng:
   - Xem tồn kho
   - Kiểm tra hàng tồn thấp

5. 📊 Thống kê:
   - Metrics hệ thống
   - Báo cáo doanh số
   - Conversion funnel

6. ⚙️ Hệ thống:
   - Thông tin hệ thống
   - Danh sách plugins
   - Lịch sử sự kiện
"""
        self.show_text_window("📖 Hướng dẫn", msg)
    
    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo(
            "ℹ️ About",
            "🛒 Hệ Thống Bán Hàng Đa Kiến Trúc\n\n"
            "Version: 1.0.0\n"
            "Architectures:\n"
            "  - Client-Server (GUI + API)\n"
            "  - Layered Architecture\n"
            "  - Event-Driven\n"
            "  - Microkernel (Plugins)\n"
            "  - DDD (Domain-Driven Design)\n\n"
            "Powered by Python + FastAPI + Tkinter"
        )

def main():
    """Main entry point for GUI client"""
    try:
        root = tk.Tk()
        
        # Style
        style = ttk.Style()
        style.configure("Accent.TButton", foreground="white", background="#2ecc71")
        
        app = SalesClient(root)
        root.mainloop()
    except Exception as e:
        print(f"Error starting GUI: {e}")

if __name__ == "__main__":
    main()