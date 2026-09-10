import assert from 'node:assert/strict';
import test from 'node:test';
import { MarketUnitsStore } from '../../src/web/market_units_editor/src/marketUnitsClient.ts';
import { InputSourcesStore, type InputSource, type ImportBatch } from '../../src/web/market_units_editor/src/inputSourcesClient.ts';

const source: InputSource = { id: 'source-1', revision: 'version-1', name: 'Test source', subject: 'importer',
  enabled: true, max_age_seconds: 3600, allow_unknown_as_of: false,
  targets: [{ asset_id: 'asset-a', quantity_unit: 'share', external_record_ids: ['record-a'] }],
  manual_override: ['asset-a'], last_sequence: 0, last_as_of: null };
const batch: ImportBatch = { id: 'batch-1', source_id: source.id, status: 'preview', diff_hash: 'confirmed-hash',
  diff: [{ asset_id: 'asset-a', before: '10', after: '123456789012345678.123456789012', changed: true }],
  request: { source_run_id: 'run-1', collected_at: '2026-09-10T00:00:00Z', as_of: null, sequence: 1 },
  committed_at: null, changed: null };
const assets = { items: [{ asset_id: 'asset-a', name: 'Saved asset', asset_class: 'JP_STOCK', units: '10' }] };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ETag: '"test"' } });
const loaded = (s = source, b = batch) => [json({ sources: [s] }), json(assets), json({ batches: [b] })];
type Call = { path: string; method: string; body: string | undefined; headers: Headers };
async function setup(replies: (Response | Error)[], permissions = ['input-sources:manage', 'market-units:read', 'imports:read', 'imports:commit']) {
  let ready = false, counter = 0;
  const calls: Call[] = [];
  const queue = [...loaded(), ...replies];
  const auth = new MarketUnitsStore(async (input, init) => {
    if (String(input) === '/api/session') return json({ csrf_token: 'csrf', permissions, authenticated: true });
    if (!ready) return json({ items: [], revision: 'initial', storage_state: 'ready', updated_at: null });
    calls.push({ path: String(input), method: init?.method ?? 'GET', body: init?.body?.toString(), headers: new Headers(init?.headers) });
    const reply = queue.shift(); assert.ok(reply, 'unexpected request');
    if (reply instanceof Error) throw reply;
    return reply;
  });
  await auth.initialize(); ready = true;
  const store = new InputSourcesStore(auth, () => `key-${++counter}`);
  await store.initialize();
  return { store, auth, calls, remaining: () => queue.length };
}

test('source save uses captured configuration revision and explicit resume IDs', async () => {
  const updated = { ...source, revision: 'version-2', manual_override: [] };
  const { store, calls } = await setup([json(updated), ...loaded(updated)]);
  store.edit(store.getSnapshot().sources[0]); store.updateForm({ name: 'Updated' }, ['asset-a']);
  await store.saveSource();
  const write = calls[3];
  assert.equal(write.method, 'PUT');
  assert.equal(write.headers.get('X-CSRF-Token'), 'csrf');
  const payload = JSON.parse(write.body!);
  assert.equal(payload.base_source_revision, 'version-1');
  assert.deepEqual(payload.resume_ids, ['asset-a']);
  assert.equal(payload.config.name, 'Updated');
  assert.equal(store.getSnapshot().form, null);
});

test('refresh preserves draft and rejects saving an old source configuration', async () => {
  const { store, calls } = await setup(loaded({ ...source, revision: 'version-2' }));
  store.edit(store.getSnapshot().sources[0]); store.updateForm({ name: 'Unsaved' });
  const form = store.getSnapshot().form;
  await store.refresh(); await store.saveSource();
  assert.equal(store.getSnapshot().form, form);
  assert.equal(calls.length, 6);
  assert.match(store.getSnapshot().notice!, /設定が更新/);
});

test('lost mutation response locks edits and retry keeps body/key and CSRF', async () => {
  const { store, calls } = await setup([new Error('lost response'), json(source), ...loaded()]);
  store.edit(store.getSnapshot().sources[0]);
  await store.saveSource();
  const form = store.getSnapshot().form;
  store.updateForm({ name: 'wrong' }); store.cancelForm(); await store.refresh(); await store.saveSource();
  assert.equal(store.getSnapshot().form, form);
  assert.equal(calls.length, 4);
  await store.retry();
  assert.equal(calls[3].body, calls[4].body);
  assert.equal(calls[3].headers.get('Idempotency-Key'), calls[4].headers.get('Idempotency-Key'));
  assert.equal(store.getSnapshot().pending, null);
});

test('expired receipt requires comparison GET and explicit reconciliation without automatic writes', async () => {
  const { store, calls } = await setup([json({ code: 'idempotency_result_expired' }, 409),
    new Error('comparison unavailable'), ...loaded()]);
  store.edit(store.getSnapshot().sources[0]); store.updateForm({ name: 'Unsaved' });
  await store.saveSource();
  assert.equal(store.getSnapshot().pending?.expired, true);
  const form = store.getSnapshot().form;
  await store.retry(); store.confirmReconciliation(); await store.saveSource();
  assert.equal(calls.length, 4);
  await store.refresh(); store.confirmReconciliation();
  assert.ok(store.getSnapshot().pending);
  await store.refresh();
  assert.equal(store.getSnapshot().form, form);
  assert.equal(store.canWrite, false);
  store.confirmReconciliation();
  assert.equal(store.canWrite, true);
  assert.equal(store.getSnapshot().form, null);
  assert.equal(calls.filter(c => c.method !== 'GET').length, 1);
});

test('successful write followed by failed GET cannot be saved again', async () => {
  const { store, calls } = await setup([json(source), new Error('GET failed'), ...loaded()]);
  store.edit(store.getSnapshot().sources[0]); await store.saveSource();
  assert.equal(store.getSnapshot().needsRefresh, true);
  assert.equal(store.getSnapshot().pending, null);
  store.edit(); await store.saveSource();
  assert.equal(calls.length, 5);
  await store.refresh(); assert.equal(store.canWrite, true);
});

for (const action of ['commit', 'cancel'] as const) {
  test(`batch ${action} uses the exact reviewed diff hash`, async () => {
    const done = { ...batch, status: action === 'commit' ? 'committed' as const : 'cancelled' as const };
    const { store, calls } = await setup([json(done), ...loaded(source, done)]);
    await store.actOnBatch(batch.id, action);
    assert.equal(calls[3].path, `/api/v1/import-batches/batch-1/${action}`);
    assert.deepEqual(JSON.parse(calls[3].body!), { diff_hash: batch.diff_hash });
    await store.actOnBatch(batch.id, action);
    assert.equal(calls.length, 7);
  });
}

test('batch conflict blocks new writes until refresh and preserves source form', async () => {
  const { store, calls } = await setup([json({ code: 'source_changed' }, 412)]);
  await store.actOnBatch(batch.id, 'commit');
  assert.equal(store.getSnapshot().pending, null);
  assert.equal(store.getSnapshot().needsRefresh, true);
  await store.actOnBatch(batch.id, 'commit');
  assert.equal(calls.length, 4);
});

test('view-only import permissions cannot mutate a batch', async () => {
  const { store, calls } = await setup([], ['input-sources:manage', 'market-units:read', 'imports:read']);
  await store.actOnBatch(batch.id, 'commit');
  assert.equal(calls.length, 3);
});


test('lost commit followed by permission denial retains request and permits read reconciliation', async () => {
  const permissions = ['input-sources:manage', 'market-units:read', 'imports:read', 'imports:commit'];
  const committed = { ...batch, status: 'committed' as const, changed: true };
  const { store, auth, calls } = await setup([new Error('lost response'),
    json({ code: 'permission_denied' }, 403), ...loaded(source, committed), json(committed)], permissions);
  await store.actOnBatch(batch.id, 'commit');
  const original = store.getSnapshot().pending!;
  permissions.pop();
  await store.retry();
  assert.equal(store.getSnapshot().pending?.denied, true);
  assert.equal(store.getSnapshot().pending?.key, original.key);
  assert.equal(store.getSnapshot().pending?.body, original.body);
  assert.equal(store.has('imports:commit'), false);
  assert.equal(store.has('imports:read'), true);
  assert.ok(auth.getSnapshot().session);
  await store.retry(); await store.actOnBatch(batch.id, 'commit');
  store.confirmReconciliation();
  assert.ok(store.getSnapshot().pending);
  await store.refresh();
  assert.equal(store.getSnapshot().comparisonLoaded, false);
  await store.compareOriginal();
  assert.equal(calls.at(-1)?.path, '/api/v1/import-batches/batch-1');
  assert.deepEqual(store.getSnapshot().originalResult, committed);
  assert.equal(store.canWrite, false);
  store.confirmReconciliation();
  assert.equal(store.getSnapshot().pending, null);
  await store.actOnBatch(batch.id, 'commit');
  assert.equal(calls.filter(c => c.method !== 'GET').length, 2);
});

