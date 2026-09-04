const assert = require('node:assert/strict');
const { createApi } = require('./api-client.js');

const calls = [];
const api = createApi({
  fetchImpl: async (path, options) => {
    calls.push([path, options]);
    return {
      ok: true,
      status: 200,
      async json() { return { ok: true }; },
    };
  },
});

api.request('/api/session');
api.request('/api/login', { username: 'fake-user', password: 'fake-password' });

setImmediate(() => {
  assert.deepEqual(calls[0], ['/api/session', {}]);
  assert.deepEqual(JSON.parse(calls[1][1].body), {
    username: 'fake-user', password: 'fake-password',
  });
  assert.equal(calls[1][1].headers['Content-Type'], 'application/json');
  console.log('Cliente da API: OK');
});
