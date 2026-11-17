# Accretion Observatory

A local, inspectable X3D world that grows one validated addition at a time.
Six procedural families—orrery, coral, ziggurat, beacon, mycelium and gyroscope—
turn the Accretion design notes into a runnable learning environment. A manual
fragment editor supports your own experiments. No JEV key, model API, hosted
runtime or paid service is required.

This is a **new reference implementation from the two supplied design notes**.
The private source ZIP referenced by those notes was not supplied. The patch
therefore adds this implementation against an explicitly documented two-note
baseline; it does not claim to modify that unavailable application.

## Start

Install Python 3.12 or newer. On Windows double-click `run.bat`; on WSL/Linux/macOS
run `bash run.sh`. The launchers create `.venv`, install the two pinned Python
dependencies, and open the local author interface. Package installation needs
network access on first setup; the application and bundled renderer run locally.

Alternatively:

```sh
python3 -m pip install -r requirements.txt
python3 serve.py --open
```

The server binds to `127.0.0.1:8820`. The plain address is a read-only viewer.
Use the author URL printed by the server to enable Grow and Submit X3D. The
capability is consumed from the URL fragment and retained in that tab's session
storage. Keep that URL and `data/owner.key` private. This is local capability
authorization, not authentication of individual people. No cloud presence is
inferred.

On a new database, startup creates **24 authored procedural demo additions**.
These are seed content, not a recording of live model generation. Use
`python3 serve.py --demo-count 0 --data my-empty-world --open` for a blank world.
Each later click appends once; there is no background generation timer.

## Explore

1. Select an addition in the log and inspect its source, placement and admission.
2. Choose structural ambition 1–5, then Grow. The planner owns the cell and
   layer; the generator supplies local geometry inside that slot.
3. Use the history slider to preview a prefix without deleting anything.
4. Submit a small fragment through the editor. Try a `Script` or external URL
   to see a refusal recorded without advancing the world.
5. Verify history, then export both the evidence-bearing JSON archive and the
   merged `.x3d` scene. The X3D scene is visual interchange; the JSON is needed
   for ledger replay and admission records.
6. Read `Accretion-Field-Guide.html` for six experiments, design criticism,
   X3D/Loom connections and the path toward a provider adapter.

The browser loads at most 512 recent records. Only the selected detail budget
(24, 48 or 96 latest additions) uses full Inline content; other loaded additions
use bounds proxies. The full stored ledger remains available in the JSON
export. This bounded preview is not proof of 10,000-object rendering performance.

## What an append proves

The bounded fragment gate checks the restricted node/field vocabulary,
DEF/USE and local ROUTEs, numeric/cardinality limits, conservative animated
bounds, expanded resource counts and a gate-owned fit wrapper. It then runs
**real code from `hagopjay/x3d_mcp`**, pinned to
`b5c9956917714747fe1d034c729612e99b0f09c9`: X3D 4.0 XSD validation and upstream
semantic diagnostics. Upstream semantic diagnostics use a 4.1 UOM vocabulary;
that distinction is recorded in the instrument identity.

Only a passing result can enter a SQLite transaction. A head/tail compare-and-
swap prevents two contenders from receiving the same placement. The entry and
its accepted attempt commit together. Raw fragment, canonical fragment and
wrapped scene hashes bind the checks to exact bytes. Timestamps, plan,
instrument identities, policy and source digests are included in the entry hash.
Verification replays placement and checks these bindings; it does not silently
rerun validators or upgrade old evidence.

Admission is **`accretion.local-admission/v1`**, not a formal
`loom.receipt/1`. Render acceptance remains `not_run`. A visible illustrative
preview does not establish camera-pinned visibility, artistic quality, or
absence of objectionable flashing. The structural complexity number measures
quantity, not beauty. Read `docs/GATE-CONTRACT.md` for the exact accepted subset.

Hash continuity detects changes relative to a trusted checkpoint. It does not
establish authorship or stop an attacker replacing the entire database and its
checkpoint. Keep important checkpoints independently.

## Inspect and reproduce

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -O -m unittest discover -s tests -p 'test_*.py'
python3 tools/build_demo.py --count 24 --output examples
python3 tools/verify_export.py examples/world.json
python3 tools/benchmark_store.py --help
```

`examples/` contains a real validated snapshot and its checkpoint, not a fake
validator response. Independent new histories include fresh timestamps and
attempt IDs; they are not expected to have identical ledger hashes. Given the
same recorded plan, the procedural candidate is reproducible.

`reports/store-scaling.json` contains the measured 10/100-entry backend run,
instrument and machine identities, corpus plans and candidate digests. At 100
entries, cumulative append time was 4.333 s, replay verification 28.118 ms,
JSON 1,819,603 bytes and X3D 266,921 bytes on that rig. A 1,000-entry run was
not performed: the measured trend projected 154.386 s, above the benchmark's
90 s stop rule. These are backend measurements, not GPU or cloud benchmarks.

The next useful optimization is to replace repeated full-payload rescans with
transactionally maintained planning/index columns and deduplicate instrument
records by content hash. The current 10,000-entry cap is a configured bound,
not a measured capacity result.

## Files and provenance

- `accretion/`: gate, procedural generator, pinned MCP adapter, canonical codec,
  transactional ledger and independent archive verifier.
- `serve.py`, `web/`: loopback HTTP service and browser controls.
- `source-notes/`: the two original attachments, preserved byte for byte.
- `docs/DESIGN-REVIEW.md`: concrete corrections to the draft's cloud, storage,
  token, authorization and evidence assumptions.
- `vendor/x3d_mcp/ORIGIN.json`: exact upstream paths and hashes.
- `THIRD-PARTY-NOTICES.md`: renderer and validator provenance/licenses.
- `VALIDATION.md`: final measured checks and their scope.
- `GIT-PATCH.md`: patch baseline and application instructions.

The Loom mapping follows the inspected `x3d.loom` revision
`7a7d65709c16633afecc5b5e482d28202707db13`. No upstream repository was changed
or published. Historical model/pricing/capacity claims in the source notes are
not treated as verified behavior of this implementation.
