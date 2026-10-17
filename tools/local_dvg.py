"""로컬 DVG 흉내 — 앱 키를 받기 **전에** 내 컴퓨터에서 앱의 대화 흐름을 돌려 본다.

DVG 처럼 서명 헤더를 붙여 앱에 WebSocket 으로 연결하고, 발신자의 말은 여러분이 적은 글로 대신합니다.
앱이 계약(docs/voice-relay-v1.md)의 **형식**을 지키는지 — 메시지 하나에 지시 하나 · 10초 안 응답 · 글자 수 ·
선택지 규칙 · 끝맺음 — 를 그 자리에서 알려 줍니다.

⚠️ 이것은 흉내입니다. 진짜 DVG 와 다른 점(그래서 마지막 확인은 반드시 운영사 DVG 의 `simulate` 로 합니다):
- 주소 풀이(`expect:"address"`)를 하지 않습니다 — `address.status:"unavailable"` 을 돌려줘 앱이 «주소 풀이를 못 쓰는 설치» 경로로 갑니다.
- 생년월일(`expect:"birth"`)·전화번호(`expect:"phone"`) 풀이를 하지 않습니다.
- 선택지는 **글자가 그대로 들어 있을 때만** 고릅니다(초성 추정 없음).
- 말투 점검은 간이판입니다(쉼표로 이은 나열만 봅니다). 정식 점검은 `simulate` 의 `toneWarning` 입니다.

실행(앱을 먼저 띄운 뒤 다른 창에서):
    pip install -r examples/python/requirements.txt
    DVG_SIGNING_SECRET=test-secret python3 tools/local_dvg.py "강남역" "" "서초동" "착불" "네"

발화를 파일로 줄 수도 있습니다(JSON 배열):
    DVG_SIGNING_SECRET=test-secret python3 tools/local_dvg.py --file my_call.json

빈 문자열("")은 «무응답» 입니다. 발화를 다 쓰고 앱이 또 물으면 «발신자가 끊음» 으로 끝납니다.
종료 코드: 0 = 위반·말투 경고 없이 끝남 · 1 = 위반 또는 말투 경고가 있었다 · 2 = 연결 실패.
"""
import argparse
import asyncio
import hashlib
import hmac
import json
import os
import re
import sys
import time

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

REPLY_TIMEOUT = 10        # 계약 §3-1 — DVG 메시지 뒤 10초 안에 지시
MAX_DIRECTIVES = 60       # 계약 §4 — 지시 60회
MAX_ERRORS = 3            # 계약 §3-2 — error 3번 넘으면 사람에게
TEXT_MAX = 500
SMS_MAX_BYTES = 80        # 계약 §3-3 — 문자 80바이트(EUC-KR 기준 한글 약 40자)
SMS_PER_CALL = 4

# 쉼표로 이은 짧은 나열(「강원, 경남, 경북」·「선불인지, 착불인지」) — 전화에서 한 덩어리로 들린다.
_RUN_TOGETHER = re.compile(r"[가-힣A-Za-z0-9]{1,8}(?:인지)?\s*,\s*[가-힣A-Za-z0-9]{1,8}(?:인지)?\s*,")
_INJI_COMMA = re.compile(r"인지\s*,")


def sign(secret, app_id, call_id, ts):
    msg = f"{app_id}\n{call_id}\n{ts}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def tone_warning(text, choices=None):
    if not text:
        return ""
    if _INJI_COMMA.search(text) or _RUN_TOGETHER.search(text):
        return "예시를 쉼표로 이었다 — 낱말마다 마침표로 끊으십시오(「선불. 착불. 어느 쪽인가요?」)"
    for a in choices or []:
        for b in choices or []:
            if a != b and re.search(re.escape(a) + r"\s*,\s*" + re.escape(b), text):
                return "선택지를 쉼표로 이었다 — 낱말마다 마침표로 끊으십시오"
    return ""


def pick_choice(text, choices):
    hits = [i for i, c in enumerate(choices) if c in text]
    if len(hits) == 1:
        return {"choice": choices[hits[0]], "choiceIndex": hits[0], "choiceSource": "exact"}
    if len(hits) > 1:
        return {"choiceAmbiguous": True}
    return {}


