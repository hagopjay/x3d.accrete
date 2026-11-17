// Headless smoke test of the static (server-less) viewer, served from a sub-path like GitHub Pages.
// usage: node tools/pages_smoke.js [screenshot.png]   (needs the pre-installed Playwright + Chromium)
const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.x3d': 'model/x3d+xml', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.wasm': 'application/wasm' };
const server = http.createServer((req, res) => {
  const p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (!p.startsWith('/x3d.accrete/')) { res.writeHead(404); return res.end('nf'); }   // emulate project-pages sub-path
  const f = path.join(ROOT, p.slice('/x3d.accrete/'.length));
  if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end('nf'); }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(res);
});
(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const port = server.address().port, shot = process.argv[2];
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [], bad = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url()); });
  await page.goto(`http://127.0.0.1:${port}/x3d.accrete/web/index.html?static=1`);
  await page.waitForFunction(() => document.querySelector('#connection-status') && /STATIC/.test(document.querySelector('#connection-status').textContent), null, { timeout: 30000 });
  const out = { version: browser.version(), status: await page.textContent('#connection-status') };
  out.growDisabled = await page.$eval('#grow', b => b.disabled);
  await page.waitForTimeout(8000);   // let X_ITE assemble the world (software GL)
  await page.click('#verify');
  await page.waitForFunction(() => /Continuity|issue/.test(document.querySelector('#verify-result').textContent), null, { timeout: 30000 });
  out.verify = await page.textContent('#verify-result');
  out.verifyJson = JSON.parse(await page.textContent('#verify-json'));
  out.exportHref = await page.$eval('a.export-link', a => a.href);
  out.webgl = await page.evaluate(() => !!document.createElement('canvas').getContext('webgl2'));
  out.canvas = await page.evaluate(() => !!document.querySelector('x3d-canvas,canvas'));
  if (shot) await page.screenshot({ path: shot });
  out.errors = errors; out.bad = bad;
  console.log(JSON.stringify(out, null, 1));
  await browser.close(); server.close();
  process.exit(errors.length || bad.length || !out.verifyJson.valid || !out.growDisabled ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
