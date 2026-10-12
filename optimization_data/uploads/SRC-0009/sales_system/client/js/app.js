// ============================================================
// 📁 client/js/app.js - GIAO DIỆN CLIENT
// ============================================================

// ============================================================
// CONFIGURATION
// ============================================================
const API_BASE = 'http://localhost:8000/api';
let cart = [];
let products = [];
let currentTab = 'products';
let discountApplied = null;

// ============================================================
// INITIALIZATION
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Sales System Client Started');
    
    // Check server status
    checkServerStatus();
    
    // Load initial data
    loadProducts();
    loadCartBadge();
    
    // Setup event listeners
    setupTabSwitching();
    setupSearch();
    setupEnterKey();
});

// ============================================================
// SERVER STATUS
// ============================================================
async function checkServerStatus() {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    
    try {
        const response = await fetch(`${API_BASE}/health`);
        if (response.ok) {
            dot.className = 'status-dot online';
            text.textContent = '🟢 Online';
            console.log('✅ Server connected');
        } else {
            dot.className = 'status-dot offline';
            text.textContent = '🔴 Offline';
            console.warn('⚠️ Server offline');
        }
    } catch (error) {
        dot.className = 'status-dot offline';
        text.textContent = '🔴 Không thể kết nối';
        console.error('❌ Server connection error:', error);
        showToast('⚠️ Không thể kết nối đến server! Vui lòng chạy python app.py', 'error');
    }
}

// ============================================================
// TAB SWITCHING
// ============================================================
function setupTabSwitching() {
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const tabName = this.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Update button styles
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        }
    });
    
    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    const targetTab = document.getElementById(`tab-${tabName}`);
    if (targetTab) {
        targetTab.classList.add('active');
    }
    
    currentTab = tabName;
    
    // Load data when switching tabs
    switch(tabName) {
        case 'cart':
            renderCart();
            break;
        case 'orders':
            loadOrders();
            break;
        case 'inventory':
            loadInventory();
            break;
        case 'analytics':
            loadAnalytics();
            break;
        case 'system':
            loadSystemInfo();
            loadEvents();
            loadPlugins();
            break;
    }
}

// ============================================================
// SEARCH
// ============================================================
function setupSearch() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const query = this.value.trim();
            if (query) {
                searchProducts(query);
            } else {
                renderProducts(products);
            }
        });
    }
}

function setupEnterKey() {
    // Enter key for coupon
    const couponInput = document.getElementById('couponInput');
    if (couponInput) {
        couponInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                applyCoupon();
            }
        });
    }
    
    // Enter key for customer ID
    const customerInput = document.getElementById('customerIdInput');
    if (customerInput) {
        customerInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                loadOrders();
            }
        });
    }
}

// ============================================================
// PRODUCTS
// ============================================================
async function loadProducts() {
    const grid = document.getElementById('productGrid');
    if (!grid) return;
    
    grid.innerHTML = '<div class="loading">🔄 Đang tải sản phẩm...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/products`);
        if (response.ok) {
            products = await response.json();
            renderProducts(products);
            console.log(`📦 Loaded ${products.length} products`);
        } else {
            grid.innerHTML = '<div class="loading">❌ Không thể tải sản phẩm</div>';
        }
    } catch (error) {
        console.error('Load products error:', error);
        grid.innerHTML = `<div class="loading">❌ Lỗi kết nối: ${error.message}</div>`;
        showToast('❌ Không thể tải sản phẩm', 'error');
    }
}

