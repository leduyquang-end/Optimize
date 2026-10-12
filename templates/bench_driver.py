# -*- coding: utf-8 -*-
"""
bench_driver.py — script đo DÙNG CHUNG cho mọi nguồn có cấu trúc services/ + core/.

Cách dùng (chạy trong folder nguồn):
    python bench_driver.py                # 1 vòng: in STEP <tên> <ms> rồi THOÁT
    python bench_driver.py --repeat 30    # 30 vòng trong 1 process (tick "Script tự lặp")
    python bench_driver.py --discover     # liệt kê hàm đo được trong services/ + core/

Vì sao không treo:
    - Import THẲM hàm từ services/ và core/ — không mở web server, không vòng lặp accept().
    - Mỗi vòng in "STEP <tên> <ms>" cho từng bước rồi kết thúc bằng "RUN <ms>"; xong là thoát.

Chỉ cần sửa khối STEP_SPECS dưới đây khi sang nguồn khác (tên module/hàm/argument).
"""
import argparse
import importlib
import os
import pkgutil
import sys
import time
import types

# ---------------------------------------------------------------- cấu hình --
# (tên bước in ra, module, hàm, argument gọi thử) — sửa 1 chỗ khi đổi nguồn
STEP_SPECS = [
    ("preprocess", "services.text_service", "preprocess", ("xin chào",)),
    ("classify", "services.classify_service", "classify", ("học phí một học kỳ là bao nhiêu?",)),
    ("retrieve", "services.retrieval_service", "retrieve", ("học bổng",)),
]
# Bỏ qua khi --discover (file web server / entrypoints)
SERVER_MARKERS = ("app.run(", "uvicorn.run(", "socketio.run(", ".launch(", "gradio.")
SCAN_PACKAGES = ("services", "core")


# ------------------------------------------------------------------ import --
def load_func(module_name: str, func_name: str):
    module = importlib.import_module(module_name)
    func = getattr(module, func_name, None)
    if not callable(func):
        raise SystemExit(
            f"[bench_driver] Không tìm thấy hàm '{func_name}' trong module '{module_name}'. "
            "Sửa khối STEP_SPECS cho khớp cấu trúc nguồn này."
        )
    return func


def build_callables():
    out = []
    for name, module_name, func_name, args in STEP_SPECS:
        out.append((name, load_func(module_name, func_name), tuple(args)))
    return out


# ------------------------------------------------------------------- đo --
def run_cycle(callables) -> None:
    for name, func, args in callables:
        started = time.perf_counter()
        func(*args)
        print("STEP %s %.1f" % (name, (time.perf_counter() - started) * 1000.0), flush=True)


def discover() -> None:
    """Liệt kê hàm public trong services/ + core/ để điền STEP_SPECS."""
    root = os.path.dirname(os.path.abspath(__file__))
    print("# Gợi ý STEP_SPECS — chọn hàm đo được rồi điền vào khối cấu hình:")
    found = 0
    for pkg_name in SCAN_PACKAGES:
        pkg_dir = os.path.join(root, pkg_name)
        if not os.path.isdir(pkg_dir):
            print(f"# (không có thư mục {pkg_name}/)")
            continue
        if pkg_name not in sys.modules:
            sys.path.insert(0, root)
            try:
                importlib.import_module(pkg_name)
            except Exception as exc:  # noqa: BLE001 — discovery phải luôn chạy được
                print(f"# import {pkg_name} lỗi: {exc}")
                continue
        pkg = sys.modules[pkg_name]
        for info in pkgutil.iter_modules(pkg.__path__):
            full = f"{pkg_name}.{info.name}"
            file_path = os.path.join(pkg_dir, info.name + ".py")
            if os.path.isfile(file_path):
                try:
                    head = open(file_path, "r", encoding="utf-8", errors="replace").read(2000)
                except OSError:
                    head = ""
                if any(marker in head for marker in SERVER_MARKERS):
                    print(f"# bỏ qua {full}: có vẻ là web server")
                    continue
            try:
                module = importlib.import_module(full)
            except Exception as exc:  # noqa: BLE001
                print(f"# bỏ qua {full}: import lỗi {exc}")
                continue
            for attr in sorted(dir(module)):
                if attr.startswith("_"):
                    continue
                obj = getattr(module, attr)
                if isinstance(obj, types.FunctionType) and obj.__module__ == full:
                    found += 1
                    print(f'    ("{attr}", "{full}", "{attr}", ("giá trị thử",)),')
    if not found:
        print("# Không tìm thấy hàm nào — kiểm tra lại services/ + core/ hoặc điền STEP_SPECS tay.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1, help="số vòng lặp trong 1 process")
    parser.add_argument("--discover", action="store_true", help="liệt kê hàm đo được rồi thoát")
    args = parser.parse_args()

    if args.discover:
        discover()
        return

    callables = build_callables()
    for _ in range(max(1, args.repeat)):
        started = time.perf_counter()
        run_cycle(callables)
        print("RUN %.1f" % ((time.perf_counter() - started) * 1000.0), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
