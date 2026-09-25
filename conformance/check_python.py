"""서명 시험 벡터 — 파이썬 예제의 verify_dvg 가 DVG 와 같은 값을 받아들이는가."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples", "python"))
import order_app  # noqa: E402

v = json.load(open(os.path.join(os.path.dirname(__file__), "vector.json")))
h = {"X-DVG-App-Id": v["appId"], "X-DVG-Call-Id": v["callId"],
     "X-DVG-Timestamp": str(v["timestamp"]), "X-DVG-Signature": v["signature"]}
ts = v["timestamp"]
checks = [
    ("벡터를 받아들인다", order_app.verify_dvg(h, v["signingSecret"], now=ts), True),
    ("틀린 서명은 거절", order_app.verify_dvg({**h, "X-DVG-Signature": "0" * 64}, v["signingSecret"], now=ts), False),
    ("틀린 비밀은 거절", order_app.verify_dvg(h, "other-secret", now=ts), False),
    ("300초 넘게 지난 연결은 거절", order_app.verify_dvg(h, v["signingSecret"], now=ts + 301), False),
    ("300초 이내는 받는다", order_app.verify_dvg(h, v["signingSecret"], now=ts + 300), True),
]
bad = [name for name, got, want in checks if got != want]
for name, got, want in checks:
    print(("ok  " if got == want else "FAIL"), name)
sys.exit(1 if bad else 0)
