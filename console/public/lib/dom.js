// 작은 DOM 도우미. ⚠️ 글자는 언제나 textContent 로 넣는다 — 대화 기록에는 앱과 발신자가 한 말이 그대로 들어온다
// (innerHTML 로 넣으면 그 말이 화면에서 코드로 실행될 수 있다).

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, String(v));
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

// put: el 의 내용을 nodes 로 바꾼다. ⚠️ replaceChildren 은 null 을 글자 «null» 로 넣는다 — 빈 칸은 걸러 낸다.
export function put(el, ...nodes) {
  el.replaceChildren(...nodes.flat().filter((n) => n != null && n !== false));
}
