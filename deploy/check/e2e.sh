#!/usr/bin/env bash
# deploy/ 의 설정 파일이 **실제로 동작하는지** 끝까지 돌려 본다(CI · Ubuntu · Docker · systemd).
#
#   실제 DVG 바이너리(공개 릴리즈 · 체크섬 확인)
#     → nginx(deploy/nginx/*.conf 그대로 · 시험용 CA 인증서)
#     → systemd 로 띄운 예제 앱(deploy/systemd/dvg-app.service 그대로)
#   브라우저 대신 curl → nginx → systemd 로 띄운 콘솔(deploy/systemd/dvg-app-console.service) → DVG
#   DVG 사이드카(deploy/sidecar/run) → systemd 과도 유닛
#   컨테이너(examples/python/Dockerfile · Cloud Run 방식 — PORT 로 듣기)
#
# 이 시험이 증명하지 못하는 것: 실제 인증서 발급·갱신(certbot) · 클라우드 방화벽 · 실제 전화 통화.
#                             Cloud Run 자체(TLS 종단·콜드스타트·배포 중 통화) — 컨테이너까지만 본다.
#
# ⚠️ root 권한이 필요하고 시스템을 바꾼다(사용자 · /opt · /etc/systemd). **CI 러너 전용** — 운영 서버에서 돌리지 마십시오.
set -euo pipefail

DVG_VERSION="${DVG_VERSION:-v1.4.16.272}"   # 사이드카·시뮬레이터가 있는 판(1.4.16.262+). 올릴 때 여기만 바꾼다.
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
W=/tmp/dvg-e2e
PW_ADMIN=e2e-admin-pass
PW_CONSOLE=e2e-console-pass

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }
ok()   { printf '  \033[32mok\033[0m %s\n' "$*"; }

wait_for() { # wait_for <설명> <초> <명령…>
  local what="$1" secs="$2"; shift 2
  for _ in $(seq 1 "$secs"); do "$@" >/dev/null 2>&1 && return 0; sleep 1; done
  fail "$what — ${secs}초 안에 준비되지 않았습니다"
}

json() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1"; }

[ "$(id -u)" = 0 ] || fail "root 로 실행해야 합니다(sudo)"
rm -rf "$W"; mkdir -p "$W"

# ── 1. DVG 바이너리 ─────────────────────────────────────────────────────
say "1. DVG $DVG_VERSION 내려받기 + 체크섬 확인"
REL="https://github.com/OLSSOO-Inc/dvgateway-releases/releases/download/$DVG_VERSION"
curl -fsSL -o "$W/dvgateway_linux_amd64" "$REL/dvgateway_linux_amd64"
curl -fsSL -o "$W/SHA256SUMS" "$REL/SHA256SUMS"
(cd "$W" && grep ' dvgateway_linux_amd64$' SHA256SUMS | sha256sum -c -) || fail "체크섬이 맞지 않습니다"
chmod 755 "$W/dvgateway_linux_amd64"
ok "체크섬 일치"

# ── 2. 시험용 CA · 인증서 ───────────────────────────────────────────────
say "2. 시험용 CA 와 app.example.com · console.example.com 인증서"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=dvg-e2e-ca" \
  -keyout "$W/ca.key" -out "$W/ca.pem" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj "/CN=app.example.com" \
  -keyout "$W/srv.key" -out "$W/srv.csr" 2>/dev/null
printf 'subjectAltName=DNS:app.example.com,DNS:console.example.com\n' > "$W/san.ext"
openssl x509 -req -in "$W/srv.csr" -CA "$W/ca.pem" -CAkey "$W/ca.key" -CAcreateserial \
  -days 1 -extfile "$W/san.ext" -out "$W/srv.pem" 2>/dev/null
for d in app.example.com console.example.com; do
  mkdir -p "$W/le/$d"; cp "$W/srv.pem" "$W/le/$d/fullchain.pem"; cp "$W/srv.key" "$W/le/$d/privkey.pem"
done
grep -q 'app.example.com' /etc/hosts || echo '127.0.0.1 app.example.com console.example.com' >> /etc/hosts
ok "인증서 발급 · /etc/hosts"