function renderProducts(productList) {
    const grid = document.getElementById('productGrid');
    if (!grid) return;
    
    if (!productList || productList.length === 0) {
        grid.innerHTML = `
            <div class="empty-cart" style="grid-column: 1/-1;">
                <span style="font-size: 48px;">📦</span>
                <h3>Không có sản phẩm</h3>
                <p>Hãy thêm sản phẩm mới</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = productList.map(product => `
        <div class="product-card">
            <div class="product-name">${escapeHtml(product.name)}</div>
            <div class="product-category">${escapeHtml(product.category || 'General')}</div>
            <div class="product-price">${formatCurrency(product.price)}</div>
            <div class="product-stock">
                ${product.stock > 0 
                    ? `<span class="in-stock">✅ Còn hàng (${product.stock})</span>` 
                    : `<span class="out-of-stock">❌ Hết hàng</span>`}
            </div>
            <div class="product-actions">
                <button class="btn btn-primary" onclick="addToCart('${product.id}')" 
                        ${product.stock === 0 ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : ''}>
                    🛒 Thêm vào giỏ
                </button>
                <button class="btn btn-secondary" onclick="showProductDetail('${product.id}')">
                    👁️
                </button>
            </div>
        </div>
    `).join('');
}

async function searchProducts(query) {
    try {
        const response = await fetch(`${API_BASE}/products/search?q=${encodeURIComponent(query)}`);
        if (response.ok) {
            const results = await response.json();
            renderProducts(results);
        }
    } catch (error) {
        console.error('Search error:', error);
    }
}

// ============================================================
// CART
// ============================================================
function addToCart(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) {
        showToast('❌ Không tìm thấy sản phẩm', 'error');
        return;
    }
    
    const existing = cart.find(item => item.product_id === productId);
    if (existing) {
        if (existing.quantity >= product.stock) {
            showToast('⚠️ Không đủ hàng!', 'warning');
            return;
        }
        existing.quantity += 1;
    } else {
        if (product.stock === 0) {
            showToast('⚠️ Sản phẩm đã hết hàng!', 'warning');
            return;
        }
        cart.push({
            product_id: product.id,
            name: product.name,
            price: product.price,
            quantity: 1,
            stock: product.stock
        });
    }
    
    updateCartBadge();
    renderCart();
    showToast(`✅ Đã thêm ${product.name} vào giỏ hàng`, 'success');
}

function removeFromCart(productId) {
    const index = cart.findIndex(item => item.product_id === productId);
    if (index !== -1) {
        const removed = cart[index];
        cart.splice(index, 1);
        updateCartBadge();
        renderCart();
        showToast(`🗑️ Đã xóa ${removed.name} khỏi giỏ hàng`, 'info');
    }
}

function updateQuantity(productId, delta) {
    const item = cart.find(i => i.product_id === productId);
    if (!item) return;
    
    item.quantity += delta;
    if (item.quantity <= 0) {
        removeFromCart(productId);
        return;
    }
    if (item.quantity > item.stock) {
        item.quantity = item.stock;
        showToast('⚠️ Không đủ hàng!', 'warning');
    }
    
    discountApplied = null;
    document.getElementById('couponInput').value = '';
    updateCartBadge();
    renderCart();
}

function clearCart() {
    if (cart.length === 0) return;
    if (confirm('Bạn có chắc muốn xóa toàn bộ giỏ hàng?')) {
        cart = [];
        discountApplied = null;
        document.getElementById('couponInput').value = '';
        updateCartBadge();
        renderCart();
        showToast('🧹 Đã xóa giỏ hàng', 'info');
    }
}

function renderCart() {
    const container = document.getElementById('cartItems');
    const subtotalEl = document.getElementById('subtotal');
    const discountEl = document.getElementById('discount');
    const shippingEl = document.getElementById('shipping');
    const totalEl = document.getElementById('total');
    
    if (!container) return;
    
    if (cart.length === 0) {
        container.innerHTML = `
            <div class="empty-cart">
                <span class="empty-icon">🛒</span>
                <h3>Giỏ hàng trống</h3>
                <p>Hãy thêm sản phẩm từ danh sách sản phẩm</p>
            </div>
        `;
        if (subtotalEl) subtotalEl.textContent = '₫0';
        if (discountEl) discountEl.textContent = '₫0';
        if (shippingEl) shippingEl.textContent = '₫0';
        if (totalEl) totalEl.textContent = '₫0';
        return;
    }
    
    let subtotal = 0;
    container.innerHTML = cart.map(item => {
        const itemTotal = item.price * item.quantity;
        subtotal += itemTotal;
        return `
            <div class="cart-item">
                <div class="cart-item-info">
                    <span class="cart-item-name">${escapeHtml(item.name)}</span>
                    <span class="cart-item-price">${formatCurrency(item.price)}</span>
                </div>
                <div class="cart-item-actions">
                    <div class="cart-item-qty">
                        <button onclick="updateQuantity('${item.product_id}', -1)">−</button>
                        <span>${item.quantity}</span>
                        <button onclick="updateQuantity('${item.product_id}', 1)" 
                                ${item.quantity >= item.stock ? 'disabled style="opacity:0.5;"' : ''}>+</button>
                    </div>
                    <span class="cart-item-remove" onclick="removeFromCart('${item.product_id}')">✕</span>
                </div>
            </div>
        `;
    }).join('');
    
    // Calculate totals
    let discount = 0;
    if (discountApplied) {
        discount = discountApplied.discount_amount || 0;
    }
    
    const shipping = subtotal > 1000000 ? 0 : 30000;
    const total = subtotal - discount + shipping;
    
    if (subtotalEl) subtotalEl.textContent = formatCurrency(subtotal);
    if (discountEl) discountEl.textContent = discount > 0 ? formatCurrency(discount) : '₫0';
    if (shippingEl) shippingEl.textContent = shipping === 0 ? 'Miễn phí' : formatCurrency(shipping);
    if (totalEl) totalEl.textContent = formatCurrency(total);
}

function updateCartBadge() {
    const badge = document.getElementById('cartBadge');
    if (!badge) return;
    const count = cart.reduce((sum, item) => sum + item.quantity, 0);
    badge.textContent = count;
    badge.style.display = count > 0 ? 'inline' : 'none';
}

function loadCartBadge() {
    updateCartBadge();
}

// ============================================================
// CHECKOUT
// ============================================================
async function applyCoupon() {
    const couponInput = document.getElementById('couponInput');
    if (!couponInput) return;
    
    const coupon = couponInput.value.trim();
    
    if (!coupon) {
        showToast('⚠️ Vui lòng nhập mã giảm giá', 'warning');
        return;
    }
    
    if (cart.length === 0) {
        showToast('⚠️ Giỏ hàng trống!', 'warning');
        return;
    }
    
    try {
        const subtotal = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
        const response = await fetch(`${API_BASE}/discounts/calculate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                amount: subtotal,
                coupon: coupon,
                total_items: cart.length
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            discountApplied = result;
            showToast(`✅ Áp dụng coupon: ${coupon} - Giảm ${result.discount_percentage.toFixed(0)}% (${formatCurrency(result.discount_amount)})`, 'success');
            renderCart();
        } else {
            discountApplied = null;
            const error = await response.json();
            showToast('❌ ' + (error.detail || 'Mã giảm giá không hợp lệ'), 'error');
            renderCart();
        }
    } catch (error) {
        console.error('Coupon error:', error);
        showToast('❌ Lỗi áp dụng coupon: ' + error.message, 'error');
    }
}

