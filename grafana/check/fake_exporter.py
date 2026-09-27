"""가짜 DVG — testdata/sample-metrics.txt 를 /api/v1/metrics 로 내준다(CI 전용).

실제 DVG 처럼 **Bearer 토큰이 맞을 때만** 200 이고 아니면 401 이다. 토큰은 DVG_TOKEN_FILE 에서 읽는다.
표본은 DVG 1.4.16.271 의 지표 코드로 **생성한 실제 출력**이다(테넌트 범위 · 가짜 id).
"""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "testdata", "sample-metrics.txt")
TOKEN = open(os.environ["DVG_TOKEN_FILE"], encoding="utf-8").read().strip()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/v1/metrics":
            self.send_response(404)
            self.end_headers()
            return
        if self.headers.get("Authorization", "") != "Bearer " + TOKEN:
            self.send_response(401)
            self.end_headers()
            return
        body = open(SAMPLE, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(os.environ.get("PORT", "9998"))), H).serve_forever()
