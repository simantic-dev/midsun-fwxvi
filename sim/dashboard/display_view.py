#!/usr/bin/env python3
"""Show the steering display live in a browser while the car runs.

    python3 sim/dashboard/display_view.py steering-frames [port]

`sim --display-dir steering-frames` writes one PNG per screen change; this serves a page that
shows the newest one, refreshed five times a second, at http://localhost:<port>/ (default 8765).
Standard library only.
"""
import http.server
import os
import sys

DIR = sys.argv[1] if len(sys.argv) > 1 else "steering-frames"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765

PAGE = b"""<!doctype html><meta charset=utf-8><title>Steering display (simulated)</title>
<body style="margin:0;background:#111;color:#ccc;font:14px sans-serif;display:grid;place-items:center;height:100vh">
<div><img id=f style="image-rendering:pixelated;width:min(96vw,960px)"><p id=t></p></div>
<script>
const f=document.getElementById('f'),t=document.getElementById('t');
setInterval(async()=>{const r=await fetch('/latest.png',{cache:'no-store'});if(!r.ok)return;
f.src=URL.createObjectURL(await r.blob());t.textContent=r.headers.get('X-Frame')||''},200);
</script>"""


def newest():
    try:
        names = [n for n in os.listdir(DIR) if n.endswith(".png")]
    except FileNotFoundError:
        return None
    return max(names, default=None)  # names carry a zero-padded frame number


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.reply(200, "text/html", PAGE)
            return
        name = newest() if self.path == "/latest.png" else None
        if not name:
            self.reply(404, "text/plain", b"no frame yet")
            return
        with open(os.path.join(DIR, name), "rb") as f:
            self.reply(200, "image/png", f.read(), {"X-Frame": name})

    def reply(self, code, kind, body, headers=()):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        for k, v in dict(headers).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"steering display: http://localhost:{PORT}/  (frames from {DIR})")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
