'use strict';

// Exercise the shipped browser handlers with controlled network completion
// order. No DOM library, model calls or browser credentials are needed.
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');

const source = readFileSync(join(__dirname, '../src/cutting_layout/workbench/static/app.js'), 'utf8');
const deferred = () => {
  let resolve;
  const promise = new Promise(done => resolve = done);
  return {promise, resolve};
};

function harness() {
  const nodes = new Map();
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {
      id: selector.slice(1), value: '', checked: false, disabled: false,
      hidden: false, innerHTML: '', textContent: '', controls: [],
      querySelectorAll() {return this.controls;},
    });
    return nodes.get(selector);
  };
  const rendered = [];
  const context = vm.createContext({
    document: {querySelector: node, addEventListener() {}},
    history: {replaceState() {}}, location: {hash: ''}, crypto: webcrypto,
    setTimeout() {return 1;}, clearTimeout() {},
    // The automatic login probe stays pending; tests supply the session and
    // control subsequent requests through the same api call sites.
    fetch() {return new Promise(() => {});}, rendered,
  });
  vm.runInContext(source, context);
  vm.runInContext(`
    me={id:'alice', username:'alice', role:'employee', csrf:'test'};
    drawOrders=()=>{}; drawDetail=()=>rendered.push(detail.order.id);
    drawResults=()=>{}; drawAudit=()=>{}; schedulePoll=()=>{};
    refreshOrders=async()=>{};
  `, context);
  const evaluate = code => vm.runInContext(code, context);
  const state = () => JSON.parse(evaluate('JSON.stringify({current,detail,workspaceEpoch,requestKey})'));
  return {context, node, evaluate, state, rendered};
}

test('a delayed order cannot replace the order opened more recently', async () => {
  const h = harness(), first = deferred(), second = deferred();
  h.context.network = path => path === '/orders/a' ? first.promise : second.promise;
  h.evaluate('api=network');
  const openingA = h.evaluate("openOrder('a')");
  assert.match(h.node('#workspace').innerHTML, /正在读取订单/);
  const openingB = h.evaluate("openOrder('b')");
  second.resolve({order: {id: 'b'}});
  await openingB;
  first.resolve({order: {id: 'a'}});
  await openingA;
  assert.equal(h.state().current, 'b');
  assert.equal(h.state().detail.order.id, 'b');
  assert.deepEqual(h.rendered, ['b']);
});

test('returning to the same order also invalidates an earlier response', async () => {
  const h = harness(), old = deferred();
  h.evaluate("current='a'; workspaceEpoch=1");
  h.context.network = () => old.promise;
  h.evaluate('api=network');
  const loading = h.evaluate("refreshDetail('a',1)");
  h.evaluate("workspaceEpoch=3; detail={order:{id:'a',title:'newer'}}");
  old.resolve({order: {id: 'a', title: 'older'}});
  assert.equal(await loading, false);
  assert.equal(h.state().detail.order.title, 'newer');
});

test('logout invalidates pending order details', async () => {
  const h = harness(), response = deferred();
  h.evaluate("current='a'; workspaceEpoch=1");
  h.context.network = () => response.promise;
  h.evaluate('api=network');
  const loading = h.evaluate("refreshDetail('a',1)");
  h.evaluate('loginPage()');
  response.resolve({order: {id: 'a'}});
  assert.equal(await loading, false);
  assert.equal(h.state().detail, null);
  assert.equal(h.state().current, null);
});

test('editing parameters or their source revokes the previous confirmation', () => {
  const h = harness(), confirm = h.node('#confirm');
  for (const id of ['demand', 'stocks', 'kerf', 'stack', 'source']) {
    confirm.checked = true;
    h.evaluate("requestKey='old-request'");
    h.context.changed = {target: {id}};
    h.evaluate('invalidateConfirmation(changed)');
    assert.equal(confirm.checked, false);
    assert.equal(h.state().requestKey, null);
  }
  confirm.checked = true;
  h.evaluate("invalidateConfirmation({target:{id:'confirm'}})");
  assert.equal(confirm.checked, true);
});

test('pending forms lock both review decisions and restore disabled states', () => {
  const h = harness();
  const approve = {disabled: false}, reject = {disabled: false}, readonly = {disabled: true};
  h.node('#review').controls = [approve, reject, readonly];
  const unlock = h.evaluate("lockForms('#review')");
  assert.equal(approve.disabled, true);
  assert.equal(reject.disabled, true);
  unlock();
  assert.equal(approve.disabled, false);
  assert.equal(reject.disabled, false);
  assert.equal(readonly.disabled, true);
});

function generationForm(h) {
  for (const [id, value] of Object.entries({demand: '1200 × 6', stocks: '6000', kerf: '3', stack: '2', source: '虚构验收'})) {
    h.node('#' + id).value = value;
  }
  h.node('#confirm').checked = true;
  const button = {disabled: false};
  h.node('#generate').controls = [...['demand', 'stocks', 'kerf', 'stack', 'source', 'confirm'].map(id => h.node('#' + id)), button];
  h.context.submit = {preventDefault() {}, submitter: button};
  h.evaluate("current='a'; workspaceEpoch=1; detail={order:{id:'a',proposal:null},versions:[]}");
  return button;
}

test('generation keeps its order context when the follow-up read arrives late', async () => {
  const h = harness(), posted = deferred(), reread = deferred();
  const button = generationForm(h);
  const requests = [];
  h.context.network = (path, payload) => {
    requests.push({path, payload});
    if (path === '/orders/a/generate') return posted.promise;
    if (path === '/orders/a') return reread.promise;
    return Promise.resolve({order: {id: 'b'}});
  };
  h.evaluate('api=network');
  const generating = h.evaluate('generateSubmit(submit)');
  assert.equal(button.disabled, true);
  assert.equal(h.node('#kerf').disabled, true);
  assert.equal(requests[0].path, '/orders/a/generate');
  assert.equal(requests[0].payload.parameters.demand['1200'], 6);
  posted.resolve({id: 'version-a'});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests[1].path, '/orders/a');
  await h.evaluate("openOrder('b')");
  reread.resolve({order: {id: 'a'}});
  await generating;
  assert.deepEqual(h.rendered, ['b']);
  assert.equal(h.state().detail.order.id, 'b');
});

test('a network failure unlocks the form and retries with the same submission key', async () => {
  const h = harness(), button = generationForm(h), keys = [];
  h.context.network = async (path, payload) => {
    keys.push(payload.request_key);
    throw Error('模拟响应丢失');
  };
  h.evaluate('api=network');
  await h.evaluate('generateSubmit(submit)');
  assert.equal(button.disabled, false);
  assert.equal(h.node('#kerf').disabled, false);
  await h.evaluate('generateSubmit(submit)');
  assert.equal(keys.length, 2);
  assert.equal(keys[0], keys[1]);
});
