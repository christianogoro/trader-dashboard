#!/usr/bin/env python3
"""
Local live dashboard server.
Reads trader data fresh on every request — no sync delay.

Run: python3 app.py
Open: http://localhost:8050
"""

import json
import mimetypes
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from sync_data import sync

PORT = 8050
ROOT = Path(__file__).parent


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serves static files, but regenerates data.json live on each request."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        # Strip query params for path matching
        path = self.path.split("?")[0]

        if path == "/data.json":
            # Generate fresh data on every request
            try:
                data = sync()
                payload = json.dumps(data, indent=2, default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(payload))
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                msg = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(msg))
                self.end_headers()
                self.wfile.write(msg)
            return

        if path == "/":
            path = "/index.html"

        # Serve static files
        super().do_GET()

    def log_message(self, format, *args):
        # Suppress noisy request logs, only show errors
        if args and "200" not in str(args[1]):
            super().log_message(format, *args)


def main():
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"Dashboard live at http://localhost:{PORT}")
    print(f"Reading from {ROOT}")
    print("Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
