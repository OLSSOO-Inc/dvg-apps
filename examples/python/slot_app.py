"""DVG 외부 앱 예제 — **시나리오 JSON 하나로 도메인을 바꾸는 슬롯 엔진**(관리형 음성 레이어 v1).

꽃 배달 · 대리운전 · 음식 배달은 «무엇을 묻고 어떻게 확인하나» 만 다르다. 이 엔진은 그 차이를 시나리오 파일에 두고
대화 규칙은 한 곳에 둔다:

- 주소 칸(`address`)  → `ask.expect:"address"` — DVG 가 시·도/구·군/동으로 풀어 준다. 여러 곳이면 **DVG 의 질문을 그대로** 다시 묻는다.
- 선택 칸(`choice`)   → `ask.choices` — DVG 가 답을 선택지 하나로 읽어 준다(초성 추정은 복창으로 확인).
- 자유 칸(`text`)     → 발화 원문.
- 🔴 **같은 질문을 되풀이하지 않는다** — 다시 물을 때는 시나리오의 `again`(다른 문장)을 쓴다. 두 번 실패하면 사람에게.
- 🔴 끝에 **전체를 복창**하고 「네」 를 받아야 등록한다. 나열은 **마침표로** 끊는다(쉼표는 전화에서 한 덩어리로 들린다).

계약: ../../docs/voice-relay-v1.md (§3-4 선택지 · §3-5 주소 · §3-6 대화 예)

실행:
    pip install -r requirements.txt
    export DVG_SIGNING_SECRET=...                       # 앱 등록 때 받은 서명 비밀
    DVG_APP_SCENARIO=scenarios/flower.json python3 slot_app.py

⚠️ 예제다 — 실제 주문 등록은 `register_order()` 자리에 넣는다.
"""
import asyncio
import json
import os
import sys

from websockets.asyncio.server import serve

# 서명 확인·환경변수는 기본 예제와 **같은 코드**를 쓴다(두 벌을 두지 않는다).
from order_app import HOST, PATH, PORT, SIGNING_SECRET, CallEnded, process_request, recv, say

MAX_ASKS_PER_SLOT = 3  # 첫 질문 + 다른 문장 한 번 + (주소가 여러 곳일 때) DVG 의 좁히는 질문


def load_scenario(path):
    with open(path, encoding="utf-8") as f:
        sc = json.load(f)
    problems = validate_scenario(sc)
    if problems:
        raise SystemExit(f"시나리오 {path}: " + " · ".join(problems))
    return sc


def validate_scenario(sc):
    """틀린 시나리오로 통화를 받지 않는다 — 시작할 때 거른다(CI 도 이 함수를 쓴다)."""
    out = []
    if not sc.get("slots"):
        out.append("slots 가 비었다")
    keys = set()
    for s in sc.get("slots", []):
        k = s.get("key", "")
        if not k or k in keys:
            out.append(f"key 가 없거나 겹친다: {k!r}")
        keys.add(k)
        if s.get("type") not in ("address", "choice", "text"):
            out.append(f"{k}: type 은 address·choice·text")
        if not s.get("ask") or not s.get("again") or s.get("ask") == s.get("again"):
            out.append(f"{k}: ask 와 again 은 둘 다 있고 **서로 달라야** 한다(같은 질문 반복 금지)")
        if s.get("type") == "choice":
            cs = s.get("choices") or []
            if not (2 <= len(cs) <= 6) or len(set(cs)) != len(cs) or any(not (1 <= len(c) <= 20) for c in cs):
                out.append(f"{k}: choices 는 2~6개 · 각 1~20자 · 중복 없음")
        if s.get("type") == "address" and len(s.get("label", "")) > 10:
            out.append(f"{k}: label 은 10자 이하")
    return out


async def send(ws, msg):
    await ws.send(json.dumps(msg, ensure_ascii=False))
    return await recv(ws)


