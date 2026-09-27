# 계약 변경 이력

필드 추가는 버전을 올리지 않습니다(모르는 필드는 무시). **기존 앱을 깨뜨리는 변경만** 버전을 올립니다.

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
