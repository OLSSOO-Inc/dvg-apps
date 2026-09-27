// 화면이 쓰는 판단 — DOM 을 모르는 순수 함수(브라우저와 Node 시험이 같은 파일을 쓴다).
//
// ⭐ 이 파일이 지키는 것: **「0」과 「모름」을 섞지 않는다.**
//   - 이 달 기록이 없으면 «0건» 이 아니라 «아직 기록 없음» 이다.
//   - 장부를 못 읽었으면 «0» 이 아니라 «읽지 못함» 이다.
//   - 수량을 몰랐던 통화가 있으면 음성인식·음성합성 합계는 «최소값» 이다.
// 정합 판정(complete)은 DVG 가 한다 — 여기서 다시 계산하지 않는다(필드가 늘면 조용히 틀린다).

// 통화 결말 — DVG 계약의 값 그대로. toHuman: 실통화였다면 사람에게 연결됐다.
export const OUTCOMES = {
  completed: { label: '앱이 끝냄', toHuman: false },
  transferred: { label: '사람에게 넘김(앱 요청)', toHuman: true },
  caller_hangup: { label: '발신자가 끊음', toHuman: false },
  app_unavailable: { label: '앱 연결 실패', toHuman: true },
  app_error: { label: '앱 오류·응답 없음', toHuman: true },
  limit: { label: '지시 수·시간 상한', toHuman: true },
  quota: { label: '월 상한 초과', toHuman: true },
  notice_transfer: { label: 'AI 고지 실패', toHuman: true },
  voice_failed: { label: '음성 연결 실패', toHuman: true },
};

export function outcomeLabel(code) {
  return OUTCOMES[code]?.label ?? code; // 모르는 결말도 버리지 않고 그대로 보인다
}