async function checkout() {
    if (cart.length === 0) {
        showToast('⚠️ Giỏ hàng trống!', 'warning');
        return;
    }
    
    const customerId = document.getElementById('customerIdCheckout');
    if (!customerId) return;
    
    const customerIdValue = customerId.value || 'customer_001';
    
    const orderData = {
        customer_id: customerIdValue,
        items: cart.map(item => ({
            product_id: item.product_id,
            quantity: item.quantity
        })),
        shipping_address: {
            street: '123 Main St',
            city: 'New York',
            state: 'NY',
            zip_code: '10001',
            country: 'USA'
        },
        coupon: document.getElementById('couponInput').value.trim() || null
    };
    
    try {
        showToast('⏳ Đang xử lý đơn hàng...', 'info');
        
        const response = await fetch(`${API_BASE}/orders`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderData)
        });
        
        if (response.ok) {
            const order = await response.json();
            showToast(`✅ Đơn hàng ${order.id.slice(0, 8)} đã được tạo!`, 'success');
            
            // Process payment
            await processPayment(order.id);
            
            // Clear cart
            cart = [];
            discountApplied = null;
            document.getElementById('couponInput').value = '';
            updateCartBadge();
            renderCart();
            
            // Load orders
            document.getElementById('customerIdInput').value = customerIdValue;
            loadOrders();
            
            // Switch to orders tab
            switchTab('orders');
        } else {
            const error = await response.json();
            showToast('❌ ' + (error.detail || 'Tạo đơn hàng thất bại'), 'error');
        }
    } catch (error) {
        console.error('Checkout error:', error);
        showToast('❌ Lỗi: ' + error.message, 'error');
    }
}

