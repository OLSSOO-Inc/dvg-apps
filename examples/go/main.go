// DVG 외부 앱 최소 예제 (Go) — 음성 주문 접수 · 관리형 음성 레이어 v1.
//
// DVG 가 전화·음성인식·음성합성을 맡고, 이 앱은 **텍스트로만** 대화를 이끈다.
// 계약: ../../docs/voice-relay-v1.md
//
// 실행:
//
//	go run .                                   # DVG_SIGNING_SECRET=... 필요 · 기본 127.0.0.1:19999, 경로 /relay
//	go build -o order-app . && ./order-app     # 사이드카용 바이너리
//
// DVG 사이드카(같은 서버에서 DVG 가 띄움)로 돌리면 DVG_APP_* 가 자동으로 들어온다.
// ⚠️ 예제다 — 실제 주문 등록은 registerOrder() 자리에 넣는다(업무 시스템 API 는 앱이 직접 부른다).
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/websocket"
)

// MaxSkew: 이보다 오래된(또는 미래의) 연결은 거절한다(재생 방지).
const MaxSkew = 300 * time.Second

func env(def string, names ...string) string {
	for _, n := range names {
		if v := os.Getenv(n); v != "" {
			return v
		}
	}
	return def
}

// VerifyDVG: DVG 가 건 연결인가 — 서명·타임스탬프 확인.
func VerifyDVG(h http.Header, secret string, now time.Time) bool {
	appID, callID := h.Get("X-DVG-App-Id"), h.Get("X-DVG-Call-Id")
	ts, sig := h.Get("X-DVG-Timestamp"), h.Get("X-DVG-Signature")
	if secret == "" || appID == "" || callID == "" || sig == "" {
		return false
	}
	sec, err := strconv.ParseInt(ts, 10, 64)
	if err != nil || strconv.FormatInt(sec, 10) != ts {
		return false
	}
	if d := now.Sub(time.Unix(sec, 0)); d > MaxSkew || d < -MaxSkew {
		return false
	}
	m := hmac.New(sha256.New, []byte(secret))
	m.Write([]byte(appID + "\n" + callID + "\n" + ts))
	return hmac.Equal([]byte(hex.EncodeToString(m.Sum(nil))), []byte(sig))
}

var errCallEnded = errors.New("call ended")

// msg: DVG ↔ 앱 메시지(필요한 필드만 — 모르는 필드는 무시된다).
type msg struct {
	Type      string   `json:"type"`
	Text      string   `json:"text,omitempty"`
	Choices   []string `json:"choices,omitempty"`
	Silence   bool     `json:"silence,omitempty"`
	Choice    string   `json:"choice,omitempty"`
	Reason    string   `json:"reason,omitempty"`
	CallID    string   `json:"callId,omitempty"`
	OrgID     string   `json:"orgId,omitempty"`
	Caller    *string  `json:"caller,omitempty"`
	Simulated bool     `json:"simulated,omitempty"`
}

// session: 한 통화 — DVG 는 엄격한 요청·응답이라 읽기·쓰기가 한 고루틴에서 번갈아 일어난다.
type session struct{ c *websocket.Conn }

func (s session) recv() (msg, error) {
	var m msg
	_ = s.c.SetReadDeadline(time.Now().Add(15 * time.Minute))
	if err := s.c.ReadJSON(&m); err != nil {
		return m, err
	}
	if m.Type == "end" {
		log.Printf("통화 끝: %s", m.Reason)
		return m, errCallEnded
	}
	return m, nil
}

func (s session) send(m msg) error { return s.c.WriteJSON(m) }

// ask: 질문하고 답을 받는다. choices 를 주면 DVG 가 답을 그중 하나로 읽어 준다(초성 판정 포함).
func (s session) ask(text string, choices []string) (string, error) {
	if err := s.send(msg{Type: "ask", Text: text, Choices: choices}); err != nil {
		return "", err
	}
	m, err := s.recv()
	if err != nil || m.Type != "prompt" || m.Silence {
		return "", err
	}
	if choices != nil {
		return m.Choice, nil // 못 골랐으면 빈 값 → 다시 묻는다
	}
	return strings.TrimSpace(m.Text), nil
}

