/* Accretion static read-only mode.
 *
 * Loaded before app.js. On loopback, a live serve.py that answers api/status wins and this file does nothing
 * (add ?static=1 to force the static copy). Anywhere else (GitHub Pages, file hosting) it answers the UI's /api/* requests from the
 * pre-exported files in static-world/ and verifies the archive in the browser with
 * verify-archive.js. No write path exists: POSTs are refused.
 */
(function () {
  'use strict';
  const realFetch = window.fetch.bind(window);
  const base = new URL('static-world/', document.baseURI).href;
  const json = (value, status) => new Response(JSON.stringify(value), { status: status || 200, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
  let mode = null, archive = null, manifest = null;

  const forced = new URLSearchParams(location.search).has('static');
  const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname);
  const decide = (async () => {
    if (loopback && !forced) {   // a local serve.py wins; remote hosts never probe /api (avoids a pointless 404)
      try {
        const live = await realFetch(new URL('api/status', document.baseURI), { cache: 'no-cache' });
        if (live.ok && (live.headers.get('content-type') || '').includes('json')) { const b = await live.json(); if (b && b.capabilities) return 'live'; }
      } catch (_) { /* no server */ }
    }
    try {
      const m = await realFetch(base + 'manifest.json', { cache: 'no-cache' });
      if (m.ok) { manifest = await m.json(); return 'static'; }
    } catch (_) { /* no static world either */ }
    return 'none';
  })();

  async function getArchive() {
    if (!archive) { const r = await realFetch(base + 'api/export.json'); if (!r.ok) throw new Error('static archive missing'); archive = await r.json(); }
    return archive;
  }
  function staticCapabilities() {
    return { writer: false, cloud_presence: false, actual_mcp: false, local_reference: true, model_calls: 0, static: true,
      identity_scope: 'Static read-only snapshot; no author capability and no server.' };
  }
  async function answer(url, options) {
    const path = url.pathname.replace(/^.*\/(?=api\/|patches\/)/, '/');
    if (options && options.method && options.method !== 'GET') return json({ error: 'This is a static read-only snapshot. Run serve.py locally to grow a world.' }, 403);
    if (path === '/api/status') return json({ capabilities: staticCapabilities(), mcp_probe: { status: 'static', note: 'Validators were run when the snapshot was built; see the archive.' } });
    if (path === '/api/world') { const r = await realFetch(base + 'api/world.json'); const w = await r.json(); w.capabilities = staticCapabilities(); return json(w); }
    if (path === '/api/attempts') return json({ attempts: [] });
    if (path === '/api/verify') {
      const a = await getArchive();
      const result = await window.AccretionVerify.verifyArchive(a, manifest && manifest.checkpoint);
      result.published_checkpoint = manifest && manifest.checkpoint;
      return json(result);
    }
    const m = path.match(/^\/api\/entries\/(\d{1,6})$/);
    if (m) return realFetch(base + 'api/entries/' + Number(m[1]) + '.json');
    return json({ error: 'No such static resource' }, 404);
  }
  window.fetch = async function (input, options) {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (!/\/(api|patches)\//.test(url.pathname) || url.origin !== location.origin || url.href.startsWith(base)) return realFetch(input, options);
    if ((await decide) !== 'static') return realFetch(input, options);
    try { return await answer(url, options); } catch (e) { return json({ error: String(e.message || e) }, 500); }
  };
  window.AccretionStatic = { base, ready: decide.then(m => m === 'static') };
  document.addEventListener('DOMContentLoaded', async () => {
    if ((await decide) !== 'static') return;
    document.documentElement.dataset.mode = 'static';
    for (const a of document.querySelectorAll('a[href^="api/export"]')) {
      const name = a.getAttribute('href').replace('api/', '');
      a.setAttribute('href', base + 'api/' + name);
    }
  });
})();
