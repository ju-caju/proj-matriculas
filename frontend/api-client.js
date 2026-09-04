/* Small transport adapter.  UI code depends on this contract, not fetch details. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ApiClient = api;
})(globalThis, function () {
  function createApi({ fetchImpl, onUnauthorized } = {}) {
    const requestFetch = fetchImpl || globalThis.fetch.bind(globalThis);
    const unauthorized = onUnauthorized || (() => {});

    async function request(path, data) {
      const options = data === undefined ? {} : {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      };
      const response = await requestFetch(path, options);
      const result = await response.json();
      if (!response.ok) {
        if (response.status === 401) unauthorized();
        throw new Error(result.error || 'Não foi possível concluir.');
      }
      return result;
    }

    return { request };
  }

  return { createApi };
});
