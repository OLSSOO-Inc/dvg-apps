"""DVG 외부 앱 최소 예제 — 음성 주문 접수(관리형 음성 레이어 v1).

DVG 가 전화·음성인식·음성합성을 맡고, 이 앱은 **텍스트로만** 대화를 이끈다.
계약: ../../docs/voice-relay-v1.md · 시작하기: ../../docs/getting-started.md

실행:
    pip install "websockets>=13"
    export DVG_SIGNING_SECRET=...        # 앱 등록 때 받은 서명 비밀
    python3 order_app.py                 # 기본 127.0.0.1:19999, 경로 /relay

DVG 가 띄우게 하려면(사이드카): /opt/dvgateway/apps/{앱 id}/run 에 이 파일을 실행하는 스크립트를 두고
대시보드 🧩 앱 → 🖥 이 서버에서 실행. 서명 비밀·포트는 DVG 가 DVG_APP_* 로 넣는다(시작하기 §2).

⚠️ 예제다 — 실제 주문 등록(업무 시스템 API 호출)은 `register_order()` 자리에 넣는다.
"""
import asyncio
import hashlib
import hmac
import json
import os
import time
from http import HTTPStatus

from websockets.asyncio.server import serve

def _env(*names, default=""):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


# DVG 사이드카(🖥 이 서버에서 실행)로 띄우면 DVG 가 DVG_APP_* 를 넣어 준다. 손으로 띄울 때는 옛 이름도 받는다.
SIGNING_SECRET = _env("DVG_APP_SIGNING_SECRET", "DVG_SIGNING_SECRET")
HOST = _env("DVG_APP_HOST", "APP_HOST", default="127.0.0.1")
PORT = int(_env("DVG_APP_PORT", "APP_PORT", default="19999"))
PATH = _env("DVG_APP_PATH", "APP_PATH", default="/relay")
MAX_SKEW = 300  # 초 — 이보다 오래된(또는 미래의) 연결은 거절한다(재생 방지)


def verify_dvg(headers, secret, now=None):
    """DVG 가 건 연결인가 — 서명·타임스탬프 확인."""
    app_id = headers.get("X-DVG-App-Id", "")
    call_id = headers.get("X-DVG-Call-Id", "")
    ts = headers.get("X-DVG-Timestamp", "")
    sig = headers.get("X-DVG-Signature", "")
    if not (secret and app_id and call_id and ts.isdigit() and sig):
        return False
    now = int(time.time()) if now is None else now
    if abs(now - int(ts)) > MAX_SKEW:
        return False
    msg = f"{app_id}\n{call_id}\n{ts}".encode()
    want = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, sig)


def process_request(connection, request):
    """WebSocket 업그레이드 전에 거른다 — 경로가 다르거나 서명이 틀리면 연결 자체를 받지 않는다."""
    if request.path != PATH:
        return connection.respond(HTTPStatus.NOT_FOUND, "not found\n")
    if not verify_dvg(request.headers, SIGNING_SECRET):
        return connection.respond(HTTPStatus.UNAUTHORIZED, "bad signature\n")
    return None


class CallEnded(Exception):
    """DVG 가 end 를 보냈다(발신자가 끊음·상한 등) — 더 보낼 것이 없다."""


async def recv(ws):
    msg = json.loads(await ws.recv())
    if msg.get("type") == "end":
        raise CallEnded(msg.get("reason", ""))
    return msg


async def ask(ws, text, choices=None):
    """질문하고 발신자 답을 받는다. 답이 없으면 빈 문자열.

    choices 를 주면 DVG 가 답을 그중 하나로 읽어 준다(초성 판정 포함). 그때는 **판정된 선택지**를 돌려준다 —
    발화 원문(「참불」 같은 오인식)이 아니라 정식 낱말이다. 🔴 초성으로 추정한 값(confirm)은 복창으로 확인한다
    (이 예제는 마지막에 전체를 복창하므로 그것으로 확인된다).
    """
    msg_out = {"type": "ask", "text": text}
    if choices:
        msg_out["choices"] = choices
    await ws.send(json.dumps(msg_out, ensure_ascii=False))
    msg = await recv(ws)
    if msg.get("type") != "prompt" or msg.get("silence"):
        return ""
    if choices:
        return msg.get("choice", "")  # 못 골랐으면 빈 값 → 다시 묻는다
    return msg.get("text", "").strip()


