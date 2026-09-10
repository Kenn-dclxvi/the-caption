"""Source-scoped import orchestration using the existing Market Units journal."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from src.app.input_api import ApiError, RECEIPT_SECONDS, response, strict_json
from src.domain.quantity_import import ImportValidationError, source_config, batch_payload, identifier, object_fields, timestamp


PREFIX = '/api/v1/'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def fail(status, code, detail):
    raise ApiError(status, code, detail)


def authorize(api, principal, source, permission):
    api._require(principal, {permission})
    if 'input-sources:manage' not in principal.permissions and principal.subject != source['subject']:
        fail(403, 'forbidden', 'This credential cannot access this source')


def accessible_source(api, principal, state, source_id, permission):
    if not isinstance(source_id, str):
        fail(422, 'invalid_input', 'source_id must be a string')
    source = state['sources'].get(source_id)
    if source is None:
        fail(404, 'not_found', 'Source not found')
    authorize(api, principal, source, permission)
    return source


def usable(source):
    if not source['enabled'] or source['manual_override']:
        fail(409, 'source_paused', 'The source is disabled or has manual overrides; owner confirmation is required')


def check_batch_source(source, batch):
    if source['revision'] != batch['source_revision']:
        fail(412, 'source_changed', 'Source configuration changed; preview again')


def handle(api, principal, method, path, headers, raw):
    try:
        return _handle(api, principal, method, path, headers, raw)
    except ImportValidationError as exc:
        fail(422, 'invalid_input', str(exc))


def _handle(api, principal, method, path, headers, raw):
    parts = path.removeprefix(PREFIX).split('/')
    write = method != 'GET'
    payload = None
    receipt_id = fingerprint = None
    if write:
        if headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            fail(415, 'unsupported_media_type', 'Use application/json')
        identifier(headers.get('idempotency-key'))
        payload = strict_json(raw)
        fingerprint = digest(payload)
        receipt_id = digest([principal.subject, method, path, headers['idempotency-key']])
    with api.repository.transaction() as session:
        current = api._authenticate(headers, write=write)
        if current.subject != principal.subject:
            fail(401, 'authentication_required', 'Authentication subject changed')
        principal = current
        state = session.state.setdefault('imports', {'sources': {}, 'batches': {}, 'receipts': {}, 'runs': {}})
        document = session.state['document']
        sources, batches = state['sources'], state['batches']
        source = batch = None
        if parts[0] == 'input-sources':
            if len(parts) == 3 and parts[2] in {'positions', 'batches'} and method == 'GET':
                source = accessible_source(api, principal, state, parts[1], 'imports:read')
                ids = {target['asset_id'] for target in source['targets']}
                if parts[2] == 'batches':
                    visible = [deepcopy(b) for b in batches.values() if b['source_id'] == source['id'] and
                               ('input-sources:manage' in principal.permissions or {d['asset_id'] for d in b['diff']} <= ids)]
                    return response(200, {'batches': visible})
                return response(200, {'base_revision': document['revision'], 'source_revision': source['revision'],
                    'manual_override': source['manual_override'], 'enabled': source['enabled'],
                    'items': [{'asset_id': row['asset_id'], 'quantity': row['units']} for row in document['items'] if row['asset_id'] in ids]})
            api._require(principal, {'input-sources:manage'})
            if len(parts) == 2:
                source = accessible_source(api, principal, state, parts[1], 'input-sources:manage')
        elif parts[0] == 'import-batches':
            permission = 'imports:read' if method == 'GET' else 'imports:preview' if len(parts) == 1 else 'imports:commit'
            api._require(principal, {permission})
            if len(parts) >= 2:
                batch = batches.get(parts[1])
                if batch is None:
                    fail(404, 'not_found', 'Batch not found')
                source = accessible_source(api, principal, state, batch['source_id'], permission)
                if method != 'GET':
                    check_batch_source(source, batch)
                elif 'input-sources:manage' not in principal.permissions and not {d['asset_id'] for d in batch['diff']} <= {t['asset_id'] for t in source['targets']}:
                    fail(403, 'forbidden', 'Historical batch is outside current scope')
            else:
                if not isinstance(payload, dict):
                    fail(422, 'invalid_input', 'Expected an object')
                source = accessible_source(api, principal, state, payload.get('source_id'), permission)
        else:
            fail(404, 'not_found', 'Unknown import operation')
        if write and receipt_id in state['receipts']:
            receipt = state['receipts'][receipt_id]
            if receipt['fingerprint'] != fingerprint:
                fail(409, 'idempotency_key_reused', 'Key already used for a different request')
            if api.clock() - receipt['created_at'] >= RECEIPT_SECONDS:
                fail(409, 'idempotency_result_expired', 'Read the batch history to reconcile the result')
            return response(receipt['status'], deepcopy(receipt['body']), {'Idempotency-Replayed': 'true'})
        if write and len(state['receipts']) >= 10000:
            fail(503, 'import_capacity_reached', 'Import receipt capacity reached; contact the owner')
        status, write_csv = 200, False
        if parts[0] == 'input-sources':
            if method == 'GET' and len(parts) in (1, 2):
                return response(200, deepcopy(source) if source else {'sources': deepcopy(list(sources.values()))})
            if (method, len(parts)) not in {('POST', 1), ('PUT', 2)}:
                fail(405, 'method_not_allowed', 'Unsupported source operation')
            if method == 'POST':
                if len(sources) >= 100:
                    fail(503, 'import_capacity_reached', 'Source capacity reached')
                config = source_config(payload, document['items'])
                source_id = str(uuid4())
            else:
                object_fields(payload, ['base_source_revision', 'config', 'resume_ids'])
                if payload['base_source_revision'] != source['revision']:
                    fail(412, 'source_changed', 'Read current source configuration first')
                if not isinstance(payload['resume_ids'], list) or any(i not in source['manual_override'] for i in payload['resume_ids']):
                    fail(422, 'invalid_input', 'Unknown manual override')
                config = source_config(payload['config'], document['items'])
                source_id = source['id']
            ids = {t['asset_id'] for t in config['targets']}
            if any(ids & {t['asset_id'] for t in other['targets']} for sid, other in sources.items() if sid != source_id):
                fail(409, 'source_overlap', 'Each target can belong to only one source')
            result = {**deepcopy(config), 'id': source_id, 'revision': str(uuid4()),
                      'manual_override': [] if source is None else [i for i in source['manual_override'] if i in ids and i not in payload['resume_ids']],
                      'last_sequence': 0 if source is None else source['last_sequence'],
                      'last_as_of': None if source is None else source['last_as_of']}
            sources[source_id] = result
            status = 201 if method == 'POST' else 200
        elif method == 'GET' and len(parts) == 2:
            return response(200, deepcopy(batch))
        elif method == 'POST' and len(parts) == 1:
            usable(source)
            run_id = digest([source['id'], payload.get('source_run_id')])
            previous = state['runs'].get(run_id)
            if previous:
                if previous['fingerprint'] != fingerprint:
                    fail(409, 'source_run_reused', 'Run ID already used with different input')
                result = deepcopy(batches[previous['batch_id']])
                check_batch_source(source, result)
            else:
                if len(batches) >= 10000:
                    fail(503, 'import_capacity_reached', 'Batch capacity reached')
                diff = batch_payload(payload, source, document['items'], api.clock())
                check_order(source, payload)
                if payload['base_revision'] != document['revision']:
                    fail(412, 'revision_mismatch', 'Read source positions again')
                batch_id = str(uuid4())
                result = {'id': batch_id, 'source_id': source['id'], 'source_revision': source['revision'],
                          'status': 'preview', 'request': deepcopy(payload), 'diff': diff, 'diff_hash': digest(diff),
                          'base_revision': document['revision'], 'result_revision': None, 'committed_at': None,
                          'change_id': None, 'changed': None}
                batches[batch_id] = deepcopy(result)
                state['runs'][run_id] = {'fingerprint': fingerprint, 'batch_id': batch_id}
            status = 201
        elif method == 'POST' and len(parts) == 3 and parts[2] in {'commit', 'cancel'}:
            object_fields(payload, ['diff_hash'])
            if payload['diff_hash'] != batch['diff_hash']:
                fail(412, 'diff_mismatch', 'Commit/cancel must reference the previewed diff')
            if parts[2] == 'cancel':
                if batch['status'] == 'committed':
                    fail(409, 'batch_committed', 'Committed history cannot be cancelled')
                batch['status'] = 'cancelled'
            elif batch['status'] == 'cancelled':
                fail(409, 'batch_cancelled', 'Preview a new batch')
            elif batch['status'] != 'committed':
                usable(source)
                batch_payload(batch['request'], source, document['items'], api.clock())
                check_order(source, batch['request'])
                if document['revision'] != batch['base_revision']:
                    fail(412, 'revision_mismatch', 'Input changed since preview; preview a new run')
                old = deepcopy(document)
                values = {d['asset_id']: d['after'] for d in batch['diff'] if d['changed']}
                for row in document['items']:
                    if row['asset_id'] in values:
                        row['units'] = values[row['asset_id']]
                write_csv = bool(values)
                now = datetime.fromtimestamp(api.clock(), timezone.utc).isoformat()
                change_id = str(uuid4()) if write_csv else None
                if write_csv:
                    document.update(revision=str(uuid4()), updated_at=now)
                    session.state['changes'].append({'change_id': change_id, 'subject': principal.subject,
                        'source_id': source['id'], 'batch_id': batch['id'], 'before': old, 'after': deepcopy(document)})
                source['last_sequence'] = batch['request']['sequence']
                if batch['request']['as_of'] is not None:
                    source['last_as_of'] = batch['request']['as_of']
                batch.update(status='committed', result_revision=document['revision'], committed_at=now,
                             change_id=change_id, changed=write_csv)
            result = deepcopy(batch)
        else:
            fail(405, 'method_not_allowed', 'Unsupported import operation')
        state['receipts'][receipt_id] = {'fingerprint': fingerprint, 'created_at': api.clock(), 'status': status, 'body': deepcopy(result)}
        session.commit(write_csv=write_csv)
        return response(status, result, {'Idempotency-Replayed': 'false'})


def check_order(source, payload):
    if payload['sequence'] <= source['last_sequence']:
        fail(409, 'stale_import', 'Sequence must increase monotonically for this source')
    if payload['as_of'] is not None and source['last_as_of'] is not None and timestamp(payload['as_of']) <= timestamp(source['last_as_of']):
        fail(409, 'stale_import', 'Same or older as_of requires owner reconciliation')
