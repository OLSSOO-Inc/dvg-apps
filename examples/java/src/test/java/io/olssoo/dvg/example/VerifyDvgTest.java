package io.olssoo.dvg.example;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** 서명 시험 벡터 — verifyDvg 가 DVG 와 같은 값을 받아들이는가(../../conformance/vector.json). */
class VerifyDvgTest {

    @Test
    void conformanceVector() throws Exception {
        JsonObject v = JsonParser.parseString(Files.readString(Path.of("../../conformance/vector.json"))).getAsJsonObject();
        String secret = v.get("signingSecret").getAsString();
        long ts = v.get("timestamp").getAsLong();
        Map<String, String> h = new HashMap<>();
        h.put("X-DVG-App-Id", v.get("appId").getAsString());
        h.put("X-DVG-Call-Id", v.get("callId").getAsString());
        h.put("X-DVG-Timestamp", Long.toString(ts));
        h.put("X-DVG-Signature", v.get("signature").getAsString());

        assertEquals(true, OrderApp.verifyDvg(h::get, secret, ts), "벡터를 받아들인다");
        Map<String, String> bad = new HashMap<>(h);
        bad.put("X-DVG-Signature", "0".repeat(64));
        assertEquals(false, OrderApp.verifyDvg(bad::get, secret, ts), "틀린 서명은 거절");
        assertEquals(false, OrderApp.verifyDvg(h::get, "other-secret", ts), "틀린 비밀은 거절");
        assertEquals(false, OrderApp.verifyDvg(h::get, secret, ts + 301), "300초 넘게 지난 연결은 거절");
        assertEquals(true, OrderApp.verifyDvg(h::get, secret, ts + 300), "300초 이내는 받는다");
        Map<String, String> noTs = new HashMap<>(h);
        noTs.put("X-DVG-Timestamp", "1790000000.5");
        assertEquals(false, OrderApp.verifyDvg(noTs::get, secret, ts), "숫자가 아닌 시각은 거절");
    }
}
