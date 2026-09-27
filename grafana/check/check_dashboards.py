"""그라파나 템플릿 검사.

정적(기본):  JSON 유효 · uid 유일 · 데이터 소스가 dvg-prometheus · 쿼리가 쓰는 지표가 **실제 DVG 출력(testdata)** 에 있다 ·
             표본에 개인정보 라벨이 없다.
실시간(--live): 떠 있는 프로메테우스·그라파나에 대고 — 긁기 대상이 up · 표본에 값이 있는 지표가 실제로 들어왔다 ·
             **모든 패널 쿼리가 오류 없이 돈다** · 대시보드 3개가 그라파나에 등록됐다.

⚠️ 지표 이름의 진실의 출처는 DVG 의 출력이다 — testdata/sample-metrics.txt 는 DVG 지표 코드로 생성한 실물이다.
"""
import argparse, base64, glob, json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SAMPLE = os.path.join(ROOT, "testdata", "sample-metrics.txt")
DS_UID = "dvg-prometheus"
PII = {"caller", "callee", "phone", "number", "linkedid", "linked_id", "text", "address", "did", "extension", "ext", "email"}

errors = []


def err(msg):
    errors.append(msg)
    print("✗", msg)


def families():
    fams, with_data = set(), set()
    for line in open(SAMPLE, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"# TYPE (\S+) (\S+)", line)
        if m:
            fams.add(m.group(1))
            continue
        if line and not line.startswith("#"):
            name = re.match(r"[a-zA-Z_:][a-zA-Z0-9_:]*", line).group(0)
            base = re.sub(r"_(bucket|sum|count)$", "", name)
            with_data.add(base if base in fams else name)
            for lab in re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)="', line):
                if lab.lower() in PII:
                    err(f"표본에 개인정보 라벨 {lab!r}: {line[:80]}")
    return fams, with_data


def dashboards():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "dashboards", "*.json"))):
        try:
            out.append((f, json.load(open(f, encoding="utf-8"))))
        except Exception as e:
            err(f"{f}: JSON 아님 — {e}")
    return out


def exprs(d):
    for p in d.get("panels", []):
        for t in p.get("targets", []):
            if t.get("expr"):
                yield p.get("title", "?"), t["expr"]
    for v in d.get("templating", {}).get("list", []):
        q = v.get("query")
        if isinstance(q, dict):
            q = q.get("query")
        if q:
            yield "변수 " + v.get("name", "?"), q


def substitute(e):
    e = re.sub(r"\$__range", "1h", e)
    e = re.sub(r"\$__rate_interval", "1m", e)
    e = re.sub(r"\$__interval", "1m", e)
    return re.sub(r"\$[a-zA-Z_]+", ".*", e)


def static():
    fams, with_data = families()
    ds = dashboards()
    uids = [d.get("uid") for _, d in ds]
    if len(set(uids)) != len(uids):
        err(f"uid 중복: {uids}")
    for f, d in ds:
        for p in d.get("panels", []):
            if p.get("type") == "row":
                continue
            if (p.get("datasource") or {}).get("uid") != DS_UID:
                err(f"{os.path.basename(f)} «{p.get('title')}» 데이터 소스가 {DS_UID} 가 아니다")
        for title, e in exprs(d):
            for name in set(re.findall(r"\bdvg_[a-z0-9_]+", e)):
                base = re.sub(r"_(bucket|sum|count)$", "", name)
                if name not in fams and base not in fams:
                    err(f"{os.path.basename(f)} «{title}»: DVG 가 내지 않는 지표 {name}")
    print(f"정적 검사: 대시보드 {len(ds)}개 · 지표 {len(fams)}종(값 있는 것 {len(with_data)}종)")
    return ds, with_data


def get(url, auth=None):
    req = urllib.request.Request(url)
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def prom_query(prom, q):
    return get(prom + "/api/v1/query?" + urllib.parse.urlencode({"query": q}))


def live(args, ds, with_data):
    deadline = time.time() + args.wait
    # ① 긁기 대상 up + 표본의 값이 실제로 들어옴(적어도 두 번 긁혀야 increase 가 돈다)
    while True:
        try:
            up = prom_query(args.prom, 'up{job="dvg"}')["data"]["result"]
            got = prom_query(args.prom, "count_over_time(dvg_order_calls_total[1m])")["data"]["result"]
            if up and up[0]["value"][1] == "1" and got and float(got[0]["value"][1]) >= 3:
                break
        except Exception as e:
            last = e
        if time.time() > deadline:
            err("프로메테우스가 가짜 DVG 를 긁지 못했다(시간 초과)")
            return
        time.sleep(2)
    print("프로메테우스: 긁기 대상 up · 값 들어옴")
    for fam in sorted(with_data):
        r = prom_query(args.prom, f"count({fam}) or count({fam}_count)")
        if not r["data"]["result"]:
            err(f"표본에는 있는데 프로메테우스에 없다: {fam}")
    n = 0
    for f, d in ds:
        for title, e in exprs(d):
            if e.startswith("label_values("):
                m = re.match(r"label_values\((.*),\s*([a-z_]+)\)$", e)
                sel = substitute(m.group(1)) if m else ""
                r = get(args.prom + "/api/v1/series?" + urllib.parse.urlencode({"match[]": sel}))
            else:
                r = prom_query(args.prom, substitute(e))
            n += 1
            if r.get("status") != "success":
                err(f"{os.path.basename(f)} «{title}» 쿼리 실패: {r}")
    print(f"프로메테우스: 쿼리 {n}개 실행")
    # ② 그라파나
    auth = "admin:" + args.grafana_password
    while True:
        try:
            if get(args.grafana + "/api/health").get("database") == "ok":
                break
        except Exception:
            pass
        if time.time() > deadline:
            err("그라파나가 뜨지 않았다(시간 초과)")
            return
        time.sleep(2)
    want = {d["uid"] for _, d in ds}
    for _ in range(20):
        found = {x.get("uid") for x in get(args.grafana + "/api/search?type=dash-db", auth)}
        if want <= found:
            break
        time.sleep(2)
    if not want <= found:
        err(f"그라파나에 등록 안 된 대시보드: {sorted(want - found)}")
    dsr = get(args.grafana + "/api/datasources/uid/" + DS_UID, auth)
    if dsr.get("uid") != DS_UID:
        err(f"그라파나 데이터 소스 {DS_UID} 가 없다: {dsr}")
    print(f"그라파나: 대시보드 {len(want & found)}/{len(want)} · 데이터 소스 {DS_UID}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--prom", default="http://127.0.0.1:9090")
    ap.add_argument("--grafana", default="http://127.0.0.1:3000")
    ap.add_argument("--grafana-password", default="")
    ap.add_argument("--wait", type=int, default=90)
    args = ap.parse_args()
    ds, with_data = static()
    if args.live and not errors:
        live(args, ds, with_data)
    if errors:
        print(f"실패 {len(errors)}건")
        sys.exit(1)
    print("통과")


if __name__ == "__main__":
    main()
