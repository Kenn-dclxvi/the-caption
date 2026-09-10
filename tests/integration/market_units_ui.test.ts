import assert from 'node:assert/strict';
import test from 'node:test';

import { MarketUnitsStore } from '../../src/web/market_units_editor/src/marketUnitsClient.ts';

type Call = { url: string; method: string; headers: Headers; body: string | undefined };
type Reply = Response | Error | ((call: Call) => Response | Promise<Response>);

const ID_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const ID_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const CSRF = 'session-csrf-token';
const ETAG = '"revision-one"';

test('default browser transport preserves the fetch receiver during session checks and login', async () => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = async function (this: unknown, input, init) {
    assert.equal(this, globalThis, 'native browser fetch requires its global receiver');
    calls.push(`${init?.method ?? 'GET'} ${input}`);
    if (calls.length === 1) return json({ code: 'authentication_required' }, 401);
    if (String(input) === '/api/session') return session();
    return json(resource(), 200, { ETag: ETAG });
  };
  try {
    const store = new MarketUnitsStore();
    await store.initialize();
    await store.login('test-browser-token');
    assert.ok(store.getSnapshot().session);
    assert.equal(store.getSnapshot().etag, ETAG);
    assert.deepEqual(calls, ['GET /api/session', 'POST /api/session', 'GET /api/v1/market-units']);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

function session() {
  return json({
    authenticated: true,
    csrf_token: CSRF,
    permissions: ['market-units:read', 'market-units:replace', 'market-units:clear'],
  });
}

function script(...replies: Reply[]) {
  const calls: Call[] = [];
  const queue = [...replies];
  const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const call: Call = {
      url: String(input),
      method: init?.method ?? 'GET',
      headers: new Headers(init?.headers),
      body: init?.body == null ? undefined : String(init.body),
    };
    calls.push(call);
    const reply = queue.shift();
    assert.ok(reply, `unexpected request: ${call.method} ${call.url}`);
    if (reply instanceof Error) throw reply;
    return typeof reply === 'function' ? reply(call) : reply;
  }) as typeof fetch;
  return { calls, fetcher, remaining: () => queue.length };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function makeStore(fetcher: typeof fetch) {
  let sequence = 0;
  return new MarketUnitsStore(fetcher, () => `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}`);
}

function resource(items: unknown[] = [], revision = 'rev_1') {
  return { revision, storage_state: 'ready', updated_at: '2026-09-08T00:00:00Z', items };
}

function fields(patch: Record<string, string> = {}) {
  return {
    name: 'Example Fund',
    asset_class: 'MUTUAL_FUNDS',
    currency: 'JPY',
    units: '1.000000000001',
    source_symbol: 'Example Fund',
    audit_match_key: '',
    csv_url: '',
    ...patch,
  };
}

function wireRow(asset_id = ID_A, patch: Record<string, string> = {}) {
  const item = fields(patch);
  return { asset_id, ...item, asset_key: `${item.asset_class}:${item.currency}:${item.name}` };
}

function succeeded(saved: ReturnType<typeof resource>, changed = true) {
  // A successful replacement intentionally has no ETag; only the following GET supplies it.
  return json({ changed, change_id: changed ? 'change-2' : null, resource: saved });
}

async function initialized(...replies: Reply[]) {
  const initial = resource([wireRow()]);
  const transport = script(session(), json(initial, 200, { ETag: ETAG }), ...replies);
  const store = makeStore(transport.fetcher);
  await store.initialize();
  return { store, transport, initial };
}

function applyEdit(store: MarketUnitsStore, patch: Record<string, string>, id = ID_A) {
  store.openForm(id);
  store.updateForm(patch);
  store.applyForm();
}

test('initialization checks the session before reading the versioned document and ETag', async () => {
  const initial = resource();
  const transport = script(session(), json(initial, 200, { ETag: ETAG }));
  const store = makeStore(transport.fetcher);
  await store.initialize();

  assert.deepEqual(transport.calls.map(({ method, url }) => [method, url]), [
    ['GET', '/api/session'],
    ['GET', '/api/v1/market-units'],
  ]);
  assert.deepEqual(store.getSnapshot().document, initial);
  assert.equal(store.getSnapshot().etag, ETAG);
  assert.equal(store.getSnapshot().sessionChecked, true);
  assert.equal(store.getSnapshot().dirty, false);
  assert.equal(transport.remaining(), 0);
});

test('an absent session does not read protected data; login exchanges the bearer token for a session', async () => {
  const transport = script(json({ detail: 'unauthorized' }, 401), session(), json(resource(), 200, { ETag: ETAG }));
  const store = makeStore(transport.fetcher);
  await store.initialize();

  assert.equal(transport.calls.length, 1);
  assert.equal(store.getSnapshot().sessionChecked, true);
  assert.ok(!store.getSnapshot().session);

  await store.login('private-operator-token');
  assert.deepEqual(transport.calls.map(({ method, url }) => [method, url]), [
    ['GET', '/api/session'],
    ['POST', '/api/session'],
    ['GET', '/api/v1/market-units'],
  ]);
  assert.equal(transport.calls[1].headers.get('Authorization'), 'Bearer private-operator-token');
  assert.equal(transport.calls[1].body, '{}');
  assert.equal(transport.calls[2].headers.get('Authorization'), null);
  assert.ok(!JSON.stringify(store.getSnapshot()).includes('private-operator-token'));
  assert.equal(transport.remaining(), 0);
});

test('form edits remain separate from the draft, cancellation preserves applied edits, and IDs select duplicate names', async () => {
  const transport = script(session(), json(resource([
    wireRow(ID_A, { name: 'Same Name' }),
    wireRow(ID_B, { name: 'Same Name', currency: 'USD' }),
  ]), 200, { ETag: ETAG }));
  const store = makeStore(transport.fetcher);
  await store.initialize();

  store.openForm(ID_A);
  store.updateForm({ name: 'Unapplied Name', units: '123456789012345678.123456789012' });
  assert.equal(store.getSnapshot().items[0].name, 'Same Name');
  assert.equal(store.getSnapshot().dirty, false);
  store.cancelForm();
  assert.equal(store.getSnapshot().form, null);
  assert.equal(store.getSnapshot().items[0].name, 'Same Name');

  applyEdit(store, { name: 'Applied Name' }, ID_B);
  assert.deepEqual(store.getSnapshot().items.map(({ asset_id, draft_id, name }) => ({ asset_id, draft_id, name })), [
    { asset_id: ID_A, draft_id: ID_A, name: 'Same Name' },
    { asset_id: ID_B, draft_id: ID_B, name: 'Applied Name' },
  ]);
  store.openForm(ID_A);
  store.updateForm({ name: 'Another Unapplied Name' });
  store.cancelForm();
  assert.equal(store.getSnapshot().items[1].name, 'Applied Name');
  assert.equal(store.getSnapshot().dirty, true);
  store.deleteItem(ID_A);
  assert.deepEqual(store.getSnapshot().items.map(({ asset_id }) => asset_id), [ID_B]);
  assert.equal(transport.calls.length, 2);
});

test('save sends exactly seven string fields and identity, excludes UI/server fields, and acquires a fresh ETag by GET', async () => {
  const precision = '123456789012345678.123456789012';
  const saved = resource([wireRow(ID_A, { units: precision }), wireRow(ID_B, { name: 'New Fund', units: '0.000000000001' })], 'rev_2');
  const { store, transport } = await initialized(succeeded(saved), json(saved, 200, { ETag: '"revision-two"' }));

  applyEdit(store, { units: precision });
  store.openForm();
  store.updateForm(fields({ name: 'New Fund', units: '0.000000000001' }));
  assert.equal(store.getSnapshot().form?.item.asset_id, null);
  assert.ok(store.getSnapshot().form?.item.draft_id);
  store.applyForm();
  await store.save();

  const put = transport.calls[2];
  assert.equal(put.method, 'PUT');
  assert.equal(put.url, '/api/v1/market-units');
  assert.deepEqual(JSON.parse(put.body!), {
    items: [
      { asset_id: ID_A, ...fields({ units: precision }) },
      { asset_id: null, ...fields({ name: 'New Fund', units: '0.000000000001' }) },
    ],
    clear_all: false,
  });
  assert.equal(put.headers.get('If-Match'), ETAG);
  assert.match(put.headers.get('Idempotency-Key')!, /^[0-9a-f-]{36}$/);
  assert.equal(put.headers.get('X-CSRF-Token'), CSRF);
  assert.equal(put.headers.get('Content-Type'), 'application/json');
  assert.equal(put.headers.get('Authorization'), null);
  assert.deepEqual(transport.calls.slice(2).map(({ method, url }) => [method, url]), [
    ['PUT', '/api/v1/market-units'], ['GET', '/api/v1/market-units'],
  ]);
  assert.equal(store.getSnapshot().etag, '"revision-two"');
  assert.equal(store.getSnapshot().items[1].asset_id, ID_B);
  assert.equal(store.getSnapshot().items[1].draft_id, ID_B);
  assert.equal(store.getSnapshot().items[0].units, precision);
  assert.equal(store.getSnapshot().dirty, false);
  assert.equal(store.getSnapshot().pending, null);
  assert.equal(store.getSnapshot().needsRefresh, false);
  assert.equal(transport.remaining(), 0);
});

test('refresh preserves an open form but refuses to apply it to the new epoch', async () => {
  const latest = resource([wireRow(ID_A, { name: 'Other Client' })], 'rev_2');
  const { store, transport } = await initialized(json(latest, 200, { ETag: '"revision-two"' }));
  applyEdit(store, { units: '2' });
  store.openForm(ID_A);
  store.updateForm({ name: 'Unapplied Form' });
  const form = structuredClone(store.getSnapshot().form);
  await store.refresh();

  assert.deepEqual(store.getSnapshot().form, form);
  assert.notEqual(store.getSnapshot().epoch, form!.epoch);
  assert.equal(store.getSnapshot().items[0].name, 'Other Client');
  assert.equal(store.getSnapshot().dirty, false);
  store.applyForm();
  assert.equal(store.getSnapshot().items[0].name, 'Other Client');
  assert.deepEqual(store.getSnapshot().form, form);
  assert.equal(store.getSnapshot().notice?.tone, 'error');
  assert.equal(transport.calls.length, 3);
});

test('save preserves an unapplied form and prevents its stale contents from replacing the saved draft', async () => {
  const saved = resource([wireRow(ID_A, { units: '2' })], 'rev_2');
  const { store, transport } = await initialized(succeeded(saved), json(saved, 200, { ETag: '"revision-two"' }));
  applyEdit(store, { units: '2' });
  store.openForm(ID_A);
  store.updateForm({ name: 'Unapplied Form' });
  const form = structuredClone(store.getSnapshot().form);
  await store.save();

  assert.equal(JSON.parse(transport.calls[2].body!).items[0].name, 'Example Fund');
  assert.deepEqual(store.getSnapshot().form, form);
  store.applyForm();
  assert.equal(store.getSnapshot().items[0].name, 'Example Fund');
  assert.equal(store.getSnapshot().items[0].units, '2');
  assert.equal(store.getSnapshot().dirty, false);
  assert.equal(store.getSnapshot().notice?.tone, 'error');
});

test('a write in flight freezes form and draft mutation, refresh, and duplicate saves', async () => {
  const delayed = deferred<Response>();
  const saved = resource([wireRow(ID_A, { units: '2' })], 'rev_2');
  const { store, transport } = await initialized(() => delayed.promise, json(saved, 200, { ETag: '"revision-two"' }));
  applyEdit(store, { units: '2' });
  store.openForm(ID_A);
  store.updateForm({ name: 'Open Form' });
  const before = structuredClone({ items: store.getSnapshot().items, form: store.getSnapshot().form });
  const write = store.save();
  assert.equal(store.getSnapshot().saving, true);

  store.updateForm({ units: '999' });
  store.applyForm();
  store.cancelForm();
  store.openForm();
  store.deleteItem(ID_A);
  await store.refresh();
  await store.save();
  await store.retry();
  assert.deepEqual({ items: store.getSnapshot().items, form: store.getSnapshot().form }, before);
  assert.equal(transport.calls.length, 3);

  delayed.resolve(succeeded(saved));
  await write;
  assert.equal(store.getSnapshot().saving, false);
  assert.equal(transport.calls.length, 4);
  assert.equal(transport.remaining(), 0);
});

test('412 preserves the draft, exposes a conflict, and never retries the rejected PUT', async () => {
  const { store, transport } = await initialized(json({ code: 'revision_mismatch', detail: 'Document changed' }, 412));
  applyEdit(store, { name: 'My Draft', units: '2.000000000001' });
  const draft = structuredClone(store.getSnapshot().items);
  await store.save();

  assert.deepEqual(store.getSnapshot().items, draft);
  assert.equal(store.getSnapshot().dirty, true);
  assert.equal(store.getSnapshot().conflict, true);
  assert.equal(store.getSnapshot().pending, null);
  await store.retry();
  await store.save();
  assert.equal(transport.calls.length, 3);
});

for (const failure of ['timeout', '500', '503'] as const) {
  test(`${failure} preserves the exact pending body, idempotency key and ETag for retry`, async () => {
    const failed = failure === 'timeout'
      ? new DOMException('The operation timed out', 'AbortError')
      : json({ code: 'temporarily_unavailable', detail: 'Try again' }, Number(failure));
    const saved = resource([wireRow(ID_A, { units: '123456789012345678.123456789012' })], 'rev_2');
    const { store, transport } = await initialized(failed, succeeded(saved), json(saved, 200, { ETag: '"revision-two"' }));
    applyEdit(store, { units: '123456789012345678.123456789012' });
    const draft = structuredClone(store.getSnapshot().items);
    await store.save();

    assert.deepEqual(store.getSnapshot().items, draft);
    assert.equal(store.getSnapshot().dirty, true);
    assert.ok(store.getSnapshot().pending);
    const pending = structuredClone(store.getSnapshot().pending!);
    const firstPut = transport.calls[2];
    assert.equal(pending.body, firstPut.body);
    assert.equal(pending.etag, firstPut.headers.get('If-Match'));
    assert.equal(pending.key, firstPut.headers.get('Idempotency-Key'));
    store.openForm(ID_A);
    store.updateForm({ units: '999' });
    store.applyForm();
    store.deleteItem(ID_A);
    await store.refresh();
    await store.save();
    assert.deepEqual(store.getSnapshot().items, draft);
    assert.deepEqual(store.getSnapshot().pending, pending);
    assert.equal(transport.calls.length, 3);

    await store.retry();
    const retryPut = transport.calls[3];
    assert.equal(retryPut.method, 'PUT');
    assert.equal(retryPut.body, firstPut.body);
    assert.equal(retryPut.headers.get('If-Match'), firstPut.headers.get('If-Match'));
    assert.equal(retryPut.headers.get('Idempotency-Key'), firstPut.headers.get('Idempotency-Key'));
    assert.equal(retryPut.headers.get('X-CSRF-Token'), CSRF);
    assert.equal(transport.calls[4].method, 'GET');
    assert.equal(store.getSnapshot().pending, null);
    assert.equal(store.getSnapshot().etag, '"revision-two"');
    assert.equal(transport.remaining(), 0);
  });
}

test('PUT success followed by failed GET keeps the committed resource and blocks another PUT until refresh succeeds', async () => {
  const saved = resource([wireRow(ID_A, { units: '2' })], 'rev_2');
  const latest = resource([wireRow(ID_A, { units: '3' })], 'rev_3');
  const { store, transport } = await initialized(
    succeeded(saved), new Error('read failed'), json(latest, 200, { ETag: '"revision-three"' }),
  );
  applyEdit(store, { units: '2' });
  await store.save();

  assert.deepEqual(store.getSnapshot().document, saved);
  assert.equal(store.getSnapshot().items[0].units, '2');
  assert.equal(store.getSnapshot().savedRevision, 'rev_2');
  assert.equal(store.getSnapshot().etag, null);
  assert.equal(store.getSnapshot().pending, null);
  assert.equal(store.getSnapshot().dirty, false);
  assert.equal(store.getSnapshot().needsRefresh, true);
  await store.save();
  await store.retry();
  assert.equal(transport.calls.length, 4);

  await store.refresh();
  assert.deepEqual(store.getSnapshot().document, latest);
  assert.equal(store.getSnapshot().etag, '"revision-three"');
  assert.equal(store.getSnapshot().needsRefresh, false);
  assert.match(store.getSnapshot().notice!.text, /Another client/);
  assert.doesNotMatch(store.getSnapshot().notice!.text, /rev_2|rev_3/);
  store.openForm(ID_A);
  assert.ok(store.getSnapshot().form);
  assert.equal(transport.remaining(), 0);
});

test('an empty replacement requires explicit confirmation and sends clear_all true only then', async () => {
  const saved = resource([], 'rev_2');
  const { store, transport } = await initialized(succeeded(saved), json(saved, 200, { ETag: '"revision-two"' }));
  store.deleteItem(ID_A);
  await store.save();
  assert.equal(transport.calls.length, 2);
  assert.equal(store.getSnapshot().dirty, true);
  assert.equal(store.getSnapshot().pending, null);

  await store.save(true);
  assert.deepEqual(JSON.parse(transport.calls[2].body!), { items: [], clear_all: true });
  assert.equal(store.getSnapshot().items.length, 0);
  assert.equal(store.getSnapshot().dirty, false);
  assert.equal(transport.remaining(), 0);
});

test('personal UI renews an expired browser session without token entry', async () => {
  const personal = () => json({ authenticated: true, personal_mode: true,
    csrf_token: CSRF, permissions: ['market-units:read', 'market-units:replace'] });
  const transport = script(personal(), json(resource(), 200, { ETag: ETAG }),
    json({ code: 'authentication_required' }, 401), personal(), json(resource(), 200, { ETag: ETAG }));
  const store = makeStore(transport.fetcher);
  await store.initialize();
  await store.refresh();
  assert.equal(store.getSnapshot().session?.personal_mode, true);
  assert.equal(store.getSnapshot().notice, null);
  assert.deepEqual(transport.calls.map(c => `${c.method} ${c.url}`), [
    'GET /api/session', 'GET /api/v1/market-units', 'GET /api/v1/market-units',
    'GET /api/session', 'GET /api/v1/market-units',
  ]);
});

test('personal UI renews CSRF and retries exactly the same pending save', async () => {
  const personal = (csrf: string) => json({ authenticated: true, personal_mode: true,
    csrf_token: csrf, permissions: ['market-units:read', 'market-units:replace'] });
  const original = resource([wireRow()]);
  const saved = resource([wireRow(ID_A, {units: '2'})], 'rev_2');
  const transport = script(personal('old-csrf'), json(original, 200, {ETag: ETAG}),
    json({code: 'csrf_invalid'}, 403), personal('renewed-csrf'),
    succeeded(saved), json(saved, 200, {ETag: '"revision-two"'}));
  const store = makeStore(transport.fetcher);
  await store.initialize();
  store.openForm(ID_A);
  store.updateForm({units: '2'});
  store.applyForm();
  await store.save();
  const puts = transport.calls.filter(c => c.method === 'PUT');
  assert.equal(puts.length, 2);
  assert.equal(puts[0].body, puts[1].body);
  assert.equal(puts[0].headers.get('Idempotency-Key'), puts[1].headers.get('Idempotency-Key'));
  assert.equal(puts[0].headers.get('If-Match'), puts[1].headers.get('If-Match'));
  assert.equal(puts[1].headers.get('X-CSRF-Token'), 'renewed-csrf');
  assert.equal(store.getSnapshot().pending, null);
  assert.equal(store.getSnapshot().dirty, false);
});
