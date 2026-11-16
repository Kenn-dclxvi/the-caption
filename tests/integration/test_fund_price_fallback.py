"""Fictional NAV + frozen daily calculation through the public price API."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from src.app.fund_price_fallback import FundPriceFallback
from src.app.input_api import InputApi
from src.domain.fund_price_fallback import FundPriceError, digest
from src.domain.input_api_auth import OWNER_PERMISSIONS, token_digest
from src.domain.universal_ingester import UniversalIngester
from src.infra.canonical_ledger_input_repository import CanonicalLedgerInputRepository
from src.infra.frozen_ledger_inputs import FrozenLedgerInputs, FrozenTimeline, RecordedMarketClose
from src.infra.fund_price_repository import FundPriceRepository
from src.infra.input_api_credentials import CredentialFile
from src.infra.ledger_repository import LedgerRepository
from src.infra.market_units_input_repository import MarketUnitsInputRepository
from src.infra.market_units_snapshot_repository import ensure_units_snapshot

TOKEN = 'fictional_price_token_0123456789'
ASSET_A = '00000000-0000-4000-8000-000000000001'
ASSET_B = '00000000-0000-4000-8000-000000000002'


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    import src.infra.ledger_repository as module
    current = tmp_path / 'current'
    current.mkdir()
    monkeypatch.setattr(module, 'DIR_CURRENT', str(current))
    csv = tmp_path / 'market_units.csv'
    csv.write_text('name,asset_class,currency,units,source_symbol,audit_match_key,csv_url\n'
                   'FundA,MUTUAL_FUNDS,JPY,10000,A,,\nFundB,MUTUAL_FUNDS,JPY,20000,B,,\n')
    external = tmp_path / 'external.json'
    external.write_text(json.dumps({'default': {'items': [{'name': 'Cash', 'category': 'CASH', 'amount': 300}]}}))
    basis = tmp_path / 'basis.json'
    basis.write_text(json.dumps({'default': {'total_acquisition_cost_jpy': 25000}}))
    history = tmp_path / 'history'
    history.mkdir()
    for name in ('FundA', 'FundB'):
        (history / (name + '.csv')).write_text('基準日,基準価額\n2026-11-12,10000\n')
    ensure_units_snapshot('2026-11-13', str(csv), str(current))
    inputs = FrozenLedgerInputs(CanonicalLedgerInputRepository())
    closed = RecordedMarketClose(lambda *_: True)
    kwargs = {'funds_csv_path': str(csv), 'external_assets_path': str(external),
              'portfolio_basis_path': str(basis), 'history_dir': str(history), 'units_snapshot_dir': str(current)}
    ingester = UniversalIngester(**kwargs, timeline=FrozenTimeline('2026-11-13', '2026-11-13'),
                                input_store=inputs, is_closed_fn=closed)
    ledger = ingester.run('2026-11-13', units_mode='strict', previous_records={})
    now = datetime(2026, 11, 14, 0, 31, tzinfo=timezone.utc)
    service = FundPriceFallback(FundPriceRepository(tmp_path / 'price-state'), LedgerRepository(), lambda: now)
    context = {'calls': inputs.calls, 'closed': closed.values, 'ingester': kwargs, 'previous_records': {},
               'us_date': '2026-11-13'}
    assert service.capture(ledger, context, {ASSET_A: 'FundA', ASSET_B: 'FundB'})
    requests = service.list_requests()['requests']
    credentials = tmp_path / 'credentials.json'
    credentials.write_text(json.dumps({'tokens': [{'id': 'fictional', 'subject': 'fictional',
        'sha256': token_digest(TOKEN), 'permissions': sorted(OWNER_PERMISSIONS),
        'expires_at': '2027-01-01T00:00:00+00:00', 'revoked': False}]}))
    credentials.chmod(0o600)
    api = InputApi(MarketUnitsInputRepository(csv), CredentialFile(str(credentials)),
                   fund_price_fallback=service, clock=lambda: now.timestamp())
    return service, requests, api, tmp_path, kwargs, ledger, context


def candidate(request, price='12345'):
    return {k: request[k] for k in ('request_id', 'asset_id', 'target_price_date', 'request_revision',
                                    'currency', 'price_quote_units')} | {
        'source': 'monex_fund_detail', 'retrieved_at': '2026-11-14T09:05:00+09:00',
        'source_price': price, 'source_quote_units': 10000, 'price': price}


def call(api, request=None, action=None, body=None, key=None, token=TOKEN):
    path = '/api/v1/fund-price-requests'
    if request:
        path += '/' + request['request_id']
    if action:
        path += '/' + action
    return api.handle({'method': 'POST' if action else 'GET', 'path': path,
        'headers': {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                    'Idempotency-Key': key or str(uuid4())}, 'body': json.dumps(body) if body is not None else ''})


def validate(name, value):
    contract = json.loads((Path(__file__).resolve().parents[2] / 'docs/reference/openapi-fund-prices-v1.json').read_text())
    Draft202012Validator({'$ref': '#/components/schemas/' + name, **contract},
                         format_checker=FormatChecker()).validate(value)


def test_api_frozen_inputs_and_completion(prepared):
    service, requests, api, root, kwargs, _, _ = prepared
    validate('FundPriceRequests', call(api)['body'])
    # Change all next-day inputs; they must never be used in the pending calculation.
    Path(kwargs['funds_csv_path']).write_text('corrupt next-day config')
    Path(kwargs['external_assets_path']).write_text('corrupt next-day amounts')
    Path(kwargs['portfolio_basis_path']).write_text('corrupt next-day basis')
    for path in Path(kwargs['history_dir']).iterdir():
        path.unlink()
    for request in requests:
        body = candidate(request)
        validate('FundPriceCandidate', body)
        key = str(uuid4())
        result = call(api, request, 'candidate', body, key)
        assert result['status'] == 200, result
        validate('FundPriceRequest', result['body'])
        assert result['body']['receipt'] == {'idempotency_key': key, 'candidate_digest': digest(body)}
        assert call(api, request, 'candidate', body, key)['status'] == 200
    result = call(api, requests[0], 'complete', {})
    assert result['status'] == 200 and result['body']['calculation_status'] == 'completed', result
    validate('FundPriceRequest', result['body'])
    saved = service.ledger_repository.load('2026-11-13')
    funds = [a for a in saved['assets'] if a['source'] == 'MARKET_UNITS']
    assert sorted(a['units'] for a in funds) == [10000, 20000]
    assert sorted(a['value_jpy'] for a in funds) == [12345, 24690]
    assert saved['summary']['total_assets_jpy'] == 37335
    assert saved['meta']['integrity_status'] == 'VERIFIED'
    assert call(api, requests[0], 'complete', {})['body'] == result['body']


def test_partial_adoption_does_not_complete(prepared):
    service, requests, api, *_ = prepared
    assert call(api, requests[0], 'candidate', candidate(requests[0]))['status'] == 200
    assert call(api, requests[0], 'complete', {})['body']['calculation_status'] == 'waiting_for_price'
    assert service.ledger_repository.load('2026-11-13') is None


@pytest.mark.parametrize('field,value', [('target_price_date', '2026-11-12'), ('price', '1'),
                                        ('source_quote_units', 0), ('source_price', 'NaN'),
                                        ('request_revision', 'other'), ('retrieved_at', '2027-01-01T00:00:00Z')])
def test_invalid_candidates_are_rejected(prepared, field, value):
    _, requests, api, *_ = prepared
    body = candidate(requests[0])
    body[field] = value
    assert call(api, requests[0], 'candidate', body)['status'] in (409, 422)


def test_conflicting_candidate_and_primary_recovery(prepared):
    service, requests, api, _, kwargs, *_ = prepared
    first, second = requests
    key = str(uuid4())
    assert call(api, first, 'candidate', candidate(first), key)['status'] == 200
    assert call(api, first, 'candidate', candidate(first, '12346'), key)['status'] == 409
    Path(kwargs['history_dir'], 'FundB.csv').write_text('基準日,基準価額\n2026-11-13,14000\n')
    result = call(api, second, 'candidate', candidate(second))
    assert result['status'] == 200 and result['body']['status'] == 'primary'
    assert result['body']['receipt'] is None
    assert call(api, first, 'complete', {})['body']['calculation_status'] == 'completed'


def test_confirmed_ledger_is_never_replaced(prepared):
    service, requests, api, *_ = prepared
    for request in requests:
        call(api, request, 'candidate', candidate(request))
    # An independently confirmed result appeared after the pending capture.
    other = {'meta': {'target_date': '2026-11-13', 'integrity_status': 'VERIFIED'}}
    service.ledger_repository = type('IndependentLedger', (), {'load_for_price_fallback': lambda self, day: deepcopy(other),
        'save_for_price_fallback': lambda *args: pytest.fail('confirmed ledger overwritten')})()
    assert call(api, requests[0], 'complete', {})['body']['calculation_status'] == 'correction_required'


def test_response_loss_after_canonical_publication_is_reconciled(prepared, monkeypatch):
    service, requests, api, *_ = prepared
    for request in requests:
        call(api, request, 'candidate', candidate(request))
    save = service.ledger_repository.save_document
    def lost(document, day):
        save(document, day)
        raise OSError('fictional lost response')
    monkeypatch.setattr(service.ledger_repository, 'save_document', lost)
    assert call(api, requests[0], 'complete', {})['status'] == 503
    monkeypatch.setattr(service.ledger_repository, 'save_document', save)
    assert call(api, requests[0], 'complete', {})['body']['calculation_status'] == 'completed'


def test_frozen_context_tampering_does_not_publish(prepared):
    service, requests, api, *_ = prepared
    for request in requests:
        call(api, request, 'candidate', candidate(request))
    with service.repository.transaction() as state:
        state['calculations']['2026-11-13']['context']['previous_records'] = {'tampered': True}
    assert call(api, requests[0], 'complete', {})['body']['calculation_status'] == 'calculation_failed'
    assert service.ledger_repository.load('2026-11-13') is None


def test_auth_and_disabled_service(prepared):
    _, requests, api, *_ = prepared
    assert call(api, token='bad')['status'] == 401
    api.fund_price_fallback = None
    assert call(api)['body']['code'] == 'fund_price_fallback_disabled'


def test_concurrent_same_candidate_is_idempotent(prepared):
    _, requests, api, *_ = prepared
    request = requests[0]
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: call(api, request, 'candidate', candidate(request), key), range(4)))
    assert all(r['status'] == 200 for r in results)
    assert len({digest(r['body']['receipt']) for r in results}) == 1


def test_successful_primary_prices_need_no_fallback(prepared, tmp_path):
    _, _, _, _, _, ledger, context = prepared
    service = FundPriceFallback(FundPriceRepository(tmp_path / 'no-wait'), LedgerRepository())
    ledger = ledger.model_copy(update={'assets': [a.model_copy(update={'pricing_status': 'PRICED'})
                                                 for a in ledger.assets]})
    assert service.capture(ledger, context, {ASSET_A: 'FundA', ASSET_B: 'FundB'}) is False
    assert service.list_requests() == {'requests': []}


def test_completed_receipt_rechecks_actual_canonical_file(prepared):
    _, requests, api, root, *_ = prepared
    for request in requests:
        assert call(api, request, 'candidate', candidate(request))['status'] == 200
    assert call(api, requests[0], 'complete', {})['body']['calculation_status'] == 'completed'
    (root / 'current/ledger_20261113.json').unlink()
    assert call(api, requests[0])['body']['code'] == 'ledger_readback_mismatch'
