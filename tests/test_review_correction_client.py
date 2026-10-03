"""Exercise user state adapters with delayed saves and movement finalization."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario", ["save_edit", "navigation_edit", "export", "export_error"])
def test_user_adapter_keeps_async_state_contract(scenario):
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const scenario = process.argv[1];
function deferred() { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; }
const started = deferred(), complete = deferred();
const requests = [];
let recorded = [], pending = null, phase = 'before';
const node = () => ({setAttribute(){}, appendChild(){}, replaceChildren(){}, parentNode: {},
  addEventListener(){}, textContent: '', disabled: false});
const panel = node();
const context = {
  console, Map, Set, JSON, String, Promise,
  ReviewStrings: {state:{types:{}}, feedback:{}}, updateControlState(){},
  currentPage: {}, currentIndex: 0, dirtyTypes: new Set(), items: [{page:0, measure_span:2}],
  pageValue: () => 0, itemsForCurrentPage: () => context.items,
  document: {getElementById: () => panel, createElement: node},
  CustomEvent: function(name, init){this.detail = init.detail;},
  exportMovementBtn: node(), saveStatus: node(),
  releaseTransientInteraction(){}, unresolvedMovementSuggestionCount: () => 0,
  waitForMovementSaves: () => Promise.resolve(),
  loadPage(){context.loaded = true;}, loaded: false,
  setDirty(type, dirty){ if(dirty) context.dirtyTypes.add(type); else context.dirtyTypes.delete(type); },
  saveCorrectionPage: async (type, page, items) => {
    started.resolve(); await complete.promise;
    recorded = items; pending = null;
    return {output:'corrections/mmr.json'};
  },
  async fetch(url, options) {
    requests.push(url);
    if(url === '/api/state/pending') pending = JSON.parse(options.body).items;
    if(url === '/api/state/pending/clear') pending = null;
    if(url === '/api/export_movement_boundaries') {
      started.resolve(); await complete.promise;
      phase = scenario === 'export_error' ? 'error' : 'finished';
      return {ok: scenario !== 'export_error', status:400, json: async () => ({count:1})};
    }
    return {ok:true, json: async () => ({package:{status:phase, counts:{pending:0,recorded:0,error:0}, current_identity:{}}, states:[], labels:{}})};
  },
};
context.window = context;
context.dispatchEvent = () => {};
vm.createContext(context);
// Use the maintained save completion function rather than duplicating its behavior.
const appPath = fs.existsSync('tools/review_correction/app.js')
  ? 'tools/review_correction/app.js' : 'tools/gt_relabel_gui/app_manual.js';
const app = fs.readFileSync(appPath,'utf8');
vm.runInContext(app.slice(app.indexOf('function saveCorrectionType('),
  app.indexOf('function queueMovementSave(')), context);
context.saveCorrectionTypes = types => Promise.all(types.map(type => context.saveCorrectionType(type)));
vm.runInContext(fs.readFileSync('tools/review_correction/correction_state.js','utf8'), context);
(async () => {
 await context.reviewCorrectionState.ready();
 if(scenario === 'save_edit' || scenario === 'navigation_edit') {
   context.setDirty('mmr_measure_span', true);
   const saving = scenario === 'save_edit' ? context.saveCorrectionType('mmr_measure_span') : context.switchPage(1);
   await started.promise;
   context.items = [{page:0, measure_span:3}];
   context.setDirty('mmr_measure_span', true);
   complete.resolve(); await saving;
   await context.reviewCorrectionState.ready();
   assert.equal(recorded[0].measure_span, 2);
   assert.equal(pending[0].measure_span, 3);
   assert(context.dirtyTypes.has('mmr_measure_span'));
   assert(!requests.includes('/api/state/pending/clear'));
   if(scenario === 'navigation_edit') { assert.equal(context.currentIndex,0); assert(!context.loaded); }
   // A later save of the unchanged draft can clear it normally.
   await context.saveCorrectionType('mmr_measure_span');
   await context.reviewCorrectionState.ready();
   assert.equal(recorded[0].measure_span,3);
   assert.equal(pending,null);
   assert(!context.dirtyTypes.has('mmr_measure_span'));
 } else {
   requests.length = 0;
   const finishing = context.exportMovementBtn.onclick({currentTarget:{blur(){}}});
   await started.promise;
   await Promise.resolve();
   assert(!requests.includes('/api/state'), 'state refreshed before export settled');
   complete.resolve(); await finishing;
   await context.reviewCorrectionState.ready();
   assert(requests.includes('/api/state'));
   assert.equal(context.reviewCorrectionState.get().package.status,
     scenario === 'export_error' ? 'error' : 'finished');
 }
})().catch(error => {console.error(error); process.exitCode=1;});
"""
    result = subprocess.run(
        ["node", "-e", script, scenario], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr


def test_apply_controls_survive_state_panel_refresh():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const byId = new Map();
function node(initialId = '') {
  const value = {
    children: [], parentNode: null, textContent: '', disabled: false, hidden: false,
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
    replaceChildren() { this.children = []; },
    setAttribute() {}, addEventListener() {},
  };
  let id = '';
  Object.defineProperty(value, 'id', {
    get() { return id; },
    set(next) { id = next; if (next) byId.set(next, value); },
  });
  value.id = initialId;
  return value;
}
const sidebarHeader = node('sidebarHeader');
const correctionStatePanel = node('correctionStatePanel');
sidebarHeader.appendChild(correctionStatePanel);
const context = {
  console, Promise,
  ReviewStrings: {result: {apply: 'Generate PDF', open: 'Open PDF'}},
  document: {
    getElementById(id) { return byId.get(id) || null; },
    createElement() { return node(); },
  },
  reviewCorrectionState: {
    get() { return null; }, ready() { return Promise.resolve(); }, refresh() { return Promise.resolve(); },
  },
  addEventListener() {},
  fetch: async () => ({ok: true}),
  setInterval() { return 1; }, clearInterval() {},
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('tools/review_correction/apply_result.js','utf8'), context);
const controls = byId.get('applicationControls');
assert(controls);
assert.equal(controls.parentNode, sidebarHeader);
assert.notEqual(controls.parentNode, correctionStatePanel);
assert(sidebarHeader.children.includes(controls));
correctionStatePanel.replaceChildren();
assert(sidebarHeader.children.includes(controls));
assert.equal(byId.get('applyBtn').parentNode, controls);
assert.equal(byId.get('openResultBtn').parentNode, controls);
assert.equal(byId.get('applicationStatus').parentNode, controls);
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