func (s session) end(typ, text string) error {
	if err := s.send(msg{Type: typ, Text: text}); err != nil {
		return err
	}
	_, err := s.recv()
	return err
}

func registerOrder(order map[string]string, setup msg) bool {
	b, _ := json.Marshal(order)
	if setup.Simulated {
		// 🔴 시험 통화(대시보드 🧪) — 실제 주문을 만들지 않는다.
		log.Printf("시험 통화 — 주문 등록 건너뜀: %s", b)
		return true
	}
	log.Printf("주문 등록(예제): org=%s %s", setup.OrgID, b)
	return true
}

func handle(c *websocket.Conn) error {
	s := session{c}
	setup, err := s.recv() // 첫 메시지는 항상 setup
	if err != nil {
		return err
	}
	log.Printf("통화 시작 %s (발신번호 제공=%v)", setup.CallID, setup.Caller != nil)
	order := map[string]string{}
	// (칸, 첫 질문, 다시 물을 때의 질문) — 🔴 같은 문장을 되풀이하지 않는다. 다시 물을 때는 질문을 바꾼다.
	steps := []struct {
		key, question, again string
		choices              []string
	}{
		{"origin", "어디에서 보내시나요?", "제가 잘 못 들었습니다. 물건을 가지러 갈 곳을 말씀해 주세요.", nil},
		{"destination", "어디로 보내시나요?", "제가 잘 못 들었습니다. 물건을 받으실 곳을 말씀해 주세요.", nil},
		{"pay", "결제는 선불인가요 착불인가요?", "제가 잘 못 들었습니다. 선불이면 「선불」. 착불이면 「착불」.", []string{"선불", "착불"}},
	}
	for _, st := range steps {
		ans, err := s.ask(st.question, st.choices)
		if err != nil {
			return err
		}
		if ans == "" {
			if ans, err = s.ask(st.again, st.choices); err != nil {
				return err
			}
		}
		if ans == "" {
			return s.end("transfer", "") // 번호는 DVG 가 정한다(앱이 지정할 수 없다)
		}
		order[st.key] = ans
	}
	// 복창 — 나열은 마침표로 끊는다(쉼표로 이으면 전화에서 한 덩어리로 들린다).
	ok, err := s.ask("출발 "+order["origin"]+". 도착 "+order["destination"]+". 결제 "+order["pay"]+". 맞으면 「네」라고 말씀해 주세요.", nil)
	if err != nil {
		return err
	}
	if !(strings.HasPrefix(ok, "네") || strings.HasPrefix(ok, "예") || strings.HasPrefix(ok, "맞")) {
		return s.end("transfer", "")
	}
	if registerOrder(order, setup) {
		return s.end("hangup", "접수되었습니다. 감사합니다.")
	}
	return s.end("transfer", "")
}

func main() {
	secret := env("", "DVG_APP_SIGNING_SECRET", "DVG_SIGNING_SECRET")
	host := env("127.0.0.1", "DVG_APP_HOST", "APP_HOST")
	port := env("19999", "DVG_APP_PORT", "APP_PORT")
	path := env("/relay", "DVG_APP_PATH", "APP_PATH")
	if secret == "" {
		log.Fatal("DVG_SIGNING_SECRET 이 비어 있습니다 — 앱 등록 때 받은 서명 비밀을 넣으세요")
	}
	up := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }} // 브라우저가 아니라 DVG 가 건다 — 서명으로 확인한다
	mux := http.NewServeMux()
	mux.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
		// WebSocket 업그레이드 전에 거른다 — 서명이 틀리면 연결 자체를 받지 않는다.
		if !VerifyDVG(r.Header, secret, time.Now()) {
			http.Error(w, "bad signature", http.StatusUnauthorized)
			return
		}
		c, err := up.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer c.Close()
		c.SetReadLimit(1 << 20)
		if err := handle(c); err != nil && !errors.Is(err, errCallEnded) {
			log.Printf("앱 오류: %v", err)
		}
	})
	addr := net.JoinHostPort(host, port)
	srv := &http.Server{Addr: addr, Handler: mux, ReadHeaderTimeout: 10 * time.Second}
	log.Printf("listening ws://%s%s", addr, path)
	log.Fatal(srv.ListenAndServe())
}
