"""Opaque revision compatibility across all three input resources."""
from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from test_input_api import ApiFixture, item, replacement
from test_monthly_input_api import MonthlyApi


@pytest.mark.parametrize('resource', ['market-units', 'external-assets', 'portfolio-basis'])
@pytest.mark.parametrize('existing', [False, True])
def test_revision_lifecycle_and_legacy_compatibility(tmp_path, resource, existing):
    market = resource == 'market-units'
    api = ApiFixture(tmp_path) if market else MonthlyApi(tmp_path, resource)
    repository = api.repository if market else api.repo
    data_file = api.csv_path if market else api.file
    if market and not existing:
        data_file.unlink()
    elif market:
        # Use canonical decimals so unchanged PUT does not normalize legacy 2.5000.
        data_file.write_text(data_file.read_text().replace('2.5000', '2.5'))
    elif existing:
        row = {k: v for k, v in api.row().items() if k != 'entry_id'}
        data_file.write_text(json.dumps({'default': {'items': [row]} if resource == 'external-assets' else row}))
    spec = json.loads((Path(__file__).resolve().parents[2] / 'docs/reference/openapi-v1.json').read_text())
    uri = 'urn:caption:openapi'
    registry = Registry().with_resource(uri, Resource(contents=spec, specification=DRAFT202012))

    def validate(result, method):
        assert result['status'] == 200, result
        schema = spec['paths']['/' + resource][method]['responses']['200']['content']['application/json']['schema']
        Draft202012Validator({'$ref': uri + schema['$ref']}, registry=registry).validate(result['body'])

    def payload(document):
        return replacement(document) if market else {'months': deepcopy(document['months']), 'clear_all': False}

    initial = api.get()
    validate(initial, 'get')
    assert str(UUID(initial['body']['revision'])) == initial['body']['revision']
    # Seed a historical ID through the durable metadata transaction, preserving source bytes.
    with repository.transaction() as session:
        session.state['document']['revision'] = 'rev_legacy_3'
        # Fixture setup emulates an already persisted historical document.
        # Ordinary document changes remain subject to the repository write guard.
        if market:
            session._original_document = deepcopy(session.state['document'])
        else:
            session.original_document = deepcopy(session.state['document'])
        session.commit()
    old = api.get()
    validate(old, 'get')
    assert old['body']['revision'] == 'rev_legacy_3'
    source = data_file.read_bytes() if data_file.exists() else None
    if existing:
        key = legacy_key = str(uuid4())
        unchanged = api.put(payload(old['body']), old['headers']['ETag'], key=key)
        validate(unchanged, 'put')
        assert unchanged['body']['changed'] is False
        assert unchanged['body']['resource']['revision'] == 'rev_legacy_3'
        assert data_file.read_bytes() == source
        assert api.put(payload(old['body']), old['headers']['ETag'], key=key)['body'] == unchanged['body']
    changed_payload = {'items': [item(units='3')], 'clear_all': False} if market else api.payload(api.row('3'))
    key = str(uuid4())
    changed = api.put(changed_payload, old['headers']['ETag'], key=key)
    validate(changed, 'put')
    new_id = changed['body']['resource']['revision']
    assert str(UUID(new_id)) == new_id
    assert changed['body']['changed'] is True
    # Replay precedes the stale ETag check; a new request must still conflict.
    replay = api.put(changed_payload, old['headers']['ETag'], key=key)
    validate(replay, 'put')
    assert replay['body'] == changed['body']
    assert api.put(changed_payload, old['headers']['ETag'])['status'] == 412
    latest = api.get()
    validate(latest, 'get')
    assert latest['body']['revision'] == new_id
    unchanged = api.put(payload(latest['body']), latest['headers']['ETag'])
    validate(unchanged, 'put')
    assert unchanged['body']['changed'] is False
    assert unchanged['body']['resource']['revision'] == new_id
    with repository.transaction() as session:
        assert session.state['changes'][-1]['before']['revision'] == 'rev_legacy_3'
    if existing:
        # The old receipt survives a subsequent update without rewriting its revision.
        result = api.put(payload(old['body']), old['headers']['ETag'], key=legacy_key)
        validate(result, 'put')
        assert result['body']['resource']['revision'] == 'rev_legacy_3'
        assert result['body']['changed'] is False
