"""Generic imports: scoped access, preview, atomic commit and owner coexistence."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from uuid import uuid4

import pytest

from test_input_api import ApiFixture, replacement
import src.infra.market_units_input_repository as storage

IMPORT_TOKEN = 'scoped_import_test_credential_1234567890'


class ImportFixture:
    def __init__(self, tmp_path):
        self.api = ApiFixture(tmp_path)
        self.api.records.append(self.api.record(token=IMPORT_TOKEN, identifier='importer', subject='fake-source',
            permissions={'imports:read', 'imports:preview', 'imports:commit'}))
        self.api.save_credentials()
        self.initial = self.api.get()['body']
        self.asset = self.initial['items'][0]['asset_id']
        self.config = {'name': 'Fictional source', 'subject': 'fake-source', 'enabled': True,
                       'max_age_seconds': 3600, 'allow_unknown_as_of': False,
                       'targets': [{'asset_id': self.asset, 'quantity_unit': 'share', 'external_record_ids': ['record-a']}]}
        created = self.call('POST', 'input-sources', self.config, owner=True)
        assert created['status'] == 201, created
        self.source = created['body']

    def call(self, method, path, payload=None, owner=False, key=None):
        kwargs = {} if owner else {'token': IMPORT_TOKEN}
        result = self.api.request(method, path='/api/v1/' + path,
            body='' if payload is None else json.dumps(payload),
            headers={'Content-Type': 'application/json', 'Idempotency-Key': key or str(uuid4())}, **kwargs)
        if result['status'] < 300:
            spec = json.loads((Path(__file__).resolve().parents[2] / 'docs/reference/openapi-import-v1.json').read_text())
            parts = path.split('/')
            route = '/' + parts[0] + ('/{source_id}' if parts[0] == 'input-sources' else '/{batch_id}') if len(parts) > 1 else '/' + path
            if len(parts) > 2: route += '/' + parts[2]
            schema = spec['paths'][route][method.lower()]['responses'][str(result['status'])]['content']['application/json']['schema']
            registry = Registry().with_resource('urn:caption:imports', Resource(contents=spec, specification=DRAFT202012))
            Draft202012Validator(schema, registry=registry, _resolver=registry.resolver('urn:caption:imports')).validate(result['body'])
        return result

    def request(self, **changes):
        stamp = datetime.fromtimestamp(self.api.now, timezone.utc).isoformat()
        return {'source_id': self.source['id'], 'source_run_id': str(uuid4()),
                'mapping_version': 'test-1', 'base_revision': self.api.get()['body']['revision'],
                'sequence': 1, 'collected_at': stamp, 'as_of': stamp, 'enumeration_complete': True,
                'items': [{'asset_id': self.asset, 'quantity': '123', 'quantity_unit': 'share',
                           'external_record_ids': ['record-a']}], **changes}

    def preview(self, **changes):
        result = self.call('POST', 'import-batches', self.request(**changes))
        assert result['status'] == 201, result
        return result['body']

    def commit(self, batch, **kwargs):
        return self.call('POST', f"import-batches/{batch['id']}/commit", {'diff_hash': batch['diff_hash']}, **kwargs)


@pytest.fixture
def imp(tmp_path):
    return ImportFixture(tmp_path)


def test_scoped_preview_commit_replay_and_history(imp):
    before = imp.api.csv_path.read_bytes()
    positions = imp.call('GET', f"input-sources/{imp.source['id']}/positions")
    assert positions['status'] == 200
    assert positions['body']['items'] == [{'asset_id': imp.asset, 'quantity': imp.initial['items'][0]['units']}]
    assert imp.api.request(token=IMPORT_TOKEN)['status'] == 403
    assert imp.call('GET', 'input-sources')['status'] == 403
    batch = imp.preview()
    assert imp.api.csv_path.read_bytes() == before
    assert batch['diff'][0]['after'] == '123'
    key = str(uuid4())
    result = imp.commit(batch, key=key)
    assert result['status'] == 200 and result['body']['changed'] is True
    imp.api.reopen()
    assert imp.commit(batch, key=key)['body'] == result['body']
    assert imp.commit(batch)['body'] == result['body']
    saved = imp.api.get()['body']
    expected = deepcopy(imp.initial['items']); expected[0]['units'] = '123'
    assert saved['items'] == expected
    history = imp.call('GET', f"input-sources/{imp.source['id']}/batches")
    assert history['body']['batches'] == [result['body']]
    with imp.api.repository.transaction() as session:
        assert len(session.state['changes']) == 1
        assert session.state['changes'][0]['source_id'] == imp.source['id']


def test_no_change_and_zero_are_not_deletion(imp):
    batch = imp.preview(items=[{'asset_id': imp.asset, 'quantity': imp.initial['items'][0]['units'],
                              'quantity_unit': 'share', 'external_record_ids': ['record-a']}])
    raw = imp.api.csv_path.read_bytes()
    result = imp.commit(batch)
    assert result['body']['changed'] is False and result['body']['change_id'] is None
    assert imp.api.csv_path.read_bytes() == raw
    imp.api.now += 1
    batch = imp.preview(sequence=2, items=[{'asset_id': imp.asset, 'quantity': '0',
                       'quantity_unit': 'share', 'external_record_ids': ['record-a']}])
    assert imp.commit(batch)['status'] == 200
    saved = imp.api.get()['body']
    assert saved['items'][0]['units'] == '0' and len(saved['items']) == 2


@pytest.mark.parametrize('bad', [None, True, 1, '1e2', '-1', 'NaN', '01', '1.0000000000001'])
def test_rejects_invalid_quantity(imp, bad):
    payload = imp.request(); payload['items'][0]['quantity'] = bad
    assert imp.call('POST', 'import-batches', payload)['status'] == 422
    assert imp.api.get()['body'] == imp.initial


@pytest.mark.parametrize('mutation', ['missing', 'unit', 'records', 'unknown', 'incomplete', 'stale', 'future', 'unknown_time'])
def test_rejects_incomplete_or_untrusted_input(imp, mutation):
    payload = imp.request()
    if mutation == 'missing': payload['items'] = []
    if mutation == 'unit': payload['items'][0]['quantity_unit'] = 'lot'
    if mutation == 'records': payload['items'][0]['external_record_ids'] = []
    if mutation == 'unknown': payload['items'][0]['asset_id'] = imp.initial['items'][1]['asset_id']
    if mutation == 'incomplete': payload['enumeration_complete'] = False
    if mutation == 'stale': payload['collected_at'] = '2020-01-01T00:00:00+00:00'
    if mutation == 'future': payload['as_of'] = '2099-01-01T00:00:00+00:00'
    if mutation == 'unknown_time': payload['as_of'] = None
    assert imp.call('POST', 'import-batches', payload)['status'] == 422
    assert imp.api.get()['body'] == imp.initial


def test_manual_override_requires_owner_resume_and_new_preview(imp):
    batch = imp.preview()
    current = imp.api.get(); payload = replacement(current['body']); payload['items'][0]['units'] = '77'
    assert imp.api.put(payload, current['headers']['ETag'])['status'] == 200
    assert imp.commit(batch)['status'] == 412
    source = imp.call('GET', 'input-sources/' + imp.source['id'], owner=True)['body']
    assert source['manual_override'] == [imp.asset]
    assert imp.call('POST', 'import-batches', imp.request())['body']['code'] == 'source_paused'
    body = {'base_source_revision': source['revision'], 'config': imp.config, 'resume_ids': [imp.asset]}
    assert imp.call('PUT', 'input-sources/' + source['id'], body)['status'] == 403
    assert imp.call('PUT', 'input-sources/' + source['id'], body, owner=True)['status'] == 200
    assert imp.commit(imp.preview())['status'] == 200


def test_source_change_conflict_and_credential_revocation(imp):
    batch = imp.preview()
    changed = {**imp.config, 'enabled': False}
    body = {'base_source_revision': imp.source['revision'], 'config': changed, 'resume_ids': []}
    assert imp.call('PUT', 'input-sources/' + imp.source['id'], body, owner=True)['status'] == 200
    assert imp.commit(batch)['status'] == 412
    imp.api.records[1]['revoked'] = True; imp.api.save_credentials()
    assert imp.commit(batch)['status'] == 401


def test_cancel_run_reuse_hash_conflict_and_order(imp):
    payload = imp.request(); key = str(uuid4())
    first = imp.call('POST', 'import-batches', payload, key=key)
    assert imp.call('POST', 'import-batches', payload)['body'] == first['body']
    other = deepcopy(payload); other['items'][0]['quantity'] = '456'
    assert imp.call('POST', 'import-batches', other, key=key)['body']['code'] == 'idempotency_key_reused'
    assert imp.call('POST', 'import-batches', other)['body']['code'] == 'source_run_reused'
    batch = first['body']
    assert imp.call('POST', f"import-batches/{batch['id']}/commit", {'diff_hash': 'bad'})['status'] == 412
    assert imp.call('POST', f"import-batches/{batch['id']}/cancel", {'diff_hash': batch['diff_hash']})['status'] == 200
    assert imp.commit(batch)['body']['code'] == 'batch_cancelled'
    assert imp.commit(imp.preview())['status'] == 200
    assert imp.call('POST', 'import-batches', imp.request())['body']['code'] == 'stale_import'


@pytest.mark.parametrize('stage', ['pending.json', 'market_units.csv', 'state.json'])
def test_commit_recovers_quantity_and_batch_together(imp, monkeypatch, stage):
    batch = imp.preview(); key = str(uuid4())
    original = storage._replace_bytes
    tripped = False
    def interrupt(path, content, **kwargs):
        nonlocal tripped
        original(path, content, **kwargs)
        if path.name == stage and not tripped:
            tripped = True
            raise OSError('simulated stop')
    monkeypatch.setattr(storage, '_replace_bytes', interrupt)
    assert imp.commit(batch, key=key)['status'] == 503
    monkeypatch.setattr(storage, '_replace_bytes', original)
    imp.api.reopen()
    result = imp.commit(batch, key=key)
    assert result['status'] == 200 and result['body']['status'] == 'committed'
    assert imp.api.get()['body']['items'][0]['units'] == '123'
    assert len(imp.api.state()['changes']) == 1


def test_two_previews_cannot_overwrite_each_other(imp):
    from concurrent.futures import ThreadPoolExecutor
    first = imp.preview()
    second = imp.preview(sequence=2, items=[{'asset_id': imp.asset, 'quantity': '456',
                         'quantity_unit': 'share', 'external_record_ids': ['record-a']}])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(imp.commit, [first, second]))
    assert sorted(r['status'] for r in results) in ([200, 409], [200, 412])
    assert len(imp.api.state()['changes']) == 1


def test_permissions_are_rechecked_after_waiting_for_lock(imp, monkeypatch):
    from contextlib import contextmanager
    batch = imp.preview()
    original = imp.api.repository.transaction
    @contextmanager
    def changed_credentials():
        with original() as session:
            imp.api.records[1]['permissions'] = ['imports:read']
            imp.api.save_credentials()
            yield session
    monkeypatch.setattr(imp.api.repository, 'transaction', changed_credentials)
    assert imp.commit(batch)['status'] == 403
    assert imp.api.get()['body'] == imp.initial


def test_other_subject_and_removed_targets_cannot_read_history(imp):
    batch = imp.preview()
    imp.api.records[1]['subject'] = 'other-source'; imp.api.save_credentials()
    assert imp.call('GET', f"import-batches/{batch['id']}")['status'] == 403
    imp.api.records[1]['subject'] = 'fake-source'; imp.api.save_credentials()
    config = deepcopy(imp.config); config['targets'][0]['asset_id'] = imp.initial['items'][1]['asset_id']
    updated = imp.call('PUT', 'input-sources/' + imp.source['id'],
                      {'base_source_revision': imp.source['revision'], 'config': config, 'resume_ids': []}, owner=True)
    assert updated['status'] == 200
    assert imp.call('GET', f"import-batches/{batch['id']}")['status'] == 403
    assert imp.call('GET', f"import-batches/{batch['id']}", owner=True)['status'] == 200
    assert imp.call('GET', f"input-sources/{imp.source['id']}/batches")['body']['batches'] == []


def test_commit_rechecks_freshness_and_receipt_expiry(imp):
    batch = imp.preview()
    imp.api.now += 3601
    assert imp.commit(batch)['status'] == 422
    fresh = imp.preview()
    key = str(uuid4())
    committed = imp.commit(fresh, key=key)
    assert committed['status'] == 200
    imp.api.now += 31 * 86400
    assert imp.commit(fresh, key=key)['body']['code'] == 'idempotency_result_expired'
    assert imp.call('GET', f"import-batches/{fresh['id']}")['body'] == committed['body']


def test_worker_transport_commits_persisted_preview(imp):
    import os
    import subprocess
    import sys
    import time
    imp.api.now = time.time()
    batch = imp.preview()
    packet = {'id': 'commit', 'method': 'POST', 'path': f"/api/v1/import-batches/{batch['id']}/commit",
              'headers': {'Authorization': 'Bearer ' + IMPORT_TOKEN, 'Content-Type': 'application/json',
                          'Idempotency-Key': str(uuid4())}, 'body': json.dumps({'diff_hash': batch['diff_hash']})}
    env = {k: v for k, v in os.environ.items() if k != 'CAPTION_PERSONAL_UI_ORIGINS'}
    env['CAPTION_API_CREDENTIALS_FILE'] = str(imp.api.credentials_path)
    result = subprocess.run([sys.executable, '-m', 'src.app.entrypoints.input_api_worker', '--csv-path', str(imp.api.csv_path)],
                            input=json.dumps(packet) + '\n', text=True, capture_output=True, env=env, timeout=20)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response['status'] == 200 and response['body']['status'] == 'committed', response
    assert imp.api.get()['body']['items'][0]['units'] == '123'