test('permission denial offers reauthentication without losing pending request', async () => {
  const { store, auth, calls } = await setup([new Error('lost'), json({ code: 'permission_denied' }, 403)]);
  await store.actOnBatch(batch.id, 'cancel'); await store.retry();
  const pending = store.getSnapshot().pending;
  store.reauthenticate();
  assert.equal(auth.getSnapshot().session, null);
  assert.equal(store.getSnapshot().pending, pending);
  store.confirmReconciliation(); await store.compareOriginal();
  assert.equal(calls.length, 5);
});

test('browsing another source cannot reconcile the original expired batch', async () => {
  const otherSource = { ...source, id: 'source-2', name: 'Other source' };
  const otherBatch = { ...batch, id: 'batch-2', source_id: otherSource.id };
  const { store, calls } = await setup([json({ code: 'idempotency_result_expired' }, 409),
    json({ sources: [source, otherSource] }), json(assets), json({ batches: [otherBatch] }), json(batch)]);
  await store.actOnBatch(batch.id, 'commit');
  await store.select(otherSource.id);
  assert.equal(store.getSnapshot().selected, otherSource.id);
  assert.equal(store.getSnapshot().comparisonLoaded, false);
  store.confirmReconciliation();
  assert.equal(store.getSnapshot().pending?.sourceId, source.id);
  assert.equal(store.getSnapshot().pending?.batchId, batch.id);
  assert.equal(store.getSnapshot().pending?.action, 'commit');
  await store.compareOriginal();
  assert.equal(calls.at(-1)?.path, `/api/v1/import-batches/${batch.id}`);
  assert.equal(store.getSnapshot().comparisonLoaded, true);
  store.confirmReconciliation();
  assert.equal(store.getSnapshot().pending, null);
  assert.deepEqual(store.getSnapshot().batches, [otherBatch]);
  assert.equal(calls.filter(c => c.method !== 'GET').length, 1);
});

for (const [label, reply] of [
  ['failed GET', new Error('unavailable')],
  ['missing batch', json({ code: 'not_found' }, 404)],
  ['different batch', json({ ...batch, id: 'another-batch' })],
  ['different source', json({ ...batch, source_id: 'another-source' })],
] as const) {
  test(`original batch reconciliation rejects ${label}`, async () => {
    const { store, calls } = await setup([json({ code: 'idempotency_result_expired' }, 409),
      json({ sources: [source] }), json(assets), json({ batches: [] }), reply]);
    await store.actOnBatch(batch.id, 'cancel');
    await store.refresh(); store.confirmReconciliation();
    assert.ok(store.getSnapshot().pending);
    await store.compareOriginal(); store.confirmReconciliation();
    assert.equal(store.getSnapshot().comparisonLoaded, false);
    assert.equal(store.getSnapshot().originalResult, null);
    assert.ok(store.getSnapshot().pending);
    assert.equal(calls.filter(c => c.method !== 'GET').length, 1);
  });
}


for (const status of ['committed', 'cancelled'] as const) {
  test(`reconciliation carries ${status} into the list and prevents stale preview actions`, async () => {
    const done = { ...batch, status, changed: status === 'committed', committed_at: '2026-09-10T00:01:00Z' };
    const { store, calls } = await setup([new Error('lost response'),
      json({ code: 'idempotency_result_expired' }, 409), json(done)]);
    await store.actOnBatch(batch.id, status === 'committed' ? 'commit' : 'cancel');
    await store.retry();
    await store.compareOriginal();
    assert.equal(store.getSnapshot().batches[0].status, 'preview');
    store.confirmReconciliation();
    assert.deepEqual(store.getSnapshot().batches, [done]);
    assert.equal(store.getSnapshot().pending, null);
    assert.equal(store.getSnapshot().originalResult, null);
    await store.actOnBatch(batch.id, 'commit');
    await store.actOnBatch(batch.id, 'cancel');
    assert.equal(calls.filter(c => c.method !== 'GET').length, 2);
  });
}
