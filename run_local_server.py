#!/usr/bin/env python3
"""
Minimal local server for Agent From Scratch.

Serves:
- /, /polis, /challenges -> index.html
- /favicon.ico -> favicon
- /prism.bundle.min.js -> Prism JavaScript bundle
- Static files from the project directory
"""

from __future__ import annotations

import argparse
import mimetypes
import pathlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
INDEX_FILE = PROJECT_ROOT / "index.html"
FAVICON_FILE = PROJECT_ROOT / "favicon.ico"
PRISM_BUNDLE_FILE = PROJECT_ROOT / "prism.bundle.min.js"
APP_ROUTES = {"/", "/polis", "/challenges"}


class LocalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self) -> None:
        route_path = urlsplit(self.path).path
        if route_path == "/favicon.ico":
            self._serve_file(FAVICON_FILE)
            return
        if route_path in {"/prism.bundle.min.js", "/vendor/prism/prism.bundle.min.js"}:
            self._serve_file(PRISM_BUNDLE_FILE)
            return
        if self._should_serve_index(route_path):
            self._serve_index()
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        route_path = urlsplit(self.path).path
        if route_path == "/favicon.ico":
            self._serve_file(FAVICON_FILE, head_only=True)
            return
        if route_path in {"/prism.bundle.min.js", "/vendor/prism/prism.bundle.min.js"}:
            self._serve_file(PRISM_BUNDLE_FILE, head_only=True)
            return
        if self._should_serve_index(route_path):
            self._serve_index(head_only=True)
            return
        super().do_HEAD()

    def _should_serve_index(self, route_path: str) -> bool:
        if route_path in APP_ROUTES or route_path == "/index.html":
            return True

        # Let missing asset requests return 404 rather than falling back to HTML.
        if pathlib.PurePosixPath(route_path).suffix:
            return False

        static_target = pathlib.Path(self.translate_path(route_path))
        return not static_target.exists()

    def _serve_index(self, head_only: bool = False) -> None:
        self._serve_file(INDEX_FILE, head_only=head_only, fallback_error="Missing index.html")

    def _serve_file(self, file_path: pathlib.Path, head_only: bool = False, fallback_error: str = "File not found") -> None:
        if not file_path.exists():
            status = 500 if "Missing index.html" in fallback_error else 404
            self.send_error(status, fallback_error)
            return

        body = file_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local server for Agent From Scratch.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), LocalHandler)
    print(f"Serving {PROJECT_ROOT} on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