async def ask_address(ws, slot):
    """주소 칸 — 값(복창용 한 줄)과 주소 객체. 못 얻으면 (None, None)."""
    text = slot["ask"]
    for _ in range(MAX_ASKS_PER_SLOT):
        p = await send(ws, {"type": "ask", "text": text, "expect": "address", "label": slot.get("label", "주소")})
        a = p.get("address") or {}
        st = a.get("status")
        if st == "resolved":
            line = a.get("line", "")
            if a.get("detail"):
                line += " " + a["detail"]
            return line, a
        if st == "unavailable" and p.get("text"):
            return p["text"].strip(), None  # 주소 풀이를 못 쓰는 설치 — 발화 원문으로(복창이 확인한다)
        if st == "ambiguous" and a.get("question"):
            text = a["question"]  # ⭐ DVG 의 질문을 **글자 그대로** — 그래야 다음 답(「서울이요」)을 좁혀 준다
            continue
        if text == slot["again"]:
            break  # 이미 바꾼 질문으로도 못 얻었다 — 더 묻지 않는다
        text = slot["again"]
    return None, None


async def ask_choice(ws, slot):
    for text in (slot["ask"], slot["again"]):
        p = await send(ws, {"type": "ask", "text": text, "choices": slot["choices"]})
        if p.get("choice"):
            return p["choice"]  # 초성 추정(confirm)이어도 마지막 복창이 확인한다
    return None


async def ask_text(ws, slot):
    for text in (slot["ask"], slot["again"]):
        p = await send(ws, {"type": "ask", "text": text})
        if not p.get("silence") and p.get("text", "").strip():
            return p["text"].strip()
    return None


ASKERS = {"choice": ask_choice, "text": ask_text}


def register_order(scenario, order, setup):
    """⚠️ 여기에 업무 시스템 API 호출을 넣는다. 성공하면 True."""
    if setup.get("simulated"):
        print("시험 통화 — 등록 건너뜀:", scenario["name"], json.dumps(order, ensure_ascii=False), flush=True)
        return True
    print("등록(예제):", scenario["name"], json.dumps({"org": setup.get("orgId"), **order}, ensure_ascii=False), flush=True)
    return True


def make_handler(scenario):
    async def handler(ws):
        try:
            setup = await recv(ws)
            if scenario.get("greeting"):
                await say(ws, scenario["greeting"])
            order, spoken = {}, []
            for slot in scenario["slots"]:
                if slot["type"] == "address":
                    value, addr = await ask_address(ws, slot)
                    if addr:
                        order[slot["key"] + "_address"] = addr  # 3단·좌표(앱 등록이 켰을 때) 그대로
                else:
                    value = await ASKERS[slot["type"]](ws, slot)
                if not value:
                    await send(ws, {"type": "transfer"})  # 사람에게 — 번호는 DVG 가 정한다
                    return
                order[slot["key"]] = value
                spoken.append(f"{slot['readback']} {value}.")
            confirm = await send(ws, {"type": "ask", "text": " ".join(spoken) + " 맞으면 「네」. 틀리면 「아니요」.",
                                      "choices": ["네", "아니요"]})
            if confirm.get("choice") != "네" or not register_order(scenario, order, setup):
                await send(ws, {"type": "transfer"})
                return
            await send(ws, {"type": "hangup", "text": scenario.get("done", "감사합니다.")})
        except CallEnded as e:
            print("통화 끝:", e, flush=True)
    return handler


async def main():
    path = os.environ.get("DVG_APP_SCENARIO", os.path.join(os.path.dirname(__file__), "scenarios", "flower.json"))
    scenario = load_scenario(path)
    if not SIGNING_SECRET:
        raise SystemExit("DVG_SIGNING_SECRET 이 비어 있습니다 — 앱 등록 때 받은 서명 비밀을 넣으세요")
    async with serve(make_handler(scenario), HOST, PORT, process_request=process_request):
        print(f"listening ws://{HOST}:{PORT}{PATH} scenario={scenario['name']}", flush=True)
        await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        # CI: 시나리오 검사만 한다.
        load_scenario(sys.argv[2])
        print("ok", sys.argv[2])
    else:
        asyncio.run(main())
