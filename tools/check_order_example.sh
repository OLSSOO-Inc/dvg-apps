#!/usr/bin/env bash
# 주문 예제(다섯 언어 공통)가 같은 대화를 같은 결말로 끝내는지 확인한다.
#
#   DVG_SIGNING_SECRET=ci-secret tools/check_order_example.sh python3 examples/python/order_app.py
#   DVG_SIGNING_SECRET=ci-secret tools/check_order_example.sh node examples/node/order_app.mjs
#
# 인자 = 앱을 띄우는 명령. 앱은 ws://127.0.0.1:19999/relay 에서 기다려야 한다(예제 기본값).
# 앱이 떠 있는 동안 tools/local_dvg.py 로 다섯 대화를 돌리고, 끝나면 앱을 끈다.
set -euo pipefail

: "${DVG_SIGNING_SECRET:?DVG_SIGNING_SECRET 이 비어 있습니다}"
[ "$#" -ge 1 ] || { echo "사용법: $0 <앱을 띄우는 명령…>" >&2; exit 2; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
LOG="$(mktemp)"

"$@" >"$LOG" 2>&1 &
APP=$!
cleanup() { kill "$APP" 2>/dev/null || true; wait "$APP" 2>/dev/null || true; }
trap cleanup EXIT

# 앱이 포트를 열 때까지 기다린다(JVM 은 몇 초 걸린다) — 30초 안에 안 열리면 실패
for _ in $(seq 1 60); do
  if "$PY" -c 'import socket,sys; s=socket.socket(); s.settimeout(0.3); sys.exit(s.connect_ex(("127.0.0.1",19999)))'; then
    break
  fi
  if ! kill -0 "$APP" 2>/dev/null; then
    echo "앱이 시작하자마자 끝났다:" >&2; cat "$LOG" >&2; exit 1
  fi
  sleep 0.5
done

run() {
  echo "▶ $*"
  local out
  if ! out="$("$PY" "$ROOT/tools/local_dvg.py" "$@" 2>&1)"; then
    echo "$out"; echo "❌ 위 대화가 기대와 다르다" >&2; exit 1
  fi
  echo "$out" | tail -1
}

run --expect completed "강남역" "" "서초동" "착불" "네"                       # 무응답 한 번 뒤 정상
run --expect completed --file "$ROOT/tools/calls/order-narrowed.json"         # 주소 좁히기(DVG 질문을 그대로)
run --expect transferred --file "$ROOT/tools/calls/address-unknown.json"      # 주소를 두 번 못 알아들음
run --expect transferred "강남역" "서초동" "착불" "아니요"                     # 복창에서 아니요
run --chat --expect transferred "강남역" "서초동" "착불" "네"                  # 웹 채팅 — 주문 대신 사람에게
echo "✅ 다섯 대화 모두 기대한 결말"
