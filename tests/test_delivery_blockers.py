"""Synthetic-only regressions for material-level structural blocker feedback."""
from __future__ import annotations
import io
import json
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import http.cookiejar
import zipfile
from pathlib import Path

import pytest

from cloak.issues import (
    GENERIC_STRUCTURAL_BLOCKER_MESSAGE,
    SOFT_ISSUES,
    describe_issue,
    issue_details,
    required_soft_confirmations,
    structural_blockers,
)
from cloak.workflow import review_update
from fixtures import docx

REQUIRED_CODES = (
    'UNSUPPORTED_EMBEDDED_OR_DYNAMIC_PART',
    'UNSUPPORTED_BINARY_PART',
    'UNSUPPORTED_XML_TAIL',
    'SENSITIVE_FORMULA_BLOCKED',
    'SENSITIVE_REFERENCE_BLOCKED',
    'SENSITIVE_NUMERIC_WITH_FORMULAS',
    'XML_DTD_FORBIDDEN',
    'MULTIFRAME_IMAGE',
)
PASSWORD = 'SYNTHETIC-blocker-password-2026'


def test_all_required_issue_codes_have_structural_chinese_explanations():
    for code in REQUIRED_CODES:
        detail = describe_issue(code)
        assert detail['code'] == code
        assert detail['severity'] == 'structural'
        assert detail['message'] != GENERIC_STRUCTURAL_BLOCKER_MESSAGE
        assert len(detail['message']) >= 12


def test_unknown_code_is_preserved_and_fails_closed():
    detail = describe_issue('FUTURE_SYNTHETIC_CODE')
    assert detail == {
        'code': 'FUTURE_SYNTHETIC_CODE',
        'severity': 'structural',
        'message': GENERIC_STRUCTURAL_BLOCKER_MESSAGE,
    }


def test_soft_classification_is_shared_with_workflow_and_not_a_blocker():
    soft = issue_details(['IMAGE_VISUAL_REVIEW', 'RULE_ONLY_DETECTION'])
    assert {item['code'] for item in soft} == {'IMAGE_VISUAL_REVIEW', 'RULE_ONLY_DETECTION'}
    assert all(item['severity'] == 'soft' for item in soft)
    assert all(item['code'] in SOFT_ISSUES for item in soft)
    files = [{'source': 'synthetic.txt', 'issues': ['IMAGE_VISUAL_REVIEW', 'RULE_ONLY_DETECTION', 'UNSUPPORTED_BINARY_PART']}]
    assert structural_blockers([{'source': 'synthetic.txt', 'issues': ['IMAGE_VISUAL_REVIEW']}]) == []
    assert required_soft_confirmations(files) == ['IMAGE_VISUAL_REVIEW', 'RULE_ONLY_DETECTION']


def test_structural_blockers_are_per_file_and_keep_original_codes():
    files = [
        {'local_label': 'synthetic-one.docx', 'source': '/tmp/one', 'issues': ['UNSUPPORTED_BINARY_PART']},
        {'local_label': 'synthetic-two.xlsx', 'source': '/tmp/two', 'issues': ['SENSITIVE_FORMULA_BLOCKED', 'UNKNOWN_SYNTHETIC']},
    ]
    rows = structural_blockers(files)
    assert [(row['file_index'], row['file_name'], row['code']) for row in rows] == [
        (0, 'synthetic-one.docx', 'UNSUPPORTED_BINARY_PART'),
        (1, 'synthetic-two.xlsx', 'SENSITIVE_FORMULA_BLOCKED'),
        (1, 'synthetic-two.xlsx', 'UNKNOWN_SYNTHETIC'),
    ]
    assert rows[-1]['message'] == GENERIC_STRUCTURAL_BLOCKER_MESSAGE


def test_review_update_still_rejects_hard_blocker_even_with_all_soft_confirmations():
    job = {
        'files': [{'units': [], 'issues': ['UNSUPPORTED_BINARY_PART']}],
        'scenario': {},
        'reviewed': False,
        'status': 'NEEDS_REVIEW',
    }
    with pytest.raises(ValueError, match='UNRESOLVED_STRUCTURAL_BLOCKERS'):
        review_update(job, confirmations=list(SOFT_ISSUES))
    assert job['reviewed'] is False
    assert job['status'] == 'NEEDS_REVIEW'