async function processPayment(orderId) {
    try {
        const response = await fetch(`${API_BASE}/payments/process`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                order_id: orderId,
                method: 'credit_card',
                card_info: { last4: '1234' }
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                showToast(`💳 Thanh toán thành công!`, 'success');
            } else {
                showToast(`❌ Thanh toán thất bại`, 'error');
            }
        } else {
            const error = await response.json();
            showToast(`❌ Thanh toán thất bại: ${error.detail || ''}`, 'error');
        }
    } catch (error) {
        console.error('Payment error:', error);
        showToast('❌ Lỗi thanh toán: ' + error.message, 'error');
    }
}

// ============================================================
// ORDERS
// ============================================================
async function loadOrders() {
    const container = document.getElementById('ordersContainer');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">🔄 Đang tải đơn hàng...</div>';
    
    const customerIdInput = document.getElementById('customerIdInput');
    const customerId = customerIdInput ? customerIdInput.value || 'customer_001' : 'customer_001';
    
    try {
        const response = await fetch(`${API_BASE}/orders/customer/${customerId}`);
        if (response.ok) {
            const orders = await response.json();
            renderOrders(orders);
        } else {
            container.innerHTML = '<div class="loading">❌ Không có đơn hàng</div>';
        }
    } catch (error) {
        console.error('Load orders error:', error);
        container.innerHTML = `<div class="loading">❌ Lỗi: ${error.message}</div>`;
    }
}

