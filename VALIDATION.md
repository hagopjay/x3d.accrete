# Validation record — 2026-11-16

This record concerns the new local reference, not the unavailable private
Claude artifact described by the supplied notes. No model calls or external
repository writes were made.

## Automated checks

| Check | Observed result |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py'` | 85 tests pass, 3.959 s |
| Same command with `python3 -O` | 85 tests pass, 3.676 s |
| Python compilation and `node --check web/app.js` | Pass |
| Gate controls | 28 tests: malformed/restricted XML, typed references, field cardinality, transforms, supported animation envelopes, fit, expanded USE resource limits and source drift |
| Generator controls | 13 tests, including 90 family/tier local-gate controls and 30 actual-MCP controls |
| Pinned MCP adapter controls | 15 tests: real positive/negative XSD and semantic controls, missing dependency, source/schema/manifest/module-origin drift |
| Store and HTTP controls | 29 tests: stale and concurrent head races, atomic rollback, immutable records, candidate/witness/policy/placement/timestamp bindings, malformed exports, authorization, hostile origins and strict JSON |
| Public example archive | 24 entries, archive and checkpoint replay valid |
| Public merged X3D | 64,536 bytes; actual pinned XSD and semantic checks pass |

Normal and optimized test suites were executed concurrently in separate test
databases; timings are observations of that run, not isolated benchmarks.
The runtime was CPython 3.12.14, lxml 6.1.1 and jsonschema 4.26.0.

The 24-entry public example has checkpoint
`307fab65e7bb8a8bd91f42ed377ce2200e338e7804b9cce85792c6d7eea6d6bb`.
See `examples/admission-summary.json` for exact candidate, pipeline, instrument,
runtime and artifact hashes. The UI test world is a separate history with
different timestamps/attempt identities; its hashes are expected to differ.

## Browser observations

- Bundled X_ITE **16.6.0** rendered the initial 24-addition world and the later
  25-addition world in Chromium using a software WebGL/SwiftShader context.
  Camera framing visibly moved from the overall skyline to a selected sculpture.
  Full geometry and distance LOD proxies were both visible.
- The ordinary cloud browser could not create a WebGL context. It displayed
  the explicit fallback while source inspection, history controls, verification
  and local authoring remained usable. This is a tested fallback, not a claim
  that 3D rendering succeeded in that browser.
- A native author UI click appended exactly once: head 24 became 25. A separate
  read-only viewer observed the new head through its refresh path.
- Submitting `<Group><Script/></Group>` through the author editor displayed a
  rejected local attempt with `GATE_NODE_FORBIDDEN`. The head stayed at 25.
- The viewer showed the actual fragment/XSD/semantic passes and rendered
  visibility **NOT RUN**, with separate instrument scopes.
- Verify history reported continuity matching 24 entries before growth and
  25 afterward. The UI explicitly distinguished this from authorship.
- The history slider previewed head 10 while retained head stayed 25; Follow
  live tail returned the preview to 25.
- In a 390 px iframe, the effective document width and scroll width both
  measured 375 px (the frame has a scrollbar): no horizontal overflow was
  observed. The world panel moved ahead of authoring controls.
- The self-contained field guide rendered and its section navigation worked.

Relative Inline URLs were repaired to absolute, same-origin, allowlisted URLs
because scenes parsed from strings have a distinct URL base. X_ITE also awaits
resource completion and a browser frame before scene replacement. Occluded
software-rendered windows delayed that observation in this environment; no
load-time SLA or isolated browser timing benchmark is claimed. See
`docs/RENDERING.md` for the current loading and LOD limits.

These are human-facing smoke observations, **not a formal render witness**:
there is no isolated, candidate-bound camera/time/viewport capture suite or
visibility control pair. Admission records correctly retain render `not_run`.
No FPS, GPU capacity, visual parity across renderers, distributed presence,
cloud crash recovery or formal `loom.receipt/1` acceptance is asserted.

## Measured backend scaling

Every append in this run used the actual gate and pinned MCP checks. No mock
witnesses or bypasses were used. The benchmark used a fresh temporary SQLite
database, one process and one writer; no database or owner key was retained.

| Entries | Cumulative append | Verify | JSON archive | X3D export | Database |
|---|---:|---:|---:|---:|---:|
| 10 | 1.742456 s | 3.096 ms | 182,461 B | 27,077 B | 229,376 B |
| 100 | 4.333409 s | 28.118 ms | 1,819,603 B | 266,921 B | 1,982,464 B |
| 1,000 | Not run | Not run | Not measured | Not measured | Not measured |

The first append included 1,591.718 ms of cold startup. Entries 11–100 had
median 27.198 ms and p95 45.225 ms. The warm trend projected 154.386 s for the
1,000-entry target, exceeding the runner's declared 90 s stop rule; that
projection is a budgeting estimate, not a measured scaling law.

`reports/store-scaling.json` records the rig, source/instrument identities,
measurement boundaries, corpus plans/digests and report digest. Repeated full
payload scans are visible in code and are a plausible growing cost; no
function-level CPU profile isolates their exact contribution. Transactional
placement indexes and content-addressed instrument manifests are proposed next
steps, not implemented optimizations. The 10,000-entry configured limit remains
unbenchmarked. None of these backend measurements establishes GPU or cloud
performance.

## Distribution checks

The source notes are byte-identical to the two attachments. The two field-guide
copies match. Vendored MCP files retain their upstream hashes and licenses.
The additive patch is checked and applied against an independent two-note
baseline, then compared byte for byte with the distributed project. Runtime
databases, author capabilities, caches and virtual environments are excluded.