// monthUTC: DVG 장부의 달은 UTC 기준이다.
export function monthUTC(d = new Date()) {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

export function isMonth(v) {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(String(v));
}

// usageView: DVG 사용량 응답 → 화면이 그릴 상태 하나.
//   state: 'error' | 'unsupported' | 'none' | 'ok'
export function usageView(status, body, quota = { monthlyCallQuota: 0, quotaEnforce: false }) {
  if (status !== 200 || !body || typeof body !== 'object') {
    const code = body?.code;
    const msg = {
      ledger_unreadable: 'DVG 가 사용량 장부를 읽지 못했습니다 — 0건이 아니라 «모름»입니다.',
      app_key_invalid: '앱 키가 맞지 않습니다 — 키를 다시 발급받았다면 키 파일을 바꾸십시오.',
      app_disabled: '이 앱은 DVG 에서 사용 중지 상태입니다.',
      bad_month: '달은 YYYY-MM 형식이어야 합니다.',
    }[code];
    return { state: 'error', status, code: code || `http_${status}`, message: msg || body?.error || `HTTP ${status}` };
  }
  if (body.supported === false) {
    return { state: 'unsupported', month: body.month, message: '이 DVG 에서는 사용량 장부가 꺼져 있습니다.' };
  }
  if (!body.found || !body.usage) {
    return { state: 'none', month: body.month, tz: body.tz || 'UTC', message: '이 달에는 아직 기록이 없습니다(0건이 아니라 «아직 없음»).' };
  }
  const u = body.usage;
  const outcomes = Object.entries(u.byOutcome || {})
    .map(([code, n]) => ({ code, label: outcomeLabel(code), n, toHuman: OUTCOMES[code]?.toHuman ?? null }))
    .sort((a, b) => b.n - a.n || a.code.localeCompare(b.code));
  const known = outcomes.filter((o) => o.toHuman !== null);
  const toHuman = known.filter((o) => o.toHuman).reduce((s, o) => s + o.n, 0);
  const lowerBound = (u.usageUnknownCalls || 0) > 0;
  const q = Number(quota.monthlyCallQuota) || 0;
  return {
    state: 'ok',
    month: body.month,
    tz: body.tz || 'UTC',
    complete: body.complete !== false,
    calls: u.calls,
    outcomes,
    // 모르는 결말이 섞여 있으면 비율을 내지 않는다(분모가 틀린다).
    toHumanRate: u.calls > 0 && known.length === outcomes.length ? toHuman / u.calls : null,
    turns: u.turns,
    connectedSeconds: u.connectedSeconds,
    sttSeconds: u.sttSeconds,
    ttsChars: u.ttsChars,
    lowerBound,
    usageUnknownCalls: u.usageUnknownCalls || 0,
    addressLookups: u.addressLookups || 0,
    coordLookups: u.coordLookups || 0,
    tenants: Object.keys(u.byTenant || {}).length,
    quota: q > 0 ? { limit: q, used: u.calls, rate: u.calls / q, enforce: !!quota.quotaEnforce } : null,
    updatedAt: u.updatedAt,
    gatewayVersion: body.gatewayVersion,
  };
}

export function fmtSeconds(sec) {
  const s = Math.round(Number(sec) || 0);
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}분 ${s % 60}초`;
  return `${Math.floor(m / 60)}시간 ${m % 60}분`;
}

export function fmtInt(n) {
  return Number(n || 0).toLocaleString('ko-KR');
}

export function fmtPct(r) {
  return r == null ? '—' : `${(r * 100).toFixed(1)}%`;
}

// ── 시뮬레이터 ─────────────────────────────────────────────────────────

export const SIM_MAX_UTTERANCES = 20; // DVG 와 같은 상한(넘으면 DVG 가 400)
export const SIM_MAX_CHARS = 300;
export const SILENCE_MARK = '(무응답)';

// parseUtterances: 한 줄 = 발신자의 한 마디. 빈 줄은 무시하고, «(무응답)» 줄은 «아무 말도 안 함».
export function parseUtterances(text) {
  const out = [];
  const errors = [];
  for (const raw of String(text || '').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    out.push(line === SILENCE_MARK ? '' : line);
  }
  if (out.length > SIM_MAX_UTTERANCES) errors.push(`발화는 ${SIM_MAX_UTTERANCES}개까지입니다(지금 ${out.length}개)`);
  out.forEach((u, i) => {
    const n = [...u].length;
    if (n > SIM_MAX_CHARS) errors.push(`${i + 1}번째 발화가 ${n}자입니다(${SIM_MAX_CHARS}자까지)`);
  });
  return { utterances: out, errors };
}

// transcriptItems: DVG 대화 기록 → 화면 줄.
export function transcriptItems(lines) {
  return (lines || []).map((l) => {
    const who = l.who === 'caller' ? 'caller' : 'dvg';
    let text = l.text || '';
    let kindLabel = '';
    if (l.kind === 'notice') kindLabel = 'AI 고지';
    else if (l.kind === 'ask') kindLabel = '질문';
    else if (l.kind === 'silence') { kindLabel = '무응답'; text = text || '(아무 말도 하지 않음)'; }
    else if (l.kind === 'hangup') kindLabel = '끊음';
    const notes = [];
    if (l.choice) {
      let n = `선택지 판정: ${l.choice}`;
      if (l.choiceSource) n += ` (${l.choiceSource})`;
      if (l.confirm) n += ' · 추정이라 앱이 복창해야 함';
      notes.push(n);
    } else if (l.choiceAmbiguous) {
      notes.push('선택지 판정: 둘 이상에 걸림 — 앱이 다시 물어야 함');
    }
    if (l.address) notes.push(addressNote(l.address));
    return { who, kind: l.kind, kindLabel, text, notes };
  });
}

export function addressNote(a) {
  const parts = [`주소 판정: ${a.status}`];
  if (a.line) parts.push(a.line);
  if (a.status === 'ambiguous' && a.question) parts.push(`좁히는 질문 «${a.question}»`);
  if (a.status === 'partial' && a.missing?.length) parts.push(`빠진 칸 ${a.missing.join('·')}`);
  if (a.reason) parts.push(`사유 ${a.reason}`);
  if (a.coordStatus) parts.push(`좌표 ${a.coordStatus}`);
  return parts.join(' · ');
}

// simErrorText: 시뮬레이터가 대화 기록 없이 끝난 사정.
export function simErrorText(status, body, retryAfter) {
  if (status === 429) return `시험은 앱당 분당 20회까지입니다 — ${retryAfter || 60}초 뒤에 다시 해 보십시오.`;
  const byCode = {
    app_key_invalid: '앱 키가 맞지 않습니다.',
    app_disabled: '이 앱은 DVG 에서 사용 중지 상태입니다.',
    too_many_utterances: `발화는 ${SIM_MAX_UTTERANCES}개까지입니다.`,
    utterance_too_long: `발화 한 개는 ${SIM_MAX_CHARS}자까지입니다.`,
    dvg_timeout: 'DVG 가 제때 답하지 않았습니다.',
    dvg_unreachable: 'DVG 에 연결하지 못했습니다.',
  };
  return byCode[body?.code] || body?.error || `HTTP ${status}`;
}
