# 계약 변경 이력

필드 추가는 버전을 올리지 않습니다(모르는 필드는 무시). **기존 앱을 깨뜨리는 변경만** 버전을 올립니다.

## DVG 가 거는 통화 `setup.direction` (DVG 1.4.16.292+)

- DVG 가 상대에게 **먼저 걸고** 받으면 앱에 넘기는 통화가 생겼다. 앱이 받는 메시지는 수신 통화와 같고 `setup.direction` 만 `"outbound"` 다(수신은 `"inbound"` · 키가 없으면 구버전 = 수신).
- `caller` 는 발신 통화에서도 **상대 번호**(설치의 발신번호 제공이 켜졌을 때만).
- 첫인사를 바꾸고 싶은 앱(「전화 받아 주셔서 고마워요」)만 이 값을 보면 된다 — 모르는 앱은 그대로 동작한다.

## 긴 듣기 `ask.listenSeconds` (DVG 1.4.16.291+)

- `ask` 에 `listenSeconds`(5~90)를 실으면 DVG 가 그 시간 동안 **쉼으로 끊지 않고** 발신자의 말을 모아 한 번에 준다 — 「생각나는 이름을 말씀해 주세요」처럼 생각하며 쉬는 질문용(계약 §3-7).
- 적용했으면 `prompt.listenSeconds` 에 같은 값이 돌아온다. **키가 없으면 적용되지 않은 것**(구버전 DVG) — 답이 잘렸을 수 있다.
- `choices`·`expect` 와 함께 쓰거나 범위 밖이면 `error bad_listen_seconds`.
- 필드 추가라 버전(1)은 그대로다 — 모르는 앱은 이 필드를 보내지 않으므로 동작이 바뀌지 않는다.

## 예제: 연결이 닫히면 통화가 끝난 것으로

- 파이썬·Go 예제가 **`end` 없이 연결이 닫혀도** 오류 대신 `통화 끝: closed` 로 처리한다(노드 예제는 이미 그랬다).
- 계기: 실제 Cloud Run 에서 대화는 `completed` 로 끝났는데 앱이 `end` 를 못 받고 `no close frame` 스택을 남겼다 — DVG 가 close 프레임 없이 끊었고(1.4.16.274 이하) 앞단 프록시가 마지막 메시지를 버린 것으로 추정.
- DVG 1.4.16.275 부터는 `end` 뒤에 close(1000) 로 닫는다. 계약 문서 §3-2 `end` 행에 두 가지(정상 종료 · 닫힘 = 끝 · 결말 모름)를 적었다.
- 확인: 두 예제를 로컬에 띄워 서명 연결 뒤 close 없이 끊음 → 둘 다 `통화 끝: closed` · Go 예제 시험(Go 1.26.7) 통과.

## Cloud Run 실측

- 퀵 가이드 B2 명령을 **적힌 그대로** 실제 Cloud Run(서울)에 실행 — 전부 성공. 서명 없는 연결 401 · DVG 1.4.16.273 시뮬레이터 `completed`.
- **콜드스타트 1.19초**(25분 쉰 뒤 첫 연결 · Cloud Run 로그 `Starting new instance … AUTOSCALING` 로 진짜 콜드스타트임을 확인) — DVG 연결 제한 5초 안. `--min-instances 0` 도 쓸 수 있다고 가이드에 적었다.
- ⚠️ 남은 미확인: 새 판 배포 중 진행 통화 · 실제 전화.

## Cloud Run 예제

- `examples/python/Dockerfile` — `PORT` 로 듣고(Cloud Run 기본 8080) root 가 아닌 사용자로 돈다. 퀵 가이드 **B2** 에 배포 명령(비밀 관리자 · `--timeout 900` · `--min-instances 1`).
- 예제 앱이 서명 비밀의 **앞뒤 공백·줄바꿈을 버린다**(비밀 관리자·편집기가 붙인 줄바꿈 하나로 모든 서명이 어긋나던 함정).
- CI `deploy` 잡 9단계 — 그 Dockerfile 을 수정 없이 빌드해 `PORT=9090` 으로 띄우고, 서명 없는 연결 401 · 실제 DVG 와 대화 완주를 확인한다.
- ⚠️ **실제 Cloud Run 에는 올려 보지 않았다**(TLS 종단·콜드스타트·배포 중 통화 미확인).

## 실서버 설치 퀵 가이드 (DVG 1.4.16.262+)

- `docs/deploy-quickstart.md` + `deploy/`(nginx relay·콘솔 설정, systemd 유닛 둘, 사이드카 `run`).
- CI `deploy` 잡이 그 파일들을 **수정 없이** 실제 DVG 릴리즈(체크섬 확인) · nginx · systemd 로 돌린다 —
  DVG → nginx `wss`(인증서 검증) → 앱 · 콘솔 HTTPS · 대조군(인증서 이름 불일치 거부 · 허용 목록 밖 403) · 사이드카(일회용 사용자).
- CI 로 확인할 수 없는 것: certbot 발급·갱신 · 클라우드 방화벽 · 실제 전화 통화.

## 앱 개발사 콘솔 샘플 (DVG 1.4.16.259+)

- 한글 시스템 글꼴(Apple SD Gothic Neo · Malgun Gothic · Noto Sans KR)을 글꼴 목록에 명시 — DVG 1.4.16.273 대시보드와 같은 목록(웹 글꼴은 불러오지 않는다).
- `console/` — 앱 정보 · 사용량 · 시뮬레이터 위젯. 앱 키는 작은 서버가 들고 DVG 로 세 경로만 넘긴다(브라우저에 키 없음 · 리다이렉트 안 따라감).
  계약 v1 과 별개이며 새 DVG API 를 쓰지 않는다(`/api/v1/apps/self`·`/self/usage`·`/self/simulate` 그대로).

## 그라파나 템플릿 (DVG 1.4.16.271+)

- 대시보드 3개(주문 접수 · 외부 앱 · 개요) · 프로메테우스+그라파나 docker compose 예제 · CI 에서 실제 컨테이너로 모든 쿼리 검사.
  지표는 계약 v1 과 별개이며, **지표 이름은 바꾸지 않습니다**(바꾸면 대시보드가 조용히 빈다 — 새로 더합니다).

## v1 (DVG 1.4.16.257+)

- 1.4.16.265 — `ask.expect:"address"`·`ask.label` + `prompt.address`(주소 풀이 · 좁히는 질문 · 좌표는 앱 등록 선택) · `error bad_expect` · 사용량 `addressLookups`·`coordLookups`
- 1.4.16.262 — 사이드카 환경변수 `DVG_APP_*`(같은 서버에서 DVG 가 띄울 때)
- 1.4.16.261 — `say.interruptible` · `prompt.heardVoice`
- 1.4.16.260 — `ask.choices` + `prompt.choice`·`choiceIndex`·`choiceSource`·`confirm`·`choiceAmbiguous`
- 1.4.16.259 — `setup.simulated`(전화 없는 시험) · `POST /api/v1/apps/self/simulate`
- 1.4.16.257 — 최초: `setup`·`said`·`prompt`·`error`·`end` / `say`·`ask`·`transfer`·`hangup` · HMAC 서명 연결