function renderOrders(orders) {
    const container = document.getElementById('ordersContainer');
    if (!container) return;
    
    if (!orders || orders.length === 0) {
        container.innerHTML = `
            <div class="empty-cart">
                <span style="font-size: 48px;">📋</span>
                <h3>Chưa có đơn hàng</h3>
                <p>Hãy tạo đơn hàng đầu tiên</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = orders.map(order => `
        <div class="order-item">
            <div class="order-header">
                <span class="order-id">📋 #${order.id.slice(0, 8)}</span>
                <span class="order-status ${order.status}">${order.status}</span>
            </div>
            <div class="order-details">
                <span>Khách hàng: ${order.customer_id}</span>
                <span style="margin-left: 16px;">Ngày: ${order.created_at ? new Date(order.created_at).toLocaleString('vi-VN') : '-'}</span>
            </div>
            <div class="order-total">💰 ${formatCurrency(order.total)}</div>
        </div>
    `).join('');
}

// ============================================================
// INVENTORY
// ============================================================
async function loadInventory() {
    const tbody = document.getElementById('inventoryBody');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="5" class="loading">🔄 Đang tải...</td></tr>';
    
    try {
        const response = await fetch(`${API_BASE}/inventory`);
        if (response.ok) {
            const inventory = await response.json();
            renderInventory(inventory);
        } else {
            tbody.innerHTML = '<tr><td colspan="5" class="loading">❌ Không thể tải</td></tr>';
        }
    } catch (error) {
        console.error('Load inventory error:', error);
        tbody.innerHTML = `<tr><td colspan="5" class="loading">❌ Lỗi: ${error.message}</td></tr>`;
    }
}

function renderInventory(inventory) {
    const tbody = document.getElementById('inventoryBody');
    if (!tbody) return;
    
    const entries = Object.entries(inventory);
    if (entries.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading">📦 Kho trống</td></tr>';
        return;
    }
    
    tbody.innerHTML = entries.map(([productId, data]) => {
        const stock = data.quantity || 0;
        let status = 'in-stock';
        let statusText = '✅ Còn hàng';
        if (stock === 0) {
            status = 'out-of-stock';
            statusText = '❌ Hết hàng';
        } else if (stock < 10) {
            status = 'low-stock';
            statusText = '⚠️ Sắp hết';
        }
        
        return `
            <tr>
                <td><strong>${escapeHtml(productId)}</strong></td>
                <td><strong>${stock}</strong></td>
                <td>${escapeHtml(data.warehouse || 'WH-01')}</td>
                <td>${data.last_updated ? new Date(data.last_updated).toLocaleString('vi-VN') : '-'}</td>
                <td><span class="status-badge ${status}">${statusText}</span></td>
            </tr>
        `;
    }).join('');
}

async function showLowStock() {
    try {
        const response = await fetch(`${API_BASE}/inventory/low-stock?threshold=10`);
        if (response.ok) {
            const data = await response.json();
            const items = data.low_stock_items || [];
            
            if (items.length === 0) {
                showToast('✅ Không có hàng tồn thấp', 'success');
            } else {
                const message = items.map(item => 
                    `⚠️ ${item.product_id}: ${item.stock} units`
                ).join('\n');
                showToast(`📦 Hàng tồn thấp:\n${message}`, 'warning');
            }
        } else {
            showToast('❌ Không thể kiểm tra hàng tồn thấp', 'error');
        }
    } catch (error) {
        console.error('Low stock error:', error);
        showToast('❌ Lỗi: ' + error.message, 'error');
    }
}

// ============================================================
// ANALYTICS
// ============================================================
async function loadAnalytics() {
    await loadMetrics();
    await loadSalesChart();
    await loadFunnel();
}

async function loadMetrics() {
    try {
        const response = await fetch(`${API_BASE}/analytics/metrics`);
        if (response.ok) {
            const metrics = await response.json();
            const totalOrders = document.getElementById('totalOrders');
            const totalRevenue = document.getElementById('totalRevenue');
            const totalCustomers = document.getElementById('totalCustomers');
            const avgOrder = document.getElementById('avgOrder');
            
            if (totalOrders) totalOrders.textContent = metrics.total_orders || 0;
            if (totalRevenue) totalRevenue.textContent = formatCurrency(metrics.total_revenue || 0);
            if (totalCustomers) totalCustomers.textContent = metrics.total_customers || 0;
            if (avgOrder) avgOrder.textContent = formatCurrency(metrics.average_order_value || 0);
        }
    } catch (error) {
        console.error('Metrics error:', error);
    }
}

async function loadSalesChart() {
    try {
        const response = await fetch(`${API_BASE}/analytics/sales?days=7`);
        if (response.ok) {
            const report = await response.json();
            renderChart(report);
        }
    } catch (error) {
        console.error('Chart error:', error);
    }
}

function renderChart(report) {
    const chartContainer = document.getElementById('salesChart');
    if (!chartContainer) return;
    
    const dailyOrders = report.daily_orders || {};
    const dates = Object.keys(dailyOrders);
    const values = Object.values(dailyOrders);
    
    if (dates.length === 0) {
        chartContainer.innerHTML = '<div class="loading">📊 Chưa có dữ liệu</div>';
        return;
    }
    
    const maxValue = Math.max(...values, 1);
    
    chartContainer.innerHTML = dates.map((date, index) => {
        const height = Math.max((values[index] / maxValue) * 100, 10);
        const day = date.slice(5);
        return `
            <div class="chart-bar" style="height: ${height}%;">
                <span class="chart-label">${day}</span>
            </div>
        `;
    }).join('');
}

async function loadFunnel() {
    try {
        const response = await fetch(`${API_BASE}/analytics/funnel`);
        if (response.ok) {
            const funnel = await response.json();
            const ordersCreated = document.getElementById('ordersCreated');
            const paymentsSuccess = document.getElementById('paymentsSuccess');
            const conversionRate = document.getElementById('conversionRate');
            
            if (ordersCreated) ordersCreated.textContent = funnel.orders_created || 0;
            if (paymentsSuccess) paymentsSuccess.textContent = funnel.payments_success || 0;
            if (conversionRate) conversionRate.textContent = (funnel.conversion_rate || 0) + '%';
        }
    } catch (error) {
        console.error('Funnel error:', error);
    }
}

// ============================================================
// SYSTEM
// ============================================================
async function loadSystemInfo() {
    const container = document.getElementById('systemInfo');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">🔄 Đang tải...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/health`);
        if (response.ok) {
            const info = await response.json();
            container.innerHTML = `
                <div class="info-row"><span>Status</span><span>✅ ${escapeHtml(info.status)}</span></div>
                <div class="info-row"><span>Version</span><span>${escapeHtml(info.version || '1.0.0')}</span></div>
                <div class="info-row"><span>Plugins</span><span>${info.plugins || 0}</span></div>
                <div class="info-row"><span>Products</span><span>${info.products || 0}</span></div>
                <div class="info-row"><span>Orders</span><span>${info.orders || 0}</span></div>
                <div class="info-row"><span>Events</span><span>${info.events || 0}</span></div>
                <div class="info-row"><span>Timestamp</span><span>${info.timestamp ? new Date(info.timestamp).toLocaleString('vi-VN') : '-'}</span></div>
            `;
        } else {
            container.innerHTML = `<div class="loading">❌ Không thể tải thông tin</div>`;
        }
    } catch (error) {
        console.error('System info error:', error);
        container.innerHTML = `<div class="loading">❌ Lỗi: ${error.message}</div>`;
    }
}