# ── 3. nginx (deploy/nginx 그대로) ──────────────────────────────────────
say "3. nginx — deploy/nginx/*.conf 를 수정 없이 올린다"
# CI 에서는 DVG 가 같은 호스트(127.0.0.1)에서 접속한다. 운영에서는 DVG 서버의 공인 IP 를 적는다.
printf 'allow 127.0.0.1;\ndeny  all;\n' > "$W/dvg-allow.conf"
docker rm -f dvg-e2e-nginx >/dev/null 2>&1 || true
docker run -d --name dvg-e2e-nginx --network host \
  -v "$REPO/deploy/nginx/dvg-relay.conf:/etc/nginx/conf.d/dvg-relay.conf:ro" \
  -v "$REPO/deploy/nginx/dvg-app-console.conf:/etc/nginx/conf.d/dvg-app-console.conf:ro" \
  -v "$W/dvg-allow.conf:/etc/nginx/dvg-allow.conf:ro" \
  -v "$W/le:/etc/letsencrypt/live:ro" \
  nginx:1.27-alpine >/dev/null
wait_for "nginx" 20 docker exec dvg-e2e-nginx nginx -t
docker exec dvg-e2e-nginx nginx -t 2>&1 | sed 's/^/  /'
wait_for "nginx 443" 20 curl -s -o /dev/null --cacert "$W/ca.pem" https://app.example.com/
ok "nginx 기동 · 설정 문법 통과"

# ── 4. DVG ──────────────────────────────────────────────────────────────
say "4. DVG 기동(PBX 없음 · 앱 플랫폼 + 사이드카 켬 · 시험용 CA 신뢰)"
D="$W/dvg"; mkdir -p "$D"
cat > "$W/dvg.env" <<EOF
GW_API_ADDR=127.0.0.1:18080
GW_DASHBOARD_ADDR=127.0.0.1:18081
GW_MEDIA_ADDR=127.0.0.1:18092
GW_API_TLS_ENABLED=false
GW_DASHBOARD_TLS_ENABLED=false
DASHBOARD_PASSWORD=$PW_ADMIN
JWT_SECRET=e2e-jwt-secret-e2e-jwt-secret-000
PBX_TENANT_SYNC_ENABLED=false
ARI_ENABLED=false
AMI_HOST=127.0.0.1
AMI_PORT=65530
GW_SOFTPHONE_ENABLED=false
GW_MESSAGING_ENABLED=false
GW_AUDIT_LOGROTATE_ENABLED=false
GW_AUDIT_LOG_DIR=$D/audit
GW_APPS_ENABLED=true
GW_APPS_FILE=$D/apps.json
GW_APPS_USAGE_DIR=$D/apps-usage
GW_APPS_SIDECAR_ENABLED=true
GW_APPS_SIDECAR_DIR=/opt/dvgateway/apps
GW_ORDER_INTAKE_ENABLED=true
GW_ORDER_ORGS_DIR=$D/orgs
GW_ORDER_DIAG_DIR=$D/order-diag
GW_ORDER_LEARN_DIR=$D/order-learn
GW_ORDER_COST_DIR=$D/order-cost
GW_ORDER_TOKEN_PERSIST_FILE=$D/order-token.json
GW_ORDER_KEYTERMS_FILE=$D/order-keyterms.json
CDR_DIR=$D/cdr
CDR_DB_PATH=$D/cdr.db
STATS_FILE=$D/stats.json
STATS_DB_PATH=$D/stats.db
LICENSE_FILE_PATH=$D/license.json
GW_CALL_EVENTS_DIR=$D/events
GW_CALL_QUALITY_DIR=$D/quality
GW_CALL_QUALITY_MOS_DIR=$D/quality-mos
GW_CALL_SUMMARY_DIR=$D/summaries
GW_CALL_SHARE_DIR=$D/shares
GW_MOBILE_SEATS_FILE=$D/mobile-seats.json
GW_SOFTPHONE_STORE_PATH=$D/softphone.json
GW_SMS_DIR=$D/sms
GW_MINUTES_DIR=$D/minutes
GW_DIVERSION_STATE_DIR=$D/diversion-state
GW_ATTACH_DIR=$D/attach
GW_RETENTION_DIR=$D/retention
GW_METRICS_TOKENS_FILE=$D/metrics-tokens.json
SSL_CERT_FILE=$W/ca.pem
EOF
( set -a; . "$W/dvg.env"; set +a; exec "$W/dvgateway_linux_amd64" ) > "$W/dvg.log" 2>&1 &
echo $! > "$W/dvg.pid"
wait_for "DVG /health" 40 curl -sf http://127.0.0.1:18080/health
ok "DVG $(curl -s http://127.0.0.1:18080/api/v1/version | json 'd["version"]')"

