#!/usr/bin/env python3
from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import default_data_dir
from app.main import create_app


def find_port(host: str = "127.0.0.1", start: int = 8000, end: int = 8099) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free localhost port in {start}-{end}")


def open_browser_later(url: str) -> None:
    time.sleep(0.8)
    webbrowser.open(url)


def main() -> int:
    host = "127.0.0.1"
    port = find_port(host=host)
    app = create_app(data_dir=default_data_dir())
    url = f"http://{host}:{port}"
    threading.Thread(target=open_browser_later, args=(url,), daemon=True).start()
    print(f"Email Assist is running at {url}")
    print(f"Data directory: {default_data_dir()}")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
