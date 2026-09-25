package main

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"testing"
	"time"
)

// 서명 시험 벡터 — VerifyDVG 가 DVG 와 같은 값을 받아들이는가(../../conformance/vector.json).
func TestVerifyDVG_ConformanceVector(t *testing.T) {
	b, err := os.ReadFile("../../conformance/vector.json")
	if err != nil {
		t.Fatal(err)
	}
	var v struct {
		SigningSecret, AppID, CallID, Signature string
		Timestamp                               int64
	}
	if err := json.Unmarshal(b, &v); err != nil {
		t.Fatal(err)
	}
	h := http.Header{}
	h.Set("X-DVG-App-Id", v.AppID)
	h.Set("X-DVG-Call-Id", v.CallID)
	h.Set("X-DVG-Timestamp", strconv.FormatInt(v.Timestamp, 10))
	h.Set("X-DVG-Signature", v.Signature)
	at := time.Unix(v.Timestamp, 0)
	bad := h.Clone()
	bad.Set("X-DVG-Signature", "0000000000000000000000000000000000000000000000000000000000000000")
	for _, c := range []struct {
		name string
		got  bool
		want bool
	}{
		{"벡터를 받아들인다", VerifyDVG(h, v.SigningSecret, at), true},
		{"틀린 서명은 거절", VerifyDVG(bad, v.SigningSecret, at), false},
		{"틀린 비밀은 거절", VerifyDVG(h, "other-secret", at), false},
		{"300초 넘게 지난 연결은 거절", VerifyDVG(h, v.SigningSecret, at.Add(301*time.Second)), false},
		{"300초 이내는 받는다", VerifyDVG(h, v.SigningSecret, at.Add(300*time.Second)), true},
	} {
		if c.got != c.want {
			t.Errorf("%s: got %v", c.name, c.got)
		}
	}
}
