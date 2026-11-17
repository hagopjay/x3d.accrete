# Static viewer on GitHub Pages

`web/index.html` runs in two modes with the same UI:

| Mode | When | Reads | Can grow? |
|---|---|---|---|
| live | `serve.py` answers `api/status` on loopback | `/api/*` from the local server | yes, with the author capability |
| static | any other host (GitHub Pages) or `?static=1` | `web/static-world/` (pre-exported files) | no, POSTs are refused |

Static mode is `web/static-mode.js`: a `fetch` shim that answers the UI's `/api/world`, `/api/entries/N`,
`/api/attempts`, `/api/status`, `/api/verify` from files, and rewrites the export links. `/api/verify` is **recomputed in the
browser** by `web/verify-archive.js`, a port of `verify_archive` (SHA-256 chain, `accretion-c14n/1`, placement replay, candidate byte
digests, witness/policy/pipeline bindings). It does not re-run the fragment gate or the pinned XSD/semantic validators; those ran when the
snapshot was built and are recorded in the archive. Parity with the Python verifier is tested in `tests/test_static_export.py`
(valid archive plus seven tamper cases, same verdict and error text).

## Rebuild the payload

```sh
python3 tools/build_demo.py --count 96 --output examples/demo-96      # real gate + pinned validators, ~4 s
python3 tools/export_static.py --archive examples/demo-96/world.json  # writes web/static-world/ (refuses an unverifiable archive)
python3 tools/export_static.py --archive examples/demo-96/world.json --check   # CI: fails if the payload is stale
node tools/pages_smoke.js shot.png                                    # headless Chromium, served under a /x3d.accrete/ sub-path
```

## Turn Pages on (needs repository owner)

Settings → Pages → Build and deployment → Source: **Deploy from a branch** → Branch **main**, folder **/ (root)** → Save.
The root `index.html` redirects to `web/index.html`. Live URL: <https://hagopjay.github.io/x3d.accrete/>.

Hosting adds no trust. The page verifies what it was given; to anchor trust, compare the checkpoint hash shown in the page with one
you obtained some other way (the published checkpoint in `manifest.json` comes from the same origin and is not independent).