class Session:
    def __init__(self, utterances, direction):
        self.utter = list(utterances)
        self.turn = 0
        self.directives = 0
        self.errors = 0
        self.sms = 0
        self.violations = []
        self.tone = 0
        self.direction = direction

    def out(self, who, text):
        print(f"{who} {text}", flush=True)

    def violate(self, why):
        self.violations.append(why)
        self.out("  ❌", why)

    def warn(self, why):
        self.tone += 1
        self.out("  ⚠️", why)

    def next_turn(self, msg):
        self.turn += 1
        msg["turn"] = self.turn
        return json.dumps(msg, ensure_ascii=False)

    def check_text(self, m, required):
        t = m.get("text")
        if t is None or t == "":
            if required:
                return "text_required"
            return ""
        if not isinstance(t, str):
            return "text_required"
        if len(t) > TEXT_MAX:
            return "text_too_long"
        return ""

    def answer(self, m):
        """앱 지시 하나 → (DVG 가 보낼 메시지, 끝 결말 또는 None)."""
        kind = m.get("type")
        if kind == "say":
            code = self.check_text(m, required=True)
            if code:
                return {"type": "error", "code": code, "message": code}, None
            self.out("🤖 AI(안내)", m["text"])
            w = tone_warning(m["text"])
            if w:
                self.warn(w)
            return {"type": "said"}, None
        if kind == "ask":
            code = self.check_text(m, required=False)
            if code:
                return {"type": "error", "code": code, "message": code}, None
            choices = m.get("choices")
            expect = m.get("expect")
            if choices is not None:
                ok = (isinstance(choices, list) and 2 <= len(choices) <= 6
                      and all(isinstance(c, str) and 1 <= len(c) <= 20 for c in choices)
                      and len(set(choices)) == len(choices))
                if not ok:
                    return {"type": "error", "code": "bad_choices", "message": "choices 는 2~6개 · 각 1~20자 · 중복 없음"}, None
            if expect is not None:
                if expect not in ("address", "phone", "birth"):
                    return {"type": "error", "code": "bad_expect", "message": "expect 는 address·phone·birth"}, None
                if choices and expect != "birth":
                    return {"type": "error", "code": "bad_expect", "message": "choices 와 expect 는 함께 쓸 수 없다"}, None
            text = m.get("text") or ""
            label = "🤖 AI(질문)" + (f" [선택지 {' / '.join(choices)}]" if choices else "") + (f" [expect {expect}]" if expect else "")
            self.out(label, text or "(말없이 듣기)")
            w = tone_warning(text, choices)
            if w:
                self.warn(w)
            if not self.utter:
                self.out("📞 발신자", "(끊음 — 준비한 발화를 다 썼습니다)")
                return None, "caller_hangup"
            said = self.utter.pop(0)
            self.out("🙋 발신자", said if said else "(무응답)")
            p = {"type": "prompt", "text": said, "silence": said == "", "lowConfidence": False,
                 "spokeDuringPlayback": False, "heardVoice": said != ""}
            if choices and said:
                p.update(pick_choice(said, choices))
            if expect == "address":
                p["address"] = {"status": "unavailable", "reason": "local_dvg"}  # 흉내는 주소를 풀지 않는다
            return p, None
        if kind == "sms":
            t = m.get("text") or ""
            if not t:
                return {"type": "error", "code": "text_required", "message": "text_required"}, None
            self.sms += 1
            try:
                n = len(t.encode("euc-kr", errors="replace"))
            except LookupError:
                n = len(t.encode("utf-8"))
            if n > SMS_MAX_BYTES:
                self.violate(f"문자 {n}바이트 — 80바이트(한글 약 40자) 이하여야 합니다")
            if self.sms > SMS_PER_CALL:
                self.violate(f"문자 {self.sms}통 — 한 통화 {SMS_PER_CALL}통까지입니다")
            self.out("✉️ 문자", t)
            return {"type": "sms_result", "status": "sent"}, None
        if kind == "prepare":
            texts = m.get("texts")
            if (not isinstance(texts, list) or not 1 <= len(texts) <= 8
                    or not all(isinstance(t, str) and 1 <= len(t) <= 200 for t in texts)):
                return {"type": "error", "code": "bad_prepare", "message": "texts 는 1~8문장 · 각 200자 이하"}, None
            return {"type": "prepared", "accepted": 0}, None  # 시험 통화는 합성하지 않는다(계약 §3-13)
        if kind == "transfer":
            if "to" in m or "number" in m:
                self.violate("transfer 에 번호를 넣었다 — 번호는 지정할 수 없습니다(운영사가 정한 번호로만 갑니다)")
            note = m.get("note")
            self.out("🧑‍💼 사람에게 연결", f"메모: {note}" if note else "")
            return None, "transferred"
        if kind == "hangup":
            self.out("👋 끊기", m.get("text") or "")
            return None, "completed"
        return {"type": "error", "code": "unknown_type", "message": f"모르는 type: {kind!r}"}, None


