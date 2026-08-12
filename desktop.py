"""FlipRadar desktop wrapper.

Runs the Flask dashboard (web/app.py) on 127.0.0.1:5058 in a daemon thread
and opens it in a native pywebview window titled 'FlipRadar'.

Usage:
  python desktop.py           # open the desktop window
  python desktop.py --smoke   # boot Flask, hit /, exit 0 (no window)

Requires pywebview (desktop only): pip install pywebview
(or: pip install -r requirements-desktop.txt)
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import time
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("flipradar.desktop")

HOST = "127.0.0.1"
PORT = 5058
URL = f"http://{HOST}:{PORT}/"
WINDOW_TITLE = "FlipRadar"
BOOT_TIMEOUT_SECONDS = 15.0


def _start_flask() -> threading.Thread:
    """Start the Flask app from web.app in a daemon thread."""
    from web.app import app  # local import so --smoke failures are visible

    thread = threading.Thread(
        target=lambda: app.run(host=HOST, port=PORT, debug=False, use_reloader=False),
        name="flipradar-flask",
        daemon=True,
    )
    thread.start()
    return thread


def _wait_for_server(timeout: float = BOOT_TIMEOUT_SECONDS) -> bool:
    """Poll until the Flask port accepts connections, or time out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def smoke_test() -> int:
    """Boot Flask, request /, and exit -- no webview window."""
    _start_flask()
    if not _wait_for_server():
        log.error("Flask did not start on %s:%d within %.0fs", HOST, PORT, BOOT_TIMEOUT_SECONDS)
        return 1
    with urllib.request.urlopen(URL, timeout=10) as resp:
        status = resp.status
        body_len = len(resp.read())
    if status != 200:
        log.error("GET / returned HTTP %d", status)
        return 1
    log.info("smoke OK: GET / -> %d (%d bytes)", status, body_len)
    print("smoke OK")
    return 0


def run_desktop() -> int:
    """Open the dashboard in a native window."""
    try:
        import webview
    except ImportError:
        print(
            "pywebview is not installed. Install it with:\n"
            "  pip install pywebview\n"
            "or: pip install -r requirements-desktop.txt",
            file=sys.stderr,
        )
        return 1

    _start_flask()
    if not _wait_for_server():
        log.error("Flask did not start on %s:%d; is the port in use?", HOST, PORT)
        return 1

    webview.create_window(WINDOW_TITLE, URL)
    webview.start()  # blocks until the window is closed
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flipradar-desktop", description=__doc__)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="boot Flask, request /, exit 0 on success (no window)",
    )
    args = parser.parse_args(argv)
    return smoke_test() if args.smoke else run_desktop()


if __name__ == "__main__":
    sys.exit(main())
