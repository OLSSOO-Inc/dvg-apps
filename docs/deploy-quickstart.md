# 실서버 설치 퀵 가이드 — 앱 · 콘솔

앱을 실제 서버에 올리는 순서입니다. 여기 나오는 설정 파일은 전부 [`deploy/`](../deploy/) 에 있고,
**CI 가 매번 실제 DVG 릴리즈·nginx·systemd 로 그 파일들을 그대로 돌려 봅니다**([`deploy/check/e2e.sh`](../deploy/check/e2e.sh)).

> 먼저 할 일: DVG 운영사에게 **앱 등록**을 받으십시오 — 앱 id · **앱 키**(`dvga_…`) · **서명 비밀**을 받습니다(한 번만 보여 줍니다).
> 운영사가 할 일(기능 켜기 · 등록 · 회사에 설치)은 운영사 문서에 있습니다.

아래 명령은 **이 저장소를 받은 폴더에서** 실행합니다:

```bash
git clone https://github.com/OLSSOO-Inc/dvg-apps.git
```

```bash
cd dvg-apps
```

## 0. 어느 경로인가

| | A. 같은 서버(사이드카) | B. 다른 서버 | B2. 서버 없이(Cloud Run) |
|---|---|---|---|
| 앱이 사는 곳 | DVG 서버 안(DVG 가 띄움) | 여러분의 서버 | Google Cloud Run 컨테이너 |
| relay 주소 | `ws://127.0.0.1:19998/relay` | `wss://app.example.com/dvg-relay` | `wss://dvg-app-….run.app/relay` |
| 필요한 것 | DVG 서버 셸 권한 | 도메인 · 인증서 · nginx | GCP 프로젝트(인증서·TLS 는 Cloud Run 이 맡는다) |
| 누가 앱을 살려 두나 | DVG(systemd 과도 유닛) | 여러분(systemd) | Cloud Run |

**연결 방향을 기억하십시오: DVG 가 앱에 접속합니다.** 다른 서버 경로에서는 앱 서버가 **DVG 서버의 IP 에서 오는 443 접속**을 받아야 합니다.
콘솔은 반대로 앱 서버에서 **DVG 의 HTTPS 주소로 나갑니다.**

```
발신자 ─전화─▶ DVG ──wss──▶ nginx(443) ──▶ 앱(127.0.0.1:19999)
                 ▲
브라우저 ─https─▶ nginx(443) ──▶ 콘솔(127.0.0.1:8790) ──https──┘
```

## A. 같은 서버 — 사이드카

DVG 운영사에게 사이드카를 켜 달라고 하십시오(`GW_APPS_SIDECAR_ENABLED=true`). 그다음 DVG 서버에서:

1. 앱 폴더를 만들고 실행 파일을 둡니다. 위치와 이름(`run`)은 고정입니다. Debian·Ubuntu 는 `python3-venv` 가 필요합니다.

   ```bash
   sudo apt install -y python3-venv
   ```


   ```bash
   sudo mkdir -p /opt/dvgateway/apps/<앱 id>
   ```

   ```bash
   sudo cp examples/python/order_app.py /opt/dvgateway/apps/<앱 id>/
   ```

   ```bash
   sudo python3 -m venv /opt/dvgateway/apps/<앱 id>/venv
   ```

   ```bash
   sudo /opt/dvgateway/apps/<앱 id>/venv/bin/pip install -r examples/python/requirements.txt
   ```

   ```bash
   sudo install -m 0755 -o root -g root deploy/sidecar/run /opt/dvgateway/apps/<앱 id>/run
   ```

2. DVG 대시보드 🧩 앱 → 그 앱 → 🖥 사이드카에서 **관리함**을 켜고 **시작**합니다.
   서명 비밀·포트는 DVG 가 넣어 줍니다(`DVG_APP_*` 환경변수) — 파일에 적지 않습니다.
3. 🧪 시험으로 확인합니다(아래 D).

⚠️ `run` 은 root 소유 · 755 여야 합니다. 그룹이나 다른 사용자가 쓸 수 있으면 DVG 가 띄우지 않습니다.
앱은 **일회용 사용자**로 돌고 DVG·PBX 디렉터리를 읽을 수 없습니다.

