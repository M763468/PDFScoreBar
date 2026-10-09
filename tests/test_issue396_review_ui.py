"""Static contract checks for the isolated user correction review entry."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "tools" / "review_correction"


def test_review_surface_separates_navigation_display_task_and_result_state():
    html = (UI / "index.html").read_text()
    for element_id in (
        "navigation",
        "displayControls",
        "context",
        "canvas",
        "statePanel",
        "correctionStatePanel",
        "applicationControls",
        "applyBtn",
        "openResultBtn",
        "itemList",
    ):
        assert f'id="{element_id}"' in html
    assert html.index('id="navigation"') < html.index('id="main"') < html.index('id="context"')
    assert 'id="correctionStatePanel"' in html and 'id="applicationStatus"' in html
    assert html.index('id="correctionStatePanel"') < html.index('id="applicationControls"')


def test_review_scripts_load_in_dependency_order_and_keep_legacy_canvas_hooks():
    html = (UI / "index.html").read_text()
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts == ["strings.js", "app.js", "correction_state.js"]
    app = (UI / "app.js").read_text()
    ids = set(re.findall(r'id="([^"]+)"', html))
    referenced_ids = set(re.findall(r'getElementById\("([^"]+)"\)', app))
    assert referenced_ids <= ids
    for behavior in ('"wheel"', '"keydown"', '"ArrowLeft"', '"ArrowRight"'):
        assert behavior in app
    assert "resetView" in app and "displayIndex(value)" in app


def test_reviewer_copy_is_controlled_and_task_operations_are_localized():
    html = (UI / "index.html").read_text()
    strings = (UI / "strings.js").read_text()
    app = (UI / "app.js").read_text()
    assert html.index('src="strings.js"') < html.index('src="app.js"')
    assert "window.ReviewStrings.operations" in app
    for key in ("title", "navigation", "task", "display", "status", "details", "noSelection"):
        assert f'{key}: "' in strings
    assert "Re-run evaluation separately" not in app


def test_controlled_copy_populates_primary_navigation_and_context_labels():
    import subprocess
    import textwrap

    html = (UI / "index.html").read_text()
    translator = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
    strings_js = (UI / "strings.js").read_text()
    script = textwrap.dedent(
        f"""
        const vm = require('node:vm');
        const fs = require('node:fs');
        const nodes = [
          {{dataset: {{copy: 'title'}}, textContent: ''}},
          {{dataset: {{copy: 'types.barline_construction'}}, textContent: ''}},
          {{dataset: {{copy: 'stage'}}, textContent: ''}},
        ];
        const context = {{window: {{}}, document: {{querySelectorAll: () => nodes}}}};
        vm.createContext(context);
        vm.runInContext({strings_js!r}, context);
        vm.runInContext({translator!r}, context);
        if (nodes.map(node => node.textContent).join('|') !== 'Review correction|Barline|Add change') process.exit(1);
        """
    )
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
