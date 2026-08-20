#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rescene 模型聚合 · 本地 CORS 代理 + 静态服务器（零依赖）

用途：
  1) 以 http://127.0.0.1:8000 提供 index.html
  2) 转发 /proxy/{kilo|zen}/... 到对应 AI 网关，绕过浏览器 CORS 限制，
     并把流式(SSE)响应原样透传回来。

用法：
  python3 server.py            # 默认端口 8000
  python3 server.py 9000       # 自定义端口

然后浏览器打开 http://127.0.0.1:8000 ，在页面「设置」里选择「本地代理」即可。
"""
import sys, os, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import Request, ProxyHandler, build_opener
import http.client, ssl

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

# 允许代理的上游网关（白名单，防止被当作开放代理滥用）
UPSTREAM = {
    "kilo": "api.kilo.ai",
    "zen": "opencode.ai",
}
UPSTREAM_PREFIX = {
    "kilo": "/api/gateway/v1",
    "zen": "/zen/v1",
}

# 需要透传给上游的请求头（白名单）
PASS_HEADERS = {"content-type", "authorization", "accept", "user-agent"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ResceneProxy/1.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    # ---------- CORS ----------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Upstream")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ---------- 静态文件 ----------
    def _serve_static(self):
        path = urlparse(self.path).path
        if path in ("/", ""):
            path = "/index.html"
        fp = os.path.normpath(os.path.join(ROOT, path.lstrip("/")))
        if not fp.startswith(ROOT) or not os.path.isfile(fp):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        ext = os.path.splitext(fp)[1].lower()
        ctype = {"html": "text/html; charset=utf-8", "js": "application/javascript",
                 "css": "text/css", "json": "application/json"}.get(ext[1:], "application/octet-stream")
        data = open(fp, "rb").read()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---------- 代理转发 ----------
    def _proxy(self, method):
        # 期望路径：/proxy/{kilo|zen}/{rest}
        parts = self.path.split("/")
        if len(parts) < 4 or parts[1] != "proxy":
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"bad proxy path")
            return
        provider = parts[2]
        rest = "/" + "/".join(parts[3:])
        if provider not in UPSTREAM:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"unknown provider")
            return
        host = UPSTREAM[provider]
        full_path = UPSTREAM_PREFIX[provider] + rest
        if self.path.find("?") >= 0:
            full_path += "?" + urlparse(self.path).query
        if not full_path:
            full_path = "/"

        # 读取请求体
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else None

        # 透传请求头
        fwd = {}
        for k, v in self.headers.items():
            if k.lower() in PASS_HEADERS:
                fwd[k] = v
        if method in ("POST", "PUT") and body:
            fwd["Content-Length"] = str(len(body))
        if not any(k.lower() == "accept" for k in fwd):
            fwd["Accept"] = "text/event-stream, application/json"

        # 建立上游连接（urllib 自动遵循系统 HTTPS_PROXY 环境变量，同时兼容直连）
        url = "https://" + host + full_path
        try:
            opener = build_opener(ProxyHandler())
            req = Request(url, data=body, headers=fwd, method=method)
            resp = opener.open(req, timeout=120)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "upstream error", "detail": str(e)}).encode())
            return

        status = resp.getcode() or 200
        ctype = resp.headers.get("Content-Type", "application/octet-stream")
        te = resp.headers.get("Transfer-Encoding", "").lower()

        # 响应头
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Cache-Control", "no-cache")

        # 流式：透传上游，逐块写并 flush（保证 SSE 实时）
        if ctype.startswith("text/event-stream") or te == "chunked":
            for key, val in resp.headers.items():
                if key.lower() in ("transfer-encoding", "content-length"):
                    continue
                # 已经发送过的头部不再重复
                low = key.lower()
                if low in ("content-type", "access-control-allow-origin",
                           "x-accel-buffering", "cache-control", "connection"):
                    continue
                self.send_header(key, val)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                while True:
                    chunk = resp.read(1024)
                    if not chunk:
                        break
                    self.wfile.write(("%x\r\n" % len(chunk)).encode() + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            data = resp.read()
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        resp.close()

    def do_GET(self):
        if self.path.startswith("/proxy/"):
            self._proxy("GET")
        else:
            self._serve_static()

    def do_POST(self):
        if self.path.startswith("/proxy/"):
            self._proxy("POST")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")


if __name__ == "__main__":
    print("=" * 56)
    print("  Rescene 模型聚合 · 本地代理服务器")
    print("  打开浏览器访问:  http://127.0.0.1:%d" % PORT)
    print("  页面「设置」里选择「本地代理」即可绕过 CORS")
    print("  按 Ctrl+C 退出")
    print("=" * 56)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")