async def run(url, app_id, secret, utterances, direction, settings):
    call_id = f"{int(time.time())}.local"
    ts = str(int(time.time()))
    headers = {
        "X-DVG-App-Id": app_id, "X-DVG-Call-Id": call_id, "X-DVG-Timestamp": ts,
        "X-DVG-Signature": sign(secret, app_id, call_id, ts), "X-DVG-Relay-Version": "1",
    }
    s = Session(utterances, direction)
    try:
        ws = await asyncio.wait_for(connect(url, additional_headers=headers), timeout=6)
    except InvalidStatus as e:
        print(f"연결 거절 — HTTP {e.response.status_code} (서명 비밀이 앱과 같은지 확인하십시오)", file=sys.stderr)
        return 2
    except (OSError, asyncio.TimeoutError) as e:
        print(f"연결 실패 — {url} ({type(e).__name__}) · 앱을 먼저 띄웠는지 확인하십시오", file=sys.stderr)
        return 2

    setup = {"type": "setup", "version": 1, "callId": call_id, "tenantId": "local", "orgId": "local-org",
             "appId": app_id, "did": "07000000000", "noticePlayed": True, "direction": direction,
             "simulated": True, "caller": "01000000000"}
    if settings:
        setup["settings"] = settings
    reason = None
    async with ws:
        await ws.send(s.next_turn(setup))
        while reason is None:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=REPLY_TIMEOUT)
            except asyncio.TimeoutError:
                s.violate(f"{REPLY_TIMEOUT}초 안에 지시가 오지 않았다 — 실통화에서는 사람에게 넘어갑니다(app_error)")
                reason = "app_error"
                break
            except ConnectionClosed:
                s.violate("앱이 연결을 먼저 닫았다 — 실통화에서는 사람에게 넘어갑니다(app_error)")
                reason = "app_error"
                break
            try:
                m = json.loads(raw)
                if not isinstance(m, dict):
                    raise ValueError("객체가 아님")
            except ValueError:
                s.violate("JSON 이 아닌 메시지를 보냈다 — 실통화에서는 사람에게 넘어갑니다(app_error)")
                reason = "app_error"
                break
            s.directives += 1
            if s.directives > MAX_DIRECTIVES:
                s.violate(f"지시 {MAX_DIRECTIVES}회를 넘었다 — 실통화에서는 사람에게 넘어갑니다(limit)")
                reason = "limit"
                break
            reply, reason = s.answer(m)
            if reply is not None:
                if reply.get("type") == "error":
                    s.errors += 1
                    s.violate(f"지시 오류 {reply['code']} — {reply.get('message', '')}")
                    if s.errors > MAX_ERRORS:
                        reason = "app_error"
                        break
                await ws.send(s.next_turn(reply))
        try:
            await ws.send(s.next_turn({"type": "end", "reason": reason}))
        except ConnectionClosed:
            pass
    print(f"\n결말: {reason} · 지시 {s.directives}회 · 위반 {len(s.violations)}건 · 말투 경고 {s.tone}건", flush=True)
    if s.utter and reason in ("completed", "transferred"):
        print(f"(쓰지 않은 발화 {len(s.utter)}개)", flush=True)
    return 1 if s.violations or s.tone else 0


def main():
    ap = argparse.ArgumentParser(description="로컬 DVG 흉내 — 앱의 대화 흐름 점검")
    ap.add_argument("utterances", nargs="*", help="발신자 발화(순서대로) · 빈 문자열은 무응답")
    ap.add_argument("--file", help="발화 JSON 배열 파일")
    ap.add_argument("--url", default=os.environ.get("DVG_LOCAL_URL", "ws://127.0.0.1:19999/relay"))
    ap.add_argument("--app-id", default=os.environ.get("DVG_APP_ID", "local-app"))
    ap.add_argument("--outbound", action="store_true", help="DVG 가 건 통화(setup.direction=outbound)로 흉내")
    ap.add_argument("--settings", help='설치별 설정 JSON(예: \'{"shopName":"꽃마을"}\')')
    a = ap.parse_args()
    secret = os.environ.get("DVG_SIGNING_SECRET") or os.environ.get("DVG_APP_SIGNING_SECRET")
    if not secret:
        raise SystemExit("DVG_SIGNING_SECRET 이 비어 있습니다 — 앱에 넣은 것과 같은 값을 넣으십시오")
    utter = list(a.utterances)
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            utter = json.load(f)
        if not isinstance(utter, list) or not all(isinstance(u, str) for u in utter):
            raise SystemExit("--file 은 문자열 배열이어야 합니다")
    settings = json.loads(a.settings) if a.settings else None
    sys.exit(asyncio.run(run(a.url, a.app_id, secret, utter, "outbound" if a.outbound else "inbound", settings)))


if __name__ == "__main__":
    main()
