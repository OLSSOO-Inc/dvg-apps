// 소스 검사 — 화면 코드가 지켜야 할 두 규칙. DOM 없이 Node 에서 돌 수 있는 것은 이렇게 파일을 읽어 본다.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PUBLIC = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'public');

function jsFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? jsFiles(p) : e.name.endsWith('.js') ? [p] : [];
  });
}

test('innerHTML·outerHTML·insertAdjacentHTML 을 쓰지 않는다(대화 기록에는 앱·발신자의 말이 그대로 들어온다)', () => {
  for (const f of jsFiles(PUBLIC)) {
    const s = readFileSync(f, 'utf8').replace(/\/\/.*$/gm, '');
    assert.ok(!/\b(innerHTML|outerHTML|insertAdjacentHTML)\b/.test(s), path.relative(PUBLIC, f));
  }
});

test('replaceChildren 은 lib/dom.js 의 put 을 거친다(null 이 글자 «null» 로 보이지 않게)', () => {
  for (const f of jsFiles(PUBLIC)) {
    if (f.endsWith(path.join('lib', 'dom.js'))) continue;
    const s = readFileSync(f, 'utf8').replace(/\/\/.*$/gm, '');
    assert.ok(!/\.replaceChildren\(/.test(s), path.relative(PUBLIC, f));
  }
});

test('HTML 에 인라인 스크립트·스타일이 없다(CSP default-src self 와 맞춘다)', () => {
  const html = readFileSync(path.join(PUBLIC, 'index.html'), 'utf8');
  assert.ok(!/<script(?![^>]*\bsrc=)[^>]*>/.test(html), 'inline <script>');
  assert.ok(!/<style\b/.test(html), '<style>');
  assert.ok(!/\sstyle=/.test(html), 'style=');
  assert.ok(!/\son[a-z]+=/.test(html), 'on*=');
});