def _inject_unsupported_binary(path: Path) -> None:
    """Add a synthetic unsupported OOXML binary part; never uses user material."""
    original = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(original), 'r') as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as target:
        for info, content in entries:
            target.writestr(info, content)
        target.writestr('word/embeddings/synthetic-object.bin', b'\x00synthetic-test-only')


def test_desktop_lists_blocker_before_export_and_confirms_cannot_bypass(tmp_path):
    from cloak.desktop import serve

    path = tmp_path / 'synthetic-unsupported.docx'
    docx(path)
    _inject_unsupported_binary(path)

    started = threading.Event()
    record = {}

    def ready(url, server):
        record.update(url=url, server=server)
        started.set()

    thread = threading.Thread(
        target=lambda: serve(open_browser=False, ready=ready, home=tmp_path / 'tasks'),
        daemon=True,
    )
    thread.start()
    assert started.wait(15), 'synthetic desktop server did not start'
    base = record['url'].split('/?')[0]
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def post(route, data):
        req = urllib.request.Request(
            base + route,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Origin': base, 'X-CSRF': csrf[0]},
        )
        return client.open(req)

    csrf = ['']
    try:
        client.open(record['url']).read()
        state = json.load(client.open(base + '/state'))
        csrf[0] = state['csrf']
        post('/paths', {'paths': [str(path)]}).read()
        post('/scan', {
            'scenario': {'organization': 'single'},
            'password': PASSWORD,
            'password_again': PASSWORD,
            'dictionary': {},
        }).read()

        for _ in range(150):
            state = json.load(client.open(base + '/state'))
            if state['status'] != 'BUSY':
                break
            time.sleep(0.2)
        assert state['status'] == 'REVIEW', state.get('error')
        assert len(state['blockers']) >= 1
        assert all(row['file_name'] == 'synthetic-unsupported.docx' for row in state['blockers'])
        codes = {row['code'] for row in state['blockers']}
        assert 'UNSUPPORTED_BINARY_PART' in codes
        assert all(row['message'] for row in state['blockers'])

        review = json.load(client.open(base + '/review?fi=0'))
        details = {item['code']: item for item in review['issue_details']}
        assert details['UNSUPPORTED_BINARY_PART']['severity'] == 'structural'
        assert details['UNSUPPORTED_BINARY_PART']['message']

        post('/seen', {'fi': 0, 'confirmed': True}).read()
        # Even every soft confirmation cannot override a structural hard blocker.
        request = urllib.request.Request(
            base + '/export',
            data=json.dumps({'confirmations': sorted(SOFT_ISSUES)}).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Origin': base, 'X-CSRF': csrf[0]},
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            client.open(request)
        assert caught.value.code == 400
        error = json.loads(caught.value.read())
        assert '不能' in error['error'] or '阻断' in error['error']
        assert error['blockers']
        assert error['blockers'][0]['file_name'] == 'synthetic-unsupported.docx'
        state = json.load(client.open(base + '/state'))
        assert state['status'] == 'REVIEW'
        assert state['task']['reviewed'] is False
        assert state.get('result') is None
    finally:
        record['server'].shutdown()
        thread.join(15)


def test_delivery_page_real_js_lists_escapes_and_routes_blockers():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is optional; Python/API contract tests still run')
    root = Path(__file__).resolve().parents[1]
    harness = Path(__file__).with_name('test_delivery_ui.js')
    app = root / 'assets' / 'ui' / 'app.js'
    subprocess.run([node, str(harness), str(app)], check=True, capture_output=True, text=True)


def test_delivery_frontend_consumes_backend_catalog_and_escapes_all_display_fields():
    root = Path(__file__).resolve().parents[1]
    app = (root / 'assets' / 'ui' / 'app.js').read_text('utf-8')
    desktop = (root / 'scripts' / 'cloak' / 'desktop.py').read_text('utf-8')
    assert "state.blockers" in app
    assert "w.structural_blockers(j['files'])" in desktop
    assert "w.issue_details(f['issues'])" in desktop
    assert "w.required_soft_confirmations(j['files'])" in desktop
    assert "esc(label)" in app and "esc(b.message" in app and "esc(b.code" in app
    assert "review.issue_details" in app
    assert "confirmations:state.soft_confirmations||[]" in app
    assert "confirmations:['ENTITY_AMBIGUITY_REVIEW'" not in app
    assert "UNSUPPORTED_EMBEDDED_OR_DYNAMIC_PART','UNSUPPORTED_BINARY_PART" not in app
