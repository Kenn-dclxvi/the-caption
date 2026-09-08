import assert from 'node:assert/strict';
import test from 'node:test';
import { MarketUnitsStore } from '../../src/web/market_units_editor/src/marketUnitsClient.ts';
import { MonthlyInputsStore, type MonthlyResource, type MonthlyDocument } from '../../src/web/market_units_editor/src/monthlyInputsClient.ts';

const A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const EXACT = '123456789012345678.123456789012';
const ETAG = '"revision-1"';
type Call = { url: string; method: string; body: string | undefined; headers: Headers };
type Reply = Response | Error | ((call: Call) => Response | Promise<Response>);
function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}
function document(resource: MonthlyResource, revision = 'rev_1'): MonthlyDocument {
  const row = resource === 'external-assets' ? { entry_id: A, category: 'CASH_EXTERNAL', amount: EXACT, name: '' }
    : { entry_id: A, total_acquisition_cost_jpy: EXACT };
  return { revision, storage_state: 'ready', updated_at: null,
    months: { default: resource === 'external-assets' ? { items: [row as any] } : row as any } };
}
async function setup(resource: MonthlyResource, replies: Reply[], personal = false) {
  const calls: Call[] = [];
  const queue = [...replies];
  let sessionNumber = 0;
  let idNumber = 0;
  const auth = new MarketUnitsStore(async (input, init) => {
    const url = String(input);
    if (url === '/api/session') return json({ authenticated: true, personal_mode: personal,
      csrf_token: `csrf-${++sessionNumber}`, permissions: [`${resource}:read`, `${resource}:replace`, `${resource}:clear`] });
    if (url === '/api/v1/market-units') return json({ items: [], revision: 'funds', storage_state: 'ready', updated_at: null }, 200, { ETag: '"funds"' });
    const call = { url, method: init?.method ?? 'GET', headers: new Headers(init?.headers), body: init?.body?.toString() };
    calls.push(call);
    const reply = queue.shift();
    assert.ok(reply, `Unexpected request ${url}`);
    if (reply instanceof Error) throw reply;
    return typeof reply === 'function' ? reply(call) : reply;
  });
  await auth.initialize();
  const store = new MonthlyInputsStore(resource, auth, () => `00000000-0000-4000-8000-${String(++idNumber).padStart(12, '0')}`);
  await store.initialize();
  return { store, auth, calls, remaining: () => queue.length };
}

