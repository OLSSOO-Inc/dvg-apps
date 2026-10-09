// DVG 외부 앱 최소 예제 (Java) — 음성 주문 접수 · 관리형 음성 레이어 v1.
//
// DVG 가 전화·음성인식·음성합성을 맡고, 이 앱은 **텍스트로만** 대화를 이끈다.
// 계약: ../../docs/voice-relay-v1.md · 동작은 Python·Node·Go 예제와 같다.
//
// 실행(Java 17+):
//
//   mvn -q package                                   # target/order-app.jar (의존성 포함 실행 파일 하나)
//   DVG_SIGNING_SECRET=... java -jar target/order-app.jar   # 기본 127.0.0.1:19999, 경로 /relay
//
// 같은 서버(사이드카)로 실행되면 DVG_APP_* 가 자동으로 들어온다.
// ⚠️ 예제다 — 실제 주문 등록은 registerOrder() 자리에 넣는다(업무 시스템 API 는 앱이 직접 부른다).
package io.olssoo.dvg.example;

import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.java_websocket.WebSocket;
import org.java_websocket.drafts.Draft;
import org.java_websocket.exceptions.InvalidDataException;
import org.java_websocket.framing.CloseFrame;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.handshake.ServerHandshakeBuilder;
import org.java_websocket.server.WebSocketServer;

public final class OrderApp extends WebSocketServer {

    /** 이보다 오래된(또는 미래의) 연결은 거절한다(재생 방지). */
    static final long MAX_SKEW_SECONDS = 300;

    private static final Gson GSON = new Gson();
    private static final JsonObject CLOSED = new JsonObject(); // 연결이 끊겼다는 표시(큐 안에서만 쓴다)

    private final String secret;
    private final String path;
    private final Map<WebSocket, BlockingQueue<JsonObject>> inbox = new ConcurrentHashMap<>();

    OrderApp(InetSocketAddress addr, String secret, String path) {
        super(addr);
        this.secret = secret;
        this.path = path;
        setReuseAddr(true);
    }