async function loadEvents() {
    const container = document.getElementById('eventsList');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">🔄 Đang tải...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/events`);
        if (response.ok) {
            const data = await response.json();
            const events = data.events || [];
            
            if (events.length === 0) {
                container.innerHTML = '<div class="loading">📨 Chưa có sự kiện</div>';
                return;
            }
            
            container.innerHTML = events.slice(-10).map(event => `
                <div class="event-item">
                    <div><strong>${escapeHtml(event.event_type)}</strong></div>
                    <div class="event-time">${event.timestamp ? new Date(event.timestamp).toLocaleString('vi-VN') : '-'}</div>
                </div>
            `).join('');
        } else {
            container.innerHTML = `<div class="loading">❌ Không thể tải events</div>`;
        }
    } catch (error) {
        console.error('Events error:', error);
        container.innerHTML = `<div class="loading">❌ Lỗi: ${error.message}</div>`;
    }
}

async function loadPlugins() {
    const container = document.getElementById('pluginsList');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">🔄 Đang tải...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/plugins`);
        if (response.ok) {
            const data = await response.json();
            const plugins = data.plugins || [];
            
            if (plugins.length === 0) {
                container.innerHTML = '<div class="loading">🔌 Chưa có plugin</div>';
                return;
            }
            
            container.innerHTML = plugins.map(plugin => `
                <div class="plugin-item">
                    <span>${escapeHtml(plugin.name)}</span>
                    <span class="plugin-status ${plugin.status}">${plugin.status}</span>
                </div>
            `).join('');
        } else {
            container.innerHTML = `<div class="loading">❌ Không thể tải plugins</div>`;
        }
    } catch (error) {
        console.error('Plugins error:', error);
        container.innerHTML = `<div class="loading">❌ Lỗi: ${error.message}</div>`;
    }
}

