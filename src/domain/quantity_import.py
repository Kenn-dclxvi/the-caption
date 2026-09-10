"""Pure validation for source-scoped absolute quantity imports."""
from datetime import datetime
from decimal import Decimal
import re
from uuid import UUID, uuid4


class ImportValidationError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ImportValidationError(message)


def object_fields(value, fields):
    require(isinstance(value, dict) and set(value) == set(fields), 'Unexpected or missing fields')


def text(value, maximum=256):
    require(isinstance(value, str) and 0 < len(value) <= maximum and
            not re.search(r'[\x00-\x1f\x7f-\x9f]', value), 'Invalid text')
    return value


def identifier(value):
    try:
        require(str(UUID(value)) == value, 'Use a canonical UUID')
    except (ValueError, TypeError, AttributeError) as exc:
        raise ImportValidationError('Use a canonical UUID') from exc
    return value


def quantity(value):
    require(isinstance(value, str) and re.fullmatch(r'(0|[1-9][0-9]{0,17})(\.[0-9]{1,12})?', value),
            'Quantity must be an exact nonnegative decimal string')
    return value.rstrip('0').rstrip('.') if '.' in value else value


def timestamp(value):
    try:
        result = datetime.fromisoformat(value)
        require(result.tzinfo is not None, 'Timestamp needs a timezone')
        return result.timestamp()
    except (ValueError, TypeError, OverflowError) as exc:
        raise ImportValidationError('Invalid timestamp') from exc


def source_config(payload, items):
    object_fields(payload, ['name', 'subject', 'enabled', 'max_age_seconds', 'allow_unknown_as_of', 'targets'])
    text(payload['name']); text(payload['subject'])
    require(type(payload['enabled']) is bool and type(payload['allow_unknown_as_of']) is bool, 'Invalid flags')
    age = payload['max_age_seconds']
    require(type(age) is int and 1 <= age <= 30 * 86400, 'Invalid freshness limit')
    targets = payload['targets']
    require(isinstance(targets, list) and 1 <= len(targets) <= 5000, 'Invalid target count')
    allowed_ids = {row['asset_id'] for row in items if row['asset_class'] != 'FX'}
    ids, records = set(), set()
    for target in targets:
        object_fields(target, ['asset_id', 'quantity_unit', 'external_record_ids'])
        asset_id = identifier(target['asset_id'])
        require(asset_id in allowed_ids and asset_id not in ids, 'Unknown, duplicate or FX target')
        ids.add(asset_id); text(target['quantity_unit'], 64)
        external = target['external_record_ids']
        require(isinstance(external, list) and 1 <= len(external) <= 100, 'Invalid external record set')
        for record in external:
            text(record)
            require(record not in records, 'Duplicate external record')
            records.add(record)
    return payload


def batch_payload(payload, source, items, now):
    object_fields(payload, ['source_id', 'source_run_id', 'base_revision', 'mapping_version', 'sequence',
                            'collected_at', 'as_of', 'enumeration_complete', 'items'])
    text(payload['source_run_id']); text(payload['mapping_version']); text(payload['base_revision'])
    require(type(payload['sequence']) is int and 1 <= payload['sequence'] <= 9007199254740991, 'Invalid sequence')
    require(payload['enumeration_complete'] is True, 'Incomplete enumeration')
    collected = timestamp(payload['collected_at'])
    require(now - source['max_age_seconds'] <= collected <= now, 'Collection is stale or in the future')
    as_of = payload['as_of']
    require(as_of is not None or source['allow_unknown_as_of'], 'Unknown as_of is not allowed')
    if as_of is not None:
        require(now - source['max_age_seconds'] <= timestamp(as_of) <= collected, 'as_of is stale or in the future')
    incoming = payload['items']
    require(isinstance(incoming, list) and 1 <= len(incoming) <= 5000, 'Invalid item count')
    targets = {t['asset_id']: t for t in source['targets']}
    current = {row['asset_id']: row for row in items}
    values = {}
    for row in incoming:
        object_fields(row, ['asset_id', 'quantity', 'quantity_unit', 'external_record_ids'])
        asset_id = identifier(row['asset_id'])
        require(asset_id in targets and asset_id in current and current[asset_id]['asset_class'] != 'FX' and asset_id not in values, 'Unknown or duplicate target')
        target = targets[asset_id]
        require(row['quantity_unit'] == target['quantity_unit'], 'Quantity unit mismatch')
        records = row['external_record_ids']
        require(isinstance(records, list) and all(isinstance(v, str) for v in records) and
                len(records) == len(set(records)) and set(records) == set(target['external_record_ids']),
                'Incomplete external record set')
        values[asset_id] = quantity(row['quantity'])
    require(set(values) == set(targets), 'missing_position: include every configured target explicitly')
    return [{'asset_id': asset_id, 'before': current[asset_id]['units'], 'after': value,
             'changed': Decimal(current[asset_id]['units']) != Decimal(value)} for asset_id, value in values.items()]


def pause_manual_changes(state, before, after):
    """Owner edits pause quantity automation; unchanged saves do not."""
    old = {row['asset_id']: row for row in before['items']}
    new = {row['asset_id']: row for row in after['items']}
    for source in state.get('imports', {}).get('sources', {}).values():
        for target in source['targets']:
            asset_id = target['asset_id']
            if asset_id in old and (asset_id not in new or new[asset_id]['asset_class'] == 'FX' or Decimal(old[asset_id]['units']) != Decimal(new[asset_id]['units'])):
                source['revision'] = str(uuid4())
                if asset_id not in source['manual_override']:
                    source['manual_override'].append(asset_id)