## B. 다른 서버 — nginx + systemd

Ubuntu 22.04+ 기준입니다. `app.example.com` 을 여러분의 도메인으로 바꾸십시오.

1. **인증서** — 도메인이 이 서버를 가리키게 한 뒤:

   ```bash
   sudo apt install -y nginx certbot python3-certbot-nginx python3-venv
   ```

   ```bash
   sudo certbot certonly --nginx -d app.example.com
   ```

2. **앱** — 사용자 · 폴더 · 가상환경:

   ```bash
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin dvgapp
   ```

   ```bash
   sudo mkdir -p /opt/dvg-app /etc/dvg-app
   ```

   ```bash
   sudo cp examples/python/order_app.py /opt/dvg-app/
   ```

   ```bash
   sudo python3 -m venv /opt/dvg-app/venv
   ```

   ```bash
   sudo /opt/dvg-app/venv/bin/pip install -r examples/python/requirements.txt
   ```

3. **서명 비밀** — 편집기로 `/etc/dvg-app/app.env` 를 만들고 네 줄을 넣습니다(서명 비밀은 받은 값으로):

   ```bash
   sudo install -m 0640 -o root -g dvgapp /dev/null /etc/dvg-app/app.env
   ```

   ```bash
   sudo nano /etc/dvg-app/app.env
   ```

   ```
   DVG_APP_SIGNING_SECRET=받은_서명_비밀
   DVG_APP_HOST=127.0.0.1
   DVG_APP_PORT=19999
   DVG_APP_PATH=/relay
   ```

4. **서비스로 등록**:

   ```bash
   sudo cp deploy/systemd/dvg-app.service /etc/systemd/system/
   ```

   ```bash
   sudo systemctl daemon-reload
   ```

   ```bash
   sudo systemctl enable --now dvg-app
   ```

5. **nginx** — relay 설정과 **DVG IP 허용 목록**:

   ```bash
   sudo cp deploy/nginx/dvg-relay.conf /etc/nginx/conf.d/
   ```

   ```bash
   sudo cp deploy/nginx/dvg-allow.conf.example /etc/nginx/dvg-allow.conf
   ```

   `/etc/nginx/dvg-allow.conf` 의 `203.0.113.10` 을 **DVG 서버의 공인 IP**로 바꾸고(운영사에게 받으십시오),
   `dvg-relay.conf` 의 `app.example.com` 세 곳을 바꾼 뒤:

   ```bash
   sudo nginx -t
   ```

   ```bash
   sudo systemctl reload nginx
   ```

6. **방화벽** — 443 을 **DVG 서버 IP 에만** 여십시오(클라우드 보안그룹 포함). nginx 허용 목록과 방화벽은 **둘 다** 둡니다.
7. 운영사에게 relay 주소 `wss://app.example.com/dvg-relay` 를 알려 앱 등록에 적게 합니다.

## B2. 서버 없이 — Cloud Run

서버를 두지 않고 Google Cloud Run 에 앱 컨테이너를 올립니다. 인증서와 TLS 는 Cloud Run 이 맡으므로 nginx·certbot 이 필요 없습니다.
컨테이너 파일은 [`examples/python/Dockerfile`](../examples/python/Dockerfile) 입니다(다른 언어도 같은 방식 — **`PORT` 로 듣고, 모든 주소에서 듣는다**).

명령은 `gcloud` 가 설치된 컴퓨터나 Cloud Shell 에서, 이 저장소 폴더에서 실행합니다.

1. **쓸 서비스를 켭니다**:

   ```bash
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
   ```

2. **서명 비밀을 비밀 관리자에 넣습니다** — 비밀을 명령줄에 적지 않도록 파일로 넘기고 바로 지웁니다.

   ```bash
   (umask 077; cat > "$HOME/dvg-secret.txt")
   ```

   받은 서명 비밀을 붙여 넣고 Enter · Ctrl+D 를 누른 뒤:

   ```bash
   gcloud secrets create dvg-signing-secret --data-file="$HOME/dvg-secret.txt"
   ```

   ```bash
   rm "$HOME/dvg-secret.txt"
   ```

   끝에 붙은 줄바꿈은 앱이 버립니다(그대로 두면 모든 서명이 어긋나므로 예제 앱이 앞뒤 공백을 지웁니다).

3. **Cloud Run 이 그 비밀을 읽게 합니다**(기본 서비스 계정 기준 — 다른 서비스 계정을 쓰면 그 계정으로):

   ```bash
   PN=$(gcloud projects describe "$(gcloud config get-value project)" --format='value(projectNumber)')
   ```

   ```bash
   gcloud secrets add-iam-policy-binding dvg-signing-secret --member="serviceAccount:${PN:?project number is empty}-compute@developer.gserviceaccount.com" --role=roles/secretmanager.secretAccessor
   ```

4. **배포합니다**(처음이면 저장소를 만들지 묻습니다 — `Y`):

   ```bash
   gcloud run deploy dvg-app --source examples/python --region asia-northeast3 --allow-unauthenticated --timeout 900 --min-instances 1 --set-secrets DVG_APP_SIGNING_SECRET=dvg-signing-secret:latest
   ```

   | 옵션 | 왜 |
   |---|---|
   | `--allow-unauthenticated` | DVG 는 Google 인증을 하지 않습니다. **인증은 앱의 서명 확인**이 합니다(서명 없는 연결은 401) |
   | `--timeout 900` | 통화 한 건 동안 연결이 이어집니다(DVG 상한 10분). 기본 5분이면 긴 통화가 끊깁니다 |
   | `--min-instances 1` | DVG 는 연결을 **5초** 안에 맺지 못하면 사람에게 넘깁니다. 인스턴스가 0 이면 첫 통화가 콜드스타트에 걸릴 수 있습니다(대기 인스턴스 요금이 듭니다) |
   | `asia-northeast3` | 서울. DVG 가 한국에 있으면 턴마다 왕복 시간이 줄어듭니다 |

5. **relay 주소를 확인합니다**:

   ```bash
   gcloud run services describe dvg-app --region asia-northeast3 --format='value(status.url)'
   ```

   나온 `https://dvg-app-….run.app` 의 `https://` 를 `wss://` 로 바꾸고 끝에 `/relay` 를 붙인 것이 relay 주소입니다. 운영사에게 알려 앱 등록에 적게 합니다.

⚠️ **IP 제한이 없습니다** — nginx 경로와 달리 누구나 이 주소에 연결을 시도할 수 있고, **서명 확인이 유일한 문**입니다. IP 로도 막으려면 외부 부하분산기 + Cloud Armor 를 앞에 둡니다.
⚠️ 조직 정책이 `--allow-unauthenticated` 를 막는 프로젝트가 있습니다(「도메인 제한 공유」). 그때는 배포가 실패하니 관리자에게 예외를 받으십시오.
⚠️ **새 판 배포 중에 진행 중이던 통화가 어떻게 되는지는 확인하지 않았습니다.** 통화가 적은 시간에 배포하십시오.

## C. 콘솔 — 사용량 · 시뮬레이터 화면

앱 서버(B) 또는 여러분의 다른 서버에 둡니다. **Node.js 20+** 가 필요합니다.

1. 파일과 **앱 키**:

   ```bash
   sudo cp -r console /opt/dvg-app-console
   ```

   ```bash
   sudo install -m 0640 -o root -g dvgapp /dev/null /etc/dvg-app/app.key
   ```

   ```bash
   sudo nano /etc/dvg-app/app.key
   ```

   `dvga_…` 앱 키 **한 줄만** 넣습니다.

2. 설정 — `/etc/dvg-app/console.env`:

   ```bash
   sudo install -m 0640 -o root -g dvgapp /dev/null /etc/dvg-app/console.env
   ```

   ```bash
   sudo nano /etc/dvg-app/console.env
   ```

   ```
   DVG_BASE_URL=https://dvg.example.com:8443
   DVG_APP_KEY_FILE=/etc/dvg-app/app.key
   HOST=127.0.0.1
   PORT=8790
   CONSOLE_PASSWORD=긴_비밀번호
   ```

   🔴 **`CONSOLE_PASSWORD` 를 반드시 정하십시오.** 콘솔은 127.0.0.1 로 떠 있을 때는 비밀번호를 요구하지 않는데,
   다음 단계의 nginx 가 그것을 밖으로 엽니다. `DVG_BASE_URL` 은 **https** 로(평문이면 앱 키가 암호화 없이 오갑니다).

3. 서비스와 nginx(`console.example.com` 세 곳을 바꾸고, 인증서는 1단계처럼 certbot 으로):

   ```bash
   sudo cp deploy/systemd/dvg-app-console.service /etc/systemd/system/
   ```

   ```bash
   sudo systemctl daemon-reload
   ```

   ```bash
   sudo systemctl enable --now dvg-app-console
   ```

   ```bash
   sudo cp deploy/nginx/dvg-app-console.conf /etc/nginx/conf.d/
   ```

   ```bash
   sudo nginx -t
   ```

   ```bash
   sudo systemctl reload nginx
   ```

**nginx 없이 보고 싶다면** SSH 터널이 가장 단순하고 안전합니다(콘솔 서버에 nginx·인증서가 필요 없습니다):

```bash
ssh -L 8790:127.0.0.1:8790 사용자@앱서버
```

그다음 내 컴퓨터에서 `http://127.0.0.1:8790` 을 엽니다.

## D. 확인 — 이 순서로

| 단계 | 어떻게 | 이렇게 보이면 성공 |
|---|---|---|
| 1 | `systemctl status dvg-app` | `active (running)` |
| 2 | 콘솔 🧩 앱 정보 | 앱 이름 · 켜짐 · 설치된 회사 수 |
| 3 | 콘솔 🧪 시험 실행 | 결말 **앱이 끝냄** `completed` 와 대화 기록 |
| 4 | 실제 전화 | 앱이 말한 질문이 들린다 |
| 5 | 콘솔 📊 사용량 | 방금 통화가 한 통 늘어 있다(시험은 세지 않는다) |

**3에서 막히면**

- `앱 연결 실패` · `certificate` → relay 도메인과 인증서 이름이 다릅니다(`app.example.com` 오타 · 인증서 미발급).
- `앱 연결 실패` · `403` 또는 연결 시간 초과 → DVG 서버 IP 가 `dvg-allow.conf` 또는 방화벽에 없습니다.
- `앱 오류·응답 없음` → 서명 비밀이 틀렸거나(키를 다시 받았다면 `app.env` 도 바꾸십시오) 앱이 계약을 어겼습니다(`journalctl -u dvg-app`).

## 무엇이 검증돼 있나

| 항목 | 상태 |
|---|---|
| nginx 설정 두 개 · systemd 유닛 두 개 · 사이드카 `run` | ✅ CI 가 **수정 없이** 실제 DVG 릴리즈와 함께 돌려 봄(`deploy/check/e2e.sh`) |
| DVG → nginx `wss` → 앱(인증서 검증 포함) · 콘솔 HTTPS · 비밀번호 | ✅ CI |
| 인증서 이름이 틀리면 연결 거부 · 허용 목록 밖은 403 | ✅ CI(대조군) |
| 사이드카: 일회용 사용자로 실행 · DVG 디렉터리 차단 설정 | ✅ CI |
| 컨테이너(`examples/python/Dockerfile`): `PORT` 로 듣기 · root 아님 · 서명 없는 연결 401 · 실제 DVG 와 대화 완주 | ✅ CI(Cloud Run 과 같은 방식으로 띄운 컨테이너) |
| Cloud Run 자체: 배포 명령 · TLS 종단 · 콜드스타트 시간 · 배포 중 통화 | ⚠️ **실제 Cloud Run 에 올려 보지 않았습니다**(GCP 계정 필요) — 명령은 인자 전개까지만 확인했습니다 |
| certbot 발급·갱신 · 클라우드 방화벽 · **실제 전화 통화** | ⚠️ CI 로는 확인할 수 없습니다 — 여러분 서버에서 D 표 4번으로 확인하십시오 |

⭐ AWS Lambda(API Gateway WebSocket)도 원리상 가능하지만 메시지마다 함수가 따로 불려 **통화 상태를 밖(DB)에 둬야 하고** 예제 앱을 그대로 쓸 수 없어 여기서는 다루지 않습니다.
