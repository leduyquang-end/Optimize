# -*- coding: utf-8 -*-
"""Benchmark cho sales_system — goi truc tiep services, khong can server.

  python bench_sales.py                    # 1 vong: product + order + inventory + analytics
  python bench_sales.py --repeat 30        # 30 vong trong 1 process (tick "Script tu lap")

Moi vong in cac dong STEP <ten> <ms> cho tung buoc, roi ket thuc bang RUN <ms>.
"""
import argparse
import sys
import time

sys.path.insert(0, ".")

from services.product_service import ProductService
from services.order_service import OrderService
from services.inventory_service import InventoryService
from services.analytics_service import AnalyticsService

QUERIES = ["MacBook", "Samsung", "Sony", "Dell", "HP"]


def bench_cycle(product_svc, order_svc, inv_svc, analytics_svc):
    products = product_svc.get_all_products()
    first_id = products[0].id if products else "prod1"

    started = time.perf_counter()
    for q in QUERIES:
        product_svc.search_products(q)
    print("STEP search_products %.1f" % ((time.perf_counter() - started) * 1000.0))

    started = time.perf_counter()
    for _ in range(5):
        product_svc.get_product(first_id)
    print("STEP get_product %.1f" % ((time.perf_counter() - started) * 1000.0))

    started = time.perf_counter()
    for _ in range(5):
        order_svc.create_order(
            customer_id="bench_user",
            items=[{"product_id": first_id, "quantity": 1}],
            shipping_address={
                "street": "123 Test", "city": "Hanoi",
                "state": "HN", "zip_code": "10000", "country": "VN",
            },
        )
    print("STEP create_order %.1f" % ((time.perf_counter() - started) * 1000.0))

    started = time.perf_counter()
    for _ in range(10):
        inv_svc.get_stock(first_id)
    print("STEP get_stock %.1f" % ((time.perf_counter() - started) * 1000.0))

    started = time.perf_counter()
    analytics_svc.get_metrics()
    print("STEP analytics %.1f" % ((time.perf_counter() - started) * 1000.0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1, help="so vong lap trong 1 process")
    args = parser.parse_args()

    product_svc = ProductService()
    order_svc = OrderService(product_svc)
    inv_svc = InventoryService()
    analytics_svc = AnalyticsService()

    for _ in range(max(1, args.repeat)):
        started = time.perf_counter()
        bench_cycle(product_svc, order_svc, inv_svc, analytics_svc)
        print("RUN %.1f" % ((time.perf_counter() - started) * 1000.0))
    print("done")


if __name__ == "__main__":
    main()
