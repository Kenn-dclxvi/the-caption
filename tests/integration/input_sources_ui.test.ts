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
  return { store, calls, remaining: () => queue.length };
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