// ============================================================
// PRODUCT MODAL
// ============================================================
function showAddProduct() {
    const modal = document.getElementById('addProductModal');
    if (!modal) return;
    modal.classList.add('active');
    
    const form = document.getElementById('addProductForm');
    if (form) form.reset();
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove('active');
}

async function submitProduct() {
    const name = document.getElementById('prodName');
    const description = document.getElementById('prodDesc');
    const price = document.getElementById('prodPrice');
    const stock = document.getElementById('prodStock');
    const sku = document.getElementById('prodSku');
    const category = document.getElementById('prodCategory');
    
    if (!name || !price || !stock || !sku) {
        showToast('⚠️ Vui lòng điền đầy đủ thông tin!', 'warning');
        return;
    }
    
    const nameValue = name.value.trim();
    const descValue = description ? description.value.trim() : '';
    const priceValue = parseFloat(price.value);
    const stockValue = parseInt(stock.value);
    const skuValue = sku.value.trim();
    const categoryValue = category ? category.value.trim() || 'General' : 'General';
    
    if (!nameValue || !skuValue || isNaN(priceValue) || isNaN(stockValue)) {
        showToast('⚠️ Vui lòng điền đầy đủ thông tin!', 'warning');
        return;
    }
    
    if (priceValue <= 0) {
        showToast('⚠️ Giá phải lớn hơn 0!', 'warning');
        return;
    }
    
    if (stockValue < 0) {
        showToast('⚠️ Tồn kho không được âm!', 'warning');
        return;
    }
    
    const product = { 
        name: nameValue, 
        description: descValue, 
        price: priceValue, 
        stock: stockValue, 
        sku: skuValue, 
        category: categoryValue 
    };
    
    try {
        const response = await fetch(`${API_BASE}/products`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(product)
        });
        
        if (response.ok) {
            const result = await response.json();
            showToast(`✅ Đã thêm sản phẩm: ${result.name}`, 'success');
            closeModal('addProductModal');
            loadProducts();
        } else {
            const error = await response.json();
            showToast('❌ ' + (error.detail || 'Thêm sản phẩm thất bại'), 'error');
        }
    } catch (error) {
        console.error('Submit product error:', error);
        showToast('❌ Lỗi: ' + error.message, 'error');
    }
}

function showProductDetail(productId) {
    const product = products.find(p => p.id === productId);
    if (!product) {
        showToast('❌ Không tìm thấy sản phẩm', 'error');
        return;
    }
    
    showToast(`
        📦 ${product.name}
        💰 ${formatCurrency(product.price)}
        📂 ${product.category || 'General'}
        📊 Stock: ${product.stock}
    `, 'info');
}

// ============================================================
// UTILITY FUNCTIONS
// ============================================================
function formatCurrency(amount) {
    if (amount === undefined || amount === null || isNaN(amount)) return '₫0';
    return new Intl.NumberFormat('vi-VN', {
        style: 'currency',
        currency: 'VND',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
        <span class="toast-message">${message}</span>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(40px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => {
            if (toast.parentNode) toast.remove();
        }, 300);
    }, 4000);
}

// ============================================================
// KEYBOARD SHORTCUTS
// ============================================================
document.addEventListener('keydown', function(e) {
    // Escape to close modal
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.active').forEach(modal => {
            modal.classList.remove('active');
        });
    }
    
    // Ctrl+R to refresh products
    if (e.ctrlKey && e.key === 'r') {
        e.preventDefault();
        if (currentTab === 'products') {
            loadProducts();
        } else if (currentTab === 'inventory') {
            loadInventory();
        } else if (currentTab === 'analytics') {
            loadAnalytics();
        }
    }
});

// ============================================================
// CONSOLE HELPERS
// ============================================================
console.log('🛒 Sales System Client v1.0');
console.log('📋 Available commands:');
console.log('  - loadProducts()  : Refresh products');
console.log('  - loadOrders()    : Refresh orders');
console.log('  - loadInventory() : Refresh inventory');
console.log('  - loadAnalytics() : Refresh analytics');
console.log('  - clearCart()     : Clear cart');