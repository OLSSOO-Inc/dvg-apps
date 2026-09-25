# 적합성 시험

[`vector.json`](vector.json) 은 DVG 가 실제로 만드는 서명 값입니다(DVG 게이트웨이 쪽 시험 `TestSign_PublicConformanceVector` 가 같은 값을 고정합니다).
여러분의 서명 확인 함수가 이 값을 **받아들이고**, 서명·비밀·시각이 틀리면 **거절**해야 합니다.

```bash
python3 conformance/check_python.py
```

```bash
node conformance/check_node.mjs
```

```bash
cd examples/go && go test ./...
```