    /** DVG 가 건 연결인가 — 서명·타임스탬프 확인. header 는 이름으로 값을 돌려준다(없으면 null 또는 ""). */
    static boolean verifyDvg(Function<String, String> header, String secret, long nowSeconds) {
        String appId = nz(header.apply("X-DVG-App-Id"));
        String callId = nz(header.apply("X-DVG-Call-Id"));
        String ts = nz(header.apply("X-DVG-Timestamp"));
        String sig = nz(header.apply("X-DVG-Signature"));
        if (secret == null || secret.isEmpty() || appId.isEmpty() || callId.isEmpty() || sig.isEmpty() || !ts.matches("[0-9]+")) {
            return false;
        }
        long sec;
        try {
            sec = Long.parseLong(ts);
        } catch (NumberFormatException e) {
            return false;
        }
        if (Math.abs(nowSeconds - sec) > MAX_SKEW_SECONDS) {
            return false;
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] want = HexFormat.of().formatHex(mac.doFinal((appId + "\n" + callId + "\n" + ts).getBytes(StandardCharsets.UTF_8)))
                    .getBytes(StandardCharsets.US_ASCII);
            return MessageDigest.isEqual(want, sig.getBytes(StandardCharsets.US_ASCII)); // 시간이 일정한 비교
        } catch (Exception e) {
            return false;
        }
    }

    private static String nz(String s) {
        return s == null ? "" : s;
    }

    // WebSocket 업그레이드 전에 거른다 — 경로가 다르거나 서명이 틀리면 연결 자체를 받지 않는다.
    @Override
    public ServerHandshakeBuilder onWebsocketHandshakeReceivedAsServer(WebSocket conn, Draft draft, ClientHandshake req)
            throws InvalidDataException {
        ServerHandshakeBuilder b = super.onWebsocketHandshakeReceivedAsServer(conn, draft, req);
        if (!path.equals(URI.create(req.getResourceDescriptor()).getPath())) {
            throw new InvalidDataException(CloseFrame.POLICY_VALIDATION, "not found");
        }
        if (!verifyDvg(req::getFieldValue, secret, System.currentTimeMillis() / 1000)) {
            throw new InvalidDataException(CloseFrame.POLICY_VALIDATION, "bad signature");
        }
        return b;
    }

    // 통화 하나 = 연결 하나 = 스레드 하나. DVG 는 엄격한 요청·응답이라 그 스레드에서 차례로 읽고 쓴다.
    @Override
    public void onOpen(WebSocket conn, ClientHandshake handshake) {
        BlockingQueue<JsonObject> q = new LinkedBlockingQueue<>();
        inbox.put(conn, q);
        Thread t = new Thread(() -> {
            try {
                handle(new Session(conn, q));
            } catch (CallEnded e) {
                // 정상 종료
            } catch (Exception e) {
                System.err.println("앱 오류: " + e);
            } finally {
                inbox.remove(conn);
                conn.close();
            }
        }, "call");
        t.setDaemon(true);
        t.start();
    }

    @Override
    public void onMessage(WebSocket conn, String message) {
        BlockingQueue<JsonObject> q = inbox.get(conn);
        if (q == null) {
            return;
        }
        try {
            JsonElement e = JsonParser.parseString(message);
            if (e.isJsonObject()) {
                q.offer(e.getAsJsonObject());
            }
        } catch (RuntimeException ignored) {
            // JSON 이 아니면 버린다(DVG 는 JSON 만 보낸다)
        }
    }

    @Override
    public void onClose(WebSocket conn, int code, String reason, boolean remote) {
        // DVG 는 end 를 보낸 뒤 연결을 닫는다. 앞에 프록시가 있으면 end 가 오기 전에 닫힐 수 있다 —
        // 그래도 통화는 끝났다(결말은 모른다). 오류로 다루지 않는다.
        BlockingQueue<JsonObject> q = inbox.get(conn);
        if (q != null) {
            q.offer(CLOSED);
        }
    }

    @Override
    public void onError(WebSocket conn, Exception ex) {
        System.err.println("연결 오류: " + ex);
    }

    @Override
    public void onStart() {
        setConnectionLostTimeout(60);
    }

    static final class CallEnded extends Exception {
        CallEnded(String reason) {
            super(reason);
        }
    }

    /** 한 통화. */
    static final class Session {
        private final WebSocket conn;
        private final BlockingQueue<JsonObject> q;

        Session(WebSocket conn, BlockingQueue<JsonObject> q) {
            this.conn = conn;
            this.q = q;
        }

        JsonObject recv() throws CallEnded, InterruptedException {
            JsonObject m = q.poll(15, TimeUnit.MINUTES);
            if (m == null || m == CLOSED) {
                System.out.println("통화 끝: closed");
                throw new CallEnded("closed");
            }
            if ("end".equals(str(m, "type"))) {
                System.out.println("통화 끝: " + str(m, "reason"));
                throw new CallEnded(str(m, "reason"));
            }
            return m;
        }

        void send(Map<String, Object> m) {
            conn.send(GSON.toJson(m));
        }

        /** 질문하고 답을 받는다. choices 를 주면 DVG 가 답을 그중 하나로 읽어 준다(초성 판정 포함). 못 들었으면 "". */
        String ask(String text, List<String> choices) throws CallEnded, InterruptedException {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("type", "ask");
            m.put("text", text);
            if (choices != null) {
                m.put("choices", choices);
            }
            send(m);
            JsonObject r = recv();
            if (!"prompt".equals(str(r, "type")) || (r.has("silence") && r.get("silence").getAsBoolean())) {
                return "";
            }
            return choices != null ? str(r, "choice") : str(r, "text").trim();
        }

        void end(String type, String text) throws CallEnded, InterruptedException {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("type", type);
            if (text != null && !text.isEmpty()) {
                m.put("text", text);
            }
            send(m);
            recv(); // end 가 온다(CallEnded)
        }
    }

    static String str(JsonObject o, String k) {
        return o.has(k) && o.get(k).isJsonPrimitive() ? o.get(k).getAsString() : "";
    }

    record Step(String key, String question, String again, List<String> choices) {}

    static boolean registerOrder(Map<String, String> order, JsonObject setup) {
        if (setup.has("simulated") && setup.get("simulated").getAsBoolean()) {
            // 🔴 시험 통화(setup.simulated) — 실제 주문을 만들지 않는다.
            System.out.println("시험 통화 — 주문 등록 건너뜀: " + GSON.toJson(order));
            return true;
        }
        System.out.println("주문 등록(예제): org=" + str(setup, "orgId") + " " + GSON.toJson(order));
        return true;
    }

    static void handle(Session s) throws CallEnded, InterruptedException {
        JsonObject setup = s.recv(); // 첫 메시지는 항상 setup
        System.out.println("통화 시작 " + str(setup, "callId") + " (발신번호 제공=" + setup.has("caller") + ")");
        Map<String, String> order = new LinkedHashMap<>();
        // (칸, 첫 질문, 다시 물을 때의 질문) — 🔴 같은 문장을 되풀이하지 않는다. 다시 물을 때는 질문을 바꾼다.
        List<Step> steps = new ArrayList<>();
        steps.add(new Step("origin", "어디에서 보내시나요?", "제가 잘 못 들었습니다. 물건을 가지러 갈 곳을 말씀해 주세요.", null));
        steps.add(new Step("destination", "어디로 보내시나요?", "제가 잘 못 들었습니다. 물건을 받으실 곳을 말씀해 주세요.", null));
        steps.add(new Step("pay", "선불. 착불. 결제는 어느 쪽인가요?", "제가 잘 못 들었습니다. 선불이면 「선불」. 착불이면 「착불」.", List.of("선불", "착불")));
        for (Step st : steps) {
            String ans = s.ask(st.question(), st.choices());
            if (ans.isEmpty()) {
                ans = s.ask(st.again(), st.choices());
            }
            if (ans.isEmpty()) {
                s.end("transfer", null); // 번호는 DVG 가 정한다(앱이 지정할 수 없다)
                return;
            }
            order.put(st.key(), ans);
        }
        // 복창 — 나열은 마침표로 끊는다(쉼표로 이으면 전화에서 한 덩어리로 들린다).
        String ok = s.ask("출발 " + order.get("origin") + ". 도착 " + order.get("destination") + ". 결제 " + order.get("pay")
                + ". 맞으면 「네」라고 말씀해 주세요.", null);
        if (!(ok.startsWith("네") || ok.startsWith("예") || ok.startsWith("맞"))) {
            s.end("transfer", null);
            return;
        }
        if (registerOrder(order, setup)) {
            s.end("hangup", "접수되었습니다. 감사합니다.");
        } else {
            s.end("transfer", null);
        }
    }

    static String env(String def, String... names) {
        for (String n : names) {
            String v = System.getenv(n);
            if (v != null && !v.isEmpty()) {
                return v;
            }
        }
        return def;
    }

    public static void main(String[] args) {
        String secret = env("", "DVG_APP_SIGNING_SECRET", "DVG_SIGNING_SECRET");
        String host = env("127.0.0.1", "DVG_APP_HOST", "APP_HOST");
        int port = Integer.parseInt(env("19999", "DVG_APP_PORT", "APP_PORT"));
        String path = env("/relay", "DVG_APP_PATH", "APP_PATH");
        if (secret.isEmpty()) {
            System.err.println("DVG_SIGNING_SECRET 이 비어 있습니다 — 앱 등록 때 받은 서명 비밀을 넣으세요");
            System.exit(1);
        }
        OrderApp app = new OrderApp(new InetSocketAddress(host, port), secret, path);
        System.out.println("listening ws://" + host + ":" + port + path);
        app.run(); // 막는다(끝나지 않는다)
    }
}
