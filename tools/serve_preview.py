"""本地预览服务：等价于线上 nginx 的 `error_page 404 /404.html`。

Python 内置 http.server 只会返回自带的 "Error response" 页面，
不会使用 Hugo 生成的 public/404.html，本地预览 404 时看起来像没生效。
这里补上兜底，让本地行为与生产一致。

用法: python tools/serve_preview.py [端口]   默认 8080
"""

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public"
)


class HugoHandler(SimpleHTTPRequestHandler):
    """路径不存在时返回 public/404.html（HTTP 404），与 nginx error_page 一致。"""

    not_found = os.path.join(ROOT, "404.html")

    def send_error(self, code, message=None, explain=None):
        if code == 404 and os.path.isfile(self.not_found):
            try:
                with open(self.not_found, "rb") as fh:
                    body = fh.read()
            except OSError:
                body = None
            if body is not None:
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
                return
        super().send_error(code, message, explain)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    if not os.path.isdir(ROOT):
        sys.exit("找不到构建产物目录: %s（先跑 hugo 构建）" % ROOT)

    handler = partial(HugoHandler, directory=ROOT)
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    srv.daemon_threads = True
    print("预览服务: http://localhost:%d  ->  %s" % (port, ROOT))
    print("404 兜底: %s" % ("已启用" if os.path.isfile(HugoHandler.not_found) else "未找到 404.html"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