for (const resource of ['external-assets', 'portfolio-basis'] as const) {
  const initial = () => json(document(resource), 200, { ETag: ETAG });
  test(`${resource}: month move keeps ID and exact amounts in a local draft`, async () => {
    const { store, calls } = await setup(resource, [initial()]);
    store.openForm(A); store.updateForm({ month: '2026-09' }); store.applyForm();
    assert.equal(calls.length, 1);
    assert.equal(store.getSnapshot().items[0].entry_id, A);
    assert.equal(store.getSnapshot().items[0].month, '2026-09');
    assert.ok(JSON.stringify(store.payload()).includes(EXACT));
    assert.equal('default' in store.payload().months, false);
  });
  test(`${resource}: pending request survives network failure and retry uses identical identity`, async () => {
    const saved = document(resource, 'rev_2');
    const { store, calls } = await setup(resource, [initial(), new Error('connection lost'),
      json({ changed: false, change_id: null, resource: saved }), json(saved, 200, { ETag: '"revision-2"' })]);
    await store.save();
    const pending = store.getSnapshot().pending;
    assert.ok(pending);
    const items = store.getSnapshot().items;
    store.deleteItem(A); store.openForm(); await store.refresh(); await store.save();
    assert.equal(store.getSnapshot().items, items);
    assert.equal(calls.length, 2);
    await store.retry();
    assert.equal(calls[1].body, calls[2].body);
    assert.equal(calls[1].headers.get('Idempotency-Key'), calls[2].headers.get('Idempotency-Key'));
    assert.equal(calls[1].headers.get('If-Match'), ETAG);
    assert.equal(store.getSnapshot().pending, null);
    assert.equal(store.getSnapshot().etag, '"revision-2"');
  });
  test(`${resource}: conflict preserves draft and requires Refresh before saving again`, async () => {
    const { store, calls } = await setup(resource, [initial(), json({ code: 'revision_mismatch' }, 412)]);
    store.openForm(A); store.updateForm({ month: '2026-09' }); store.applyForm();
    await store.save();
    assert.equal(store.getSnapshot().conflict, true);
    assert.equal(store.getSnapshot().items[0].month, '2026-09');
    await store.save();
    assert.equal(calls.length, 2);
  });
  test(`${resource}: saving excludes unapplied form and makes that form stale`, async () => {
    const saved = document(resource, 'rev_2');
    const { store, calls } = await setup(resource, [initial(), json({ resource: saved }), json(saved, 200, { ETag: '"revision-2"' })]);
    store.openForm(A); store.updateForm({ month: '2026-09' });
    await store.save();
    assert.equal('2026-09' in JSON.parse(calls[1].body!).months, false);
    assert.equal(store.getSnapshot().form?.item.month, '2026-09');
    store.applyForm();
    assert.equal(store.getSnapshot().items[0].month, 'default');
    assert.match(store.getSnapshot().notice!.text, /older version/);
  });
  test(`${resource}: successful save followed by failed GET cannot be saved again`, async () => {
    const saved = document(resource, 'rev_2');
    const { store, calls } = await setup(resource, [initial(), json({ resource: saved }), new Error('GET failed')]);
    await store.save();
    assert.equal(store.getSnapshot().needsRefresh, true);
    assert.equal(store.getSnapshot().pending, null);
    assert.equal(store.getSnapshot().etag, null);
    assert.match(store.getSnapshot().notice!.text, /Saved successfully/);
    await store.save();
    assert.equal(calls.length, 3);
  });
  test(`${resource}: reauthentication does not reload over edited forms or drafts`, async () => {
    const { store, auth, calls } = await setup(resource, [initial()]);
    store.openForm(A); store.updateForm({ month: '2026-09' });
    await auth.login('new-test-credential'); await store.initialize();
    assert.equal(store.getSnapshot().form?.item.month, '2026-09');
    assert.equal(calls.length, 1);
    store.applyForm();
    await auth.login('new-test-credential'); await store.initialize();
    assert.equal(store.getSnapshot().items[0].month, '2026-09');
    assert.equal(calls.length, 1);
  });
  test(`${resource}: personal session renewal retries the exact PUT with fresh CSRF`, async () => {
    const saved = document(resource, 'rev_2');
    const { store, calls } = await setup(resource, [initial(), json({ code: 'csrf_invalid' }, 403),
      json({ resource: saved }), json(saved, 200, { ETag: '"revision-2"' })], true);
    await store.save();
    assert.equal(calls[1].body, calls[2].body);
    assert.equal(calls[1].headers.get('Idempotency-Key'), calls[2].headers.get('Idempotency-Key'));
    assert.equal(calls[1].headers.get('X-CSRF-Token'), 'csrf-1');
    assert.equal(calls[2].headers.get('X-CSRF-Token'), 'csrf-2');
    assert.equal(store.getSnapshot().pending, null);
  });
  test(`${resource}: invalid months and decimals cannot be applied to the draft`, async () => {
    const { store } = await setup(resource, [initial()]);
    store.openForm(A); store.updateForm({ month: '2026-13' }); store.applyForm();
    assert.equal(store.getSnapshot().dirty, false);
    store.updateForm({ month: 'default', amount: '-1', total_acquisition_cost_jpy: '0' }); store.applyForm();
    assert.equal(store.getSnapshot().dirty, false);
    store.cancelForm(); assert.equal(store.getSnapshot().form, null);
  });
  test(`${resource}: deleting all entries requires explicit confirmation`, async () => {
    const { store, calls } = await setup(resource, [initial()]);
    store.deleteItem(A); await store.save();
    assert.equal(calls.length, 1);
    assert.equal(store.payload().clear_all, true);
  });
}

test('external-assets: untouched empty month is preserved; deleting the last row removes its month', async () => {
  const doc = document('external-assets'); doc.months['2026-09'] = { items: [] };
  const { store } = await setup('external-assets', [json(doc, 200, { ETag: ETAG })]);
  assert.deepEqual(store.payload().months['2026-09'], { items: [] });
  store.deleteItem(A);
  assert.deepEqual(store.payload(), { months: { '2026-09': { items: [] } }, clear_all: true });
});

test('portfolio-basis: adding to an existing month retains its ID; moving onto a month retains the source ID', async () => {
  const doc = document('portfolio-basis');
  doc.months['2026-09'] = { entry_id: B, total_acquisition_cost_jpy: '2' };
  const { store } = await setup('portfolio-basis', [json(doc, 200, { ETag: ETAG })]);
  store.openForm(); store.updateForm({ month: '2026-09', total_acquisition_cost_jpy: '3' }); store.applyForm();
  assert.equal((store.payload().months['2026-09'] as any).entry_id, B);
  store.openForm(A); store.updateForm({ month: '2026-09' }); store.applyForm();
  assert.equal((store.payload().months['2026-09'] as any).entry_id, A);
  assert.equal(Object.keys(store.payload().months).length, 1);
});