TOK=$(curl -sf -X POST http://127.0.0.1:18081/login -H 'Content-Type: application/json' \
  -d "{\"password\":\"$PW_ADMIN\"}" | json 'd["token"]')
[ -n "$TOK" ] || fail "관리자 로그인 실패"
admin() { curl -sS -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' "$@"; }

register() { # register <id> <relayUrl> → $W/<id>.json
  admin -X POST http://127.0.0.1:18080/api/v1/apps -d "{\"id\":\"$1\",\"name\":\"$1\",\"relayUrl\":\"$2\",\"enabled\":true}" > "$W/$1.json"
  json 'd["credentials"]["apiKey"][:5]' < "$W/$1.json" | grep -q dvga_ || { cat "$W/$1.json"; fail "앱 등록 실패: $1"; }
}

# ── 5. 앱 — deploy/systemd/dvg-app.service 그대로 ──────────────────────
say "5. 예제 앱을 systemd 로(다른 서버에 두는 경로 — relay 는 nginx wss)"
register e2e-remote "wss://app.example.com/dvg-relay"
id dvgapp >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin dvgapp
rm -rf /opt/dvg-app; mkdir -p /opt/dvg-app /etc/dvg-app
cp "$REPO/examples/python/order_app.py" /opt/dvg-app/
python3 -m venv /opt/dvg-app/venv
/opt/dvg-app/venv/bin/pip install -q -r "$REPO/examples/python/requirements.txt"
SECRET=$(json 'd["credentials"]["signingSecret"]' < "$W/e2e-remote.json")
install -m 0640 -o root -g dvgapp /dev/null /etc/dvg-app/app.env
printf 'DVG_APP_SIGNING_SECRET=%s\nDVG_APP_HOST=127.0.0.1\nDVG_APP_PORT=19999\nDVG_APP_PATH=/relay\n' "$SECRET" > /etc/dvg-app/app.env
cp "$REPO/deploy/systemd/dvg-app.service" /etc/systemd/system/
systemctl daemon-reload
systemctl restart dvg-app
wait_for "dvg-app 19999" 30 bash -c 'exec 3<>/dev/tcp/127.0.0.1/19999'
[ "$(systemctl show -p User --value dvg-app)" = dvgapp ] || fail "dvg-app 이 dvgapp 사용자로 돌지 않습니다"
ok "dvg-app.service active · 사용자 dvgapp"

# ── 6. 콘솔 — deploy/systemd/dvg-app-console.service 그대로 ────────────
say "6. 콘솔을 systemd 로(127.0.0.1 전용 · 밖은 nginx HTTPS)"
rm -rf /opt/dvg-app-console; cp -r "$REPO/console" /opt/dvg-app-console
install -m 0640 -o root -g dvgapp /dev/null /etc/dvg-app/app.key
json 'd["credentials"]["apiKey"]' < "$W/e2e-remote.json" > /etc/dvg-app/app.key
install -m 0640 -o root -g dvgapp /dev/null /etc/dvg-app/console.env
printf 'DVG_BASE_URL=http://127.0.0.1:18080\nDVG_APP_KEY_FILE=/etc/dvg-app/app.key\nHOST=127.0.0.1\nPORT=8790\nCONSOLE_PASSWORD=%s\n' "$PW_CONSOLE" > /etc/dvg-app/console.env
cp "$REPO/deploy/systemd/dvg-app-console.service" /etc/systemd/system/
systemctl daemon-reload
systemctl restart dvg-app-console
wait_for "console 8790" 30 bash -c 'exec 3<>/dev/tcp/127.0.0.1/8790'
ok "dvg-app-console.service active"

# ── 7. 확인 ────────────────────────────────────────────────────────────
say "7. 확인 — 성공 경로"
C="https://console.example.com"
code=$(curl -s -o /dev/null -w '%{http_code}' --cacert "$W/ca.pem" "$C/")
[ "$code" = 401 ] || fail "비밀번호 없이 콘솔이 열렸습니다(HTTP $code)"
ok "비밀번호 없으면 401"
body=$(curl -sf --cacert "$W/ca.pem" -u "x:$PW_CONSOLE" "$C/api/self")
echo "$body" | grep -q '"id":"e2e-remote"' || fail "콘솔 → DVG 앱 정보 실패: $body"
KEY=$(cat /etc/dvg-app/app.key)
echo "$body" | grep -qF "$KEY" && fail "앱 키가 콘솔 응답에 실렸습니다"
ok "콘솔(HTTPS) → DVG 앱 정보 · 응답에 키 없음"

sim=$(curl -sf --cacert "$W/ca.pem" -u "x:$PW_CONSOLE" -X POST "$C/api/simulate" \
  -H 'Content-Type: application/json' \
  -d '{"utterances":["강남구 역삼동 테헤란로 123","마포구 서교동이요","착불이요","네 맞아요"]}')
outcome=$(echo "$sim" | json 'd["outcome"]')
lines=$(echo "$sim" | json 'len(d["transcript"])')
[ "$outcome" = completed ] || { echo "$sim"; fail "시뮬레이터 결말이 completed 가 아닙니다: $outcome"; }
[ "$lines" -ge 8 ] || fail "대화가 너무 짧습니다($lines줄)"
ok "시뮬레이터: DVG → nginx wss(TLS 검증) → systemd 앱 · $outcome · ${lines}줄"

say "7. 확인 — 막혀야 하는 경로(대조군)"
# (a) 인증서 이름이 안 맞는 주소 — TLS 검증이 진짜로 켜져 있는가
register e2e-badname "wss://127.0.0.1/dvg-relay"
bad=$(admin -X POST http://127.0.0.1:18080/api/v1/apps/e2e-badname/simulate -d '{"utterances":["안녕"]}')
[ "$(echo "$bad" | json 'd["outcome"]')" = app_unavailable ] || { echo "$bad"; fail "이름이 다른 인증서로도 연결됐습니다"; }
echo "$bad" | json 'd["detail"]' | grep -qi 'certificate' || { echo "$bad"; fail "실패 사유가 인증서가 아닙니다"; }
ok "인증서 이름이 다르면 연결 안 됨(app_unavailable · certificate)"
# (b) DVG 가 아닌 곳에서 relay 로 — nginx allow 목록
GW=$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}')
deny=$(docker run --rm curlimages/curl:8.10.1 -s -o /dev/null -w '%{http_code}' -k \
  --resolve "app.example.com:443:$GW" https://app.example.com/dvg-relay)
[ "$deny" = 403 ] || fail "허용 목록 밖에서 relay 에 닿았습니다(HTTP $deny)"
ok "허용 목록 밖(도커 브리지 $GW 경유)은 403"
# (c) 다른 경로는 없다
[ "$(curl -s -o /dev/null -w '%{http_code}' --cacert "$W/ca.pem" https://app.example.com/)" = 404 ] || fail "relay 서버의 다른 경로가 열려 있습니다"
ok "relay 서버의 다른 경로는 404"

# ── 8. 사이드카 ────────────────────────────────────────────────────────
say "8. 사이드카 — DVG 가 systemd 과도 유닛으로 앱을 띄운다(같은 서버 경로)"
register e2e-sidecar "ws://127.0.0.1:19998/relay"
P=/opt/dvgateway/apps/e2e-sidecar
rm -rf "$P"; mkdir -p "$P"
cp "$REPO/examples/python/order_app.py" "$P/"
python3 -m venv "$P/venv"
"$P/venv/bin/pip" install -q -r "$REPO/examples/python/requirements.txt"
install -m 0755 -o root -g root "$REPO/deploy/sidecar/run" "$P/run"
chmod -R go-w /opt/dvgateway
view=$(admin http://127.0.0.1:18080/api/v1/apps/e2e-sidecar/sidecar)
echo "$view" | json 'd["supported"]' | grep -q True || { echo "$view"; fail "사이드카를 쓸 수 없다고 합니다"; }
echo "$view" | json 'd["package"].get("problem","")' | grep -q . && { echo "$view"; fail "패키지 점검 실패"; }
admin -X PUT http://127.0.0.1:18080/api/v1/apps/e2e-sidecar/sidecar -d '{"managed":true}' > /dev/null
st=$(admin -X POST http://127.0.0.1:18080/api/v1/apps/e2e-sidecar/sidecar/start)
echo "  start: $st"
wait_for "사이드카 19998" 40 bash -c 'exec 3<>/dev/tcp/127.0.0.1/19998'
PID=$(systemctl show -p MainPID --value dvg-app-e2e-sidecar.service)
[ "$PID" -gt 0 ] || fail "사이드카 PID 없음"
U=$(ps -o user= -p "$PID" | tr -d ' ')
[ "$U" != root ] || fail "사이드카가 root 로 돕니다"
ok "dvg-app-e2e-sidecar.service · PID $PID · 사용자 $U(DynamicUser)"
# 사이드카는 DVG 의 비밀을 못 읽어야 한다(InaccessiblePaths)
ip=$(systemctl show -p InaccessiblePaths --value dvg-app-e2e-sidecar.service)
echo "$ip" | grep -q '/etc/dvgateway' || fail "InaccessiblePaths 에 /etc/dvgateway 가 없습니다: $ip"
ok "InaccessiblePaths 에 DVG·PBX 경로"
sc=$(admin -X POST http://127.0.0.1:18080/api/v1/apps/e2e-sidecar/simulate -d '{"utterances":["강남구 역삼동","마포구 서교동","선불이요","네"]}')
[ "$(echo "$sc" | json 'd["outcome"]')" = completed ] || { echo "$sc"; fail "사이드카 시뮬레이터 실패"; }
ok "사이드카 시뮬레이터 completed"
admin -X POST http://127.0.0.1:18080/api/v1/apps/e2e-sidecar/sidecar/stop > /dev/null
ok "사이드카 멈춤"

# ── 9. 컨테이너(Cloud Run 과 같은 방식) ─────────────────────────────────
say "9. 컨테이너 — examples/python/Dockerfile 을 수정 없이 빌드해 PORT 로 띄운다(Cloud Run 방식)"
register e2e-container "ws://127.0.0.1:18095/relay"
docker build -q -t dvg-e2e-app "$REPO/examples/python" > /dev/null
CSEC=$(json 'd["credentials"]["signingSecret"]' < "$W/e2e-container.json")
docker rm -f dvg-e2e-app >/dev/null 2>&1 || true
# PORT 를 8080 이 아닌 값으로 준다 — 컨테이너가 PORT 를 실제로 따르는지 확인. 비밀 끝의 줄바꿈은 버려져야 한다.
docker run -d --name dvg-e2e-app -p 127.0.0.1:18095:9090 -e PORT=9090 \
  -e "DVG_APP_SIGNING_SECRET=$CSEC"$'\n' dvg-e2e-app >/dev/null
wait_for "컨테이너 앱" 30 bash -c 'exec 3<>/dev/tcp/127.0.0.1/18095'
docker logs dvg-e2e-app 2>&1 | grep -q 'listening ws://0.0.0.0:9090/relay' || { docker logs dvg-e2e-app; fail "컨테이너가 PORT 를 따르지 않습니다"; }
[ "$(docker exec dvg-e2e-app id -u)" != 0 ] || fail "컨테이너 앱이 root 로 돕니다"
ok "PORT=9090 에서 듣고 root 가 아님"
nosig=$(curl -s -o /dev/null -w '%{http_code}' -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' http://127.0.0.1:18095/relay)
[ "$nosig" = 401 ] || fail "서명 없는 연결이 401 이 아닙니다(HTTP $nosig)"
ok "서명 없는 연결은 401"
cs=$(admin -X POST http://127.0.0.1:18080/api/v1/apps/e2e-container/simulate -d '{"utterances":["강남구 역삼동","마포구 서교동","착불이요","네"]}')
[ "$(echo "$cs" | json 'd["outcome"]')" = completed ] || { echo "$cs"; docker logs dvg-e2e-app; fail "컨테이너 앱 시뮬레이터 실패"; }
ok "컨테이너 앱 시뮬레이터 completed(비밀 끝 줄바꿈 무해)"
docker rm -f dvg-e2e-app >/dev/null

say "모두 통과"