async def say(ws, text):
    await ws.send(json.dumps({"type": "say", "text": text}))
    await recv(ws)  # said


def register_order(order, setup):
    """⚠️ 여기에 업무 시스템 API 호출을 넣는다(앱이 직접 부른다 — DVG 는 중계하지 않는다).
    성공하면 True. 예제는 항상 성공으로 둔다."""
    if setup.get("simulated"):
        # 🔴 DVG 대시보드·시험 API 의 시험 통화 — 실제 주문을 만들지 않는다.
        print("시험 통화 — 주문 등록 건너뜀:", json.dumps(order, ensure_ascii=False), flush=True)
        return True
    print("주문 등록(예제):", json.dumps({"org": setup.get("orgId"), **order}, ensure_ascii=False), flush=True)
    return True


async def handler(ws):
    try:
        setup = await recv(ws)  # 첫 메시지는 항상 setup
        caller = setup.get("caller")  # 운영자가 «발신번호 제공» 을 켰을 때만 있다
        print("통화 시작", setup.get("callId"), "발신번호 제공" if caller else "발신번호 없음", flush=True)

        order = {}
        # (칸, 첫 질문, 다시 물을 때의 질문) — 🔴 같은 문장을 되풀이하지 않는다. 다시 물을 때는 **질문을 바꾼다**.
        for key, question, again, choices in (
                ("origin", "어디에서 보내시나요?", "제가 잘 못 들었습니다. 물건을 가지러 갈 곳을 말씀해 주세요.", None),
                ("destination", "어디로 보내시나요?", "제가 잘 못 들었습니다. 물건을 받으실 곳을 말씀해 주세요.", None),
                ("pay", "결제는 선불인가요 착불인가요?", "제가 잘 못 들었습니다. 선불이면 「선불」. 착불이면 「착불」.",
                 ["선불", "착불"])):
            answer = await ask(ws, question, choices)
            if not answer:
                answer = await ask(ws, again, choices)  # 두 번째는 바꾼 질문으로 — 그래도 없으면 사람에게
            if not answer:
                # 못 알아들으면 사람에게 넘긴다 — 번호는 DVG 가 정한다(앱이 지정할 수 없다)
                await ws.send(json.dumps({"type": "transfer"}))
                await recv(ws)
                return
            order[key] = answer

        # 복창 — 나열은 **마침표로** 끊는다(쉼표로 이으면 전화에서 한 덩어리로 들린다). 조사도 피한다.
        confirm = await ask(ws, f"출발 {order['origin']}. 도착 {order['destination']}. 결제 {order['pay']}. 맞으면 「네」라고 말씀해 주세요.")
        if not confirm.startswith(("네", "예", "맞")):
            await ws.send(json.dumps({"type": "transfer"}))
            await recv(ws)
            return

        if register_order(order, setup):
            await ws.send(json.dumps({"type": "hangup", "text": "접수되었습니다. 감사합니다."}))
        else:
            await ws.send(json.dumps({"type": "transfer"}))
        await recv(ws)
    except CallEnded as e:
        print("통화 끝:", e, flush=True)


async def main():
    if not SIGNING_SECRET:
        raise SystemExit("DVG_SIGNING_SECRET 이 비어 있습니다 — 앱 등록 때 받은 서명 비밀을 넣으세요")
    async with serve(handler, HOST, PORT, process_request=process_request):
        print(f"listening ws://{HOST}:{PORT}{PATH}", flush=True)
        await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    asyncio.run(main())
