"""Exercise user state adapters with delayed saves and movement finalization."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_compact_save_status_keeps_errors_visible_and_details_open_on_refresh():
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const node = () => ({children:[],textContent:'',open:false,
  appendChild(child){this.children.push(child);},replaceChildren(){this.children=[];}});
const panel=node(), details=node();
const context={window:{},panel,latestState:null,currentPage:{},pageValue:()=>0,
  document:{createElement:node,getElementById:id=>id==='correctionStateDetails'?details:id==='statePanel'?{}:null},
  CustomEvent:function(name, init){this.detail=init.detail;}};
context.window.dispatchEvent=()=>{};
vm.createContext(context);
vm.runInContext(fs.readFileSync('tools/review_correction/strings.js','utf8'),context);
const source=fs.readFileSync('tools/review_correction/correction_state.js','utf8');
vm.runInContext(source.slice(source.indexOf('  function render(state)'),source.indexOf('  async function refresh()')),context);
const state={package:{status:'mixed',counts:{pending:1,recorded:1,error:1}},states:[
  {page:0,correction_type:'mmr_measure_span',edit_status:'pending',recording_status:'recorded'},
  {page:0,correction_type:'barline_construction',edit_status:'none',recording_status:'recorded',error:'disk full'},
  {page:1,correction_type:'mmr_measure_span',edit_status:'none',recording_status:'recorded'},
]};
context.render(state);
assert.equal(panel.children.length,2,'summary and error remain visible');
assert(panel.children[1].textContent.includes('disk full'));
assert.equal(details.children.length,1,'only current-page routine detail is folded');
assert(panel.children[0].textContent.includes('1 '+context.window.ReviewStrings.state.pending));
details.open=true;
context.render(state);
assert(details.open,'polling must not close expanded details');
assert.equal(details.children.length,1,'polling must replace rather than duplicate rows');
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr


def test_canvas_hit_testing_uses_rendered_size_for_both_axes():
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync('tools/review_correction/app.js', 'utf8');
const context = {
  canvas: {width:1200, height:900,
    getBoundingClientRect: () => ({left:200, top:100, width:600, height:300})},
  viewScale: .25, viewOffset: {x:30, y:15},
};
vm.createContext(context);
for (const name of ['canvasPoint','canvasToImg']) {
  const match = source.match(new RegExp('function ' + name + '\\([\\s\\S]*?\\n}'));
  vm.runInContext(match[0], context);
}
for (const [x, y] of [[100,100],[900,2800]]) {
  const event = {clientX:200+(x*.25+30)/2, clientY:100+(y*.25+15)/3};
  const hit = context.canvasToImg(context.canvasPoint(event));
  assert(Math.abs(hit.x-x)<1e-9); assert(Math.abs(hit.y-y)<1e-9);
}
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr


def test_rest_review_entry_includes_misses_and_unflagged_reads_without_rewriting_edits():
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const rows = [], pending = new Set(['barline_construction']);
const edits = [{page:0, system:0, measure:2, op:'set_measure_span', measure_span:4}];
const context = {
  window: {}, Map, Set,
  typeSelect: {value:'barline_construction'}, opSelect: {value:'remove_barline', appendChild(node){this.value ||= node.value;}},
  selectedItemIndex: 1, currentType: () => context.typeSelect.value,
  currentOp: () => context.opSelect.value,
  releaseTransientInteraction(){},
  pageValue: () => 0, selectedMeasureKey: () => null,
  measureKey: (p,s,m) => `${p}:${s}:${m}`,
  displayIndex: value => value + 1,
  itemsForCurrentPage: type => type === 'mmr_measure_span' ? edits : [],
  // Include a missed rest (no OCR override), an unflagged high-confidence
  // wrong count, and an already edited measure. None may be hidden by this route.
  measures: [0,1,2].map(measure => ({system:0, measure})),
  baseMmrOverrides: [{page:0,system:0,measure:1,skip:36,confidence:.999}],
  itemList: {appendChild(node){rows.push(node);}},
  dirtyTypes: pending,
  details: {open:false},
  document: {createElement: () => ({setAttribute(){}}), getElementById: () => context.details},
  selectMeasure: measure => {context.selected = measure;},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('tools/review_correction/strings.js','utf8'), context);
context.window.ReviewStrings = context.window.ReviewStringCatalogs.en;
context.reviewerCopy = (key, args) => JSON.stringify(args);
const source = fs.readFileSync('tools/review_correction/app.js','utf8');
for (const [start,end] of [
  ['function baseMmrMap(', 'function updateSelectionMeta('],
  ['function renderMmrRows(', 'function movementCandidateAt('],
  ['function updateOps(', 'function updateControlState('],
  ['function startRestCountReview(', 'function switchPage('],
]) vm.runInContext(source.slice(source.indexOf(start),source.indexOf(end)), context);
Object.defineProperty(context.opSelect, 'innerHTML', {set(){this.value = '';}});
context.updateControlState = () => {rows.length = 0; context.renderMmrRows();};
const before = JSON.stringify(edits);
context.startRestCountReview();
assert.equal(context.typeSelect.value, 'mmr_measure_span');
assert.equal(context.opSelect.value, 'set_measure_span');
assert(context.details.open);
assert.equal(rows.length, 3);
assert.deepEqual(rows.map(row => JSON.parse(row.textContent).effective), [1,37,4]);
assert.equal(JSON.stringify(edits), before);
assert(pending.has('barline_construction'));
rows[0].onclick();
assert.equal(context.selected.measure, 0, 'missed rest must remain selectable');
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr


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
  addEventListener(){}, setInterval(){return 1;}, clearInterval(){},
  ReviewStrings: {state:{types:{}}, feedback:{}, result:{}}, updateControlState(){},
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
const source = fs.readFileSync('tools/review_correction/correction_state.js','utf8');
vm.runInContext(source.slice(source.indexOf('/* Apply controls')), context);
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


def test_stale_numbering_preview_responses_cannot_restore_invalidated_results():
    script = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const source = fs.readFileSync('tools/review_correction/app.js', 'utf8');
function deferred() { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; }
function makeContext() {
  const requests = [];
  const button = {attributes:{}, setAttribute(name, value){this.attributes[name] = value;}};
  const context = {
    Map, String, Object, Promise,
    provisionalNumbering: new Map(), provisionalNumberingVisible: false,
        provisionalNumberingRevision: 0, numberingPreviewRequestId: 0,
    previewNumbersBtn: button, saveStatus: {textContent:''},
    reviewerCopy: key => key, draw(){},
    waitForMovementSaves: async () => {}, saveDirtyTypes: async () => {},
    fetch: () => { const request = deferred(); requests.push(request); return request.promise; },
  };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function invalidateProvisionalNumbering()'),
    source.indexOf('function updateDirtyStatus()')), context);
  const handlerStart = source.indexOf('previewNumbersBtn.onclick = async () => {');
  const handlerEnd = source.indexOf('\n\ncanvas.addEventListener', handlerStart);
  vm.runInContext(source.slice(handlerStart, handlerEnd), context);
  return {context, requests};
}
function response(number) {
  return {ok:true, json:async () => ({pages:[{page:0, systems:[{system:0, number}]}]})};
}
async function waitForRequests(requests, count) {
  for (let i = 0; i < 20 && requests.length < count; i++) await Promise.resolve();
  assert.equal(requests.length, count, 'preview request should start');
}
(async () => {
  {
    const {context, requests} = makeContext();
    const pending = context.previewNumbersBtn.onclick();
    await waitForRequests(requests, 1);
    context.invalidateProvisionalNumbering();
    context.saveStatus.textContent = 'edited';
    requests[0].resolve(response(1));
    await pending;
    assert.equal(vm.runInContext('provisionalNumberingVisible', context), false);
    assert.equal(context.previewNumbersBtn.attributes['aria-pressed'], 'false');
    assert.equal(context.saveStatus.textContent, 'edited');
    assert.equal(vm.runInContext('provisionalNumbering.size', context), 0);
  }
  {
    const {context, requests} = makeContext();
    const older = context.previewNumbersBtn.onclick();
    await waitForRequests(requests, 1);
    const newer = context.previewNumbersBtn.onclick();
    await waitForRequests(requests, 2);
    requests[1].resolve(response(2));
    await newer;
    requests[0].resolve(response(1));
    await older;
    assert.equal(vm.runInContext('provisionalNumberingVisible', context), true);
    assert.equal(vm.runInContext('provisionalNumbering.get("0").get("0").number', context), 2);
    assert.equal(context.saveStatus.textContent, 'ui.previewReady');
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
