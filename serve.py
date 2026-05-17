"""
serve.py — Local server for the Places Dashboard.

Usage:
    python serve.py

Then open http://localhost:8080 in your browser.
The dashboard will read links_data.json live on every refresh.
"""

import http.server
import socketserver
import webbrowser
import os

PORT = 8080
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence request logs

print(f"Dashboard running at http://localhost:{PORT}")
print("Press Ctrl+C to stop.\n")
webbrowser.open(f"http://localhost:{PORT}/dashboard.html")

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
