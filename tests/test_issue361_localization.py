"""Focused checks for the reviewer-facing English/Japanese language switch."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "tools" / "review_correction"


def test_language_switch_updates_copy_and_keeps_user_entered_reason():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const html = fs.readFileSync('tools/review_correction/index.html', 'utf8');
const inline = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
  .map(match => match[1]).filter(Boolean);
const textNodes = [
  {dataset: {copy: 'title'}, textContent: ''},
  {dataset: {copy: 'types.barline_construction'}, textContent: ''},
];
const ariaNodes = [{dataset: {copyAria: 'aria.pages'}, setAttribute(name, value) { this[name] = value; }}];
const placeholderNodes = [{dataset: {copyPlaceholder: 'ui.systemPlaceholder'}, setAttribute(name, value) { this[name] = value; }}];
const reason = {dataset: {copyDefault: 'ui.reasonDefault'}, value: 'manual correction'};
const selector = {value: '', addEventListener(name, handler) { this.onchange = handler; }};
const context = {
  document: {
    title: '', documentElement: {lang: ''},
    querySelectorAll(query) {
      return {'[data-copy]': textNodes, '[data-copy-aria]': ariaNodes,
        '[data-copy-placeholder]': placeholderNodes, '[data-copy-default]': [reason]}[query] || [];
    },
    getElementById(id) { return id === 'languageSelect' ? selector : null; },
  },
  localStorage: new Map(),
  CustomEvent: function(name, init) { this.type = name; this.detail = init.detail; },
  dispatchEvent(event) { this.lastEvent = event; },
};
context.window = context;
context.localStorage = {
  getItem(key) { return values.get(key) || null; },
  setItem(key, value) { values.set(key, value); },
};
const values = new Map();
vm.createContext(context);
vm.runInContext(fs.readFileSync('tools/review_correction/strings.js', 'utf8'), context);
inline.forEach((source, index) => vm.runInContext(source, context, {filename: `review-inline-${index}.js`}));
assert.equal(textNodes[0].textContent, 'Review correction');
assert.equal(reason.value, 'manual correction');
selector.value = 'ja';
selector.onchange({target: selector});
assert.equal(context.document.documentElement.lang, 'ja');
assert.equal(context.document.title, '結果を確認・修正');
assert.equal(textNodes[0].textContent, '結果を確認・修正');
assert.equal(textNodes[1].textContent, '小節線');
assert.equal(ariaNodes[0]['aria-label'], '結果ページ');
assert.equal(placeholderNodes[0].placeholder, '例：6');
assert.equal(reason.value, '手動修正');
assert.equal(values.get('review-correction-language'), 'ja');
reason.value = 'reviewer supplied note';
selector.value = 'en';
selector.onchange({target: selector});
assert.equal(reason.value, 'reviewer supplied note');
assert.equal(textNodes[0].textContent, 'Review correction');
assert.equal(context.lastEvent.type, 'review-language-changed');
"""
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert completed.returncode == 0, completed.stderr


def test_language_catalogs_have_the_same_nested_string_surface():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const context = {window: {}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('tools/review_correction/strings.js', 'utf8'), context);
const {en, ja} = context.window.ReviewStringCatalogs;
assert.equal(ja.types.mmr_measure_span, '複数小節休符（MMR）');
assert.equal(ja.measureSpan, '複数小節休符の小節数');
assert.equal(ja.operations.mmr_measure_span[0][1], '複数小節休符の小節数を設定');
assert.equal(ja.operations.mmr_measure_span[1][1], '複数小節休符として扱わない');
function keys(value, prefix = '') {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return child && typeof child === 'object' && !Array.isArray(child)
      ? [path, ...keys(child, path)] : [path];
  }).sort();
}
assert.equal(JSON.stringify(keys(en)), JSON.stringify(keys(ja)));
"""
    completed = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert completed.returncode == 0, completed.stderr


def test_language_switch_rerenders_without_resetting_the_current_operation_or_target():
    app = (UI / "app.js").read_text(encoding="utf-8")
    start = app.index('window.addEventListener("review-language-changed", () => {')
    end = app.index("\n\nprevBtn.onclick", start)
    listener = app[start:end]
    assert "updateOps(true)" in listener
    assert "renderItems()" in listener
    assert "updateSelectionMeta()" in listener
    assert "renderPageList()" in listener
