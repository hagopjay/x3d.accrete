# Accretion World: design review against the current X3D Loom

Reviewed 16 November 2026. The inputs were the two supplied design/build notes and the canonical Loom files at **`hagopjay/x3d.loom@7a7d65709c16633afecc5b5e482d28202707db13`**. The referenced original source ZIP and private artifact implementation were not available. This is a review of the documented design and the new local reference implementation's intended contracts; it does not reproduce the original 38-test claim or the private host's database permissions.

Sources read directly from that Git commit:

- `README.md`, `LOOM-v1.md` §§1–6 and the current law table.
- `GLOSSARY.md`.
- `kit/loomkit/accept.py` and `kit/loomkit/receipt.py`.

The source distinguishes a witness, a gate, a profile and an accepted-artifact receipt. That distinction is the most useful framework for advancing Accretion.

## 1. What deserves to survive

The core design is strong: a deterministic planner owns placement and limits, a generator proposes bounded local content, and code admits or rejects it. Append-only layers give experiments a history. Isolated patch execution contexts constrain names and ROUTEs. Repair rounds turn precise diagnostics into a constructive teaching loop. A generated skyline makes the history of work visible.

The next increment should make those boundaries demonstrable. The best local product can be useful with an authored generator and no model account: grow a world, inspect the exact patch, see which checks actually ran, replay placement and verify history. Hosted generation can later supply a proposal through the same narrow boundary.

## 2. A world log is not automatically a Loom receipt

The draft calls the gate a C witness and the ledger the receipt. These are useful intuitions but stronger schema claims need more precision.

At the pinned commit, `accept.py` admits a named profile only after it finds each required witness record, matches the candidate digest, excludes development records, checks allowed statuses, requires grade C for a pass, checks coverage and verifies evidence-file hashes. `receipt.py` then builds `loom.receipt/1` from that acceptance summary. A missing, stale or errored required witness cannot be replaced by a numerical score.

Use an application-specific schema for world entries and local admission records. A fragment-gate pass is a measured observation about that gate's supported subset. An XSD/semantic pass is an observation about the pinned validator. Neither automatically certifies the complete browser application, a renderer observation, host compatibility or aesthetic quality.

| Record | What it can establish | What it cannot establish alone |
| --- | --- | --- |
| Raw proposal identity | Which bytes the generator supplied | Whether the proposal is valid, bounded or attractive |
| Local fragment-gate record | Which whitelist, type, reference and resource rules passed | Full X3D conformance, runtime success or visibility |
| Pinned XSD/semantic record | What the named validator found in the exact wrapped scene | Browser appearance, performance or human preference |
| Append record | The accepted local payload, placement and admission evidence at one sequence | Authentic authorship or acceptance under an external Loom profile |
| Renderer observation | What one named browser/renderer/camera/time actually observed | Other hosts, other views or a real GPU if software GL was used |
| Formal Loom receipt | A completed acceptance decision over a declared candidate inventory and profile | Truth beyond those instruments' stated coverage |

Keep `not_run`, `error` and `fail` separate. If an optional validator is absent, show that absence and name the narrower local admission profile. If a profile requires it, refuse admission rather than quietly downgrading the requirement. A browser preview must not create a recorded render pass merely because the canvas exists.

Relevant laws: 2, 3, 5, 6, 13, 17, 19, 25, 34 and 36.

## 3. Atomic history beats a repaired cache story

The original shard-first/manifest-second scheme can be sound only if readers can reconstruct the authoritative head and writers cannot race during that reconstruction. A lease by itself is insufficient: a slow writer may continue after its lease expires while a new writer has acquired the lease.

A local SQLite reference can make the simpler boundary concrete:

1. Freeze proposal bytes and run its declared checks.
2. Begin a write transaction and read the current head.
3. Require the expected head and previous digest to match the proposal's planning context.
4. Recompute the deterministic placement from that head and compare the full plan.
5. Insert the entry, its evidence bindings and any authoritative counters in one transaction.
6. Commit before notifying viewers. Readers see either the earlier world or the committed successor.

Use an idempotency key for a retried append. Bind it to the proposed action and context: replaying the same request returns its existing result; reusing the key for different bytes must fail. In a future distributed store, use transactional revision comparison and a fencing token in addition to a renewable lease.

| Control | Expected outcome |
| --- | --- |
| Two appenders plan from the same head | At most one new entry commits; the other reports a stale-head conflict |
| A request is delivered twice | One content entry, one stable returned result |
| An idempotency key is reused with different content | Explicit conflict, not an accidental cache hit |
| The process stops before commit | No half entry or advanced head |
| The process stops after commit but before response | Retried request resolves to the committed entry |
| The manifest/cache is missing | Rebuild from authoritative entries; do not invent history |

Append-only means the application does not rewrite admitted content. It does not mean an administrator with filesystem/database control is physically unable to alter storage. State the threat model. SQLite transaction semantics are not a distributed database proof.

## 4. Presence is a creative condition, not identity or authority

The draft correctly separates owner authorization from presence. Carry that distinction into the local version. A browser heartbeat can show an active session; it cannot independently establish a distinct human. Two tabs, two client IDs and two signed-in identities are different quantities.

The local UI should call its observations sessions or viewers, show the expiry window, and mark solo/development mode explicitly. The server must authorize every mutation independently of room contents and UI button state. Presence disappearance during a long build needs a specified policy: permit the already-authorized append, or cancel before the commit check. Do not leave that rule to timing accidents.

In a hosted version, use the host's authenticated user identity and owner role, not a `by`, `isOwner` or `role` field supplied by the caller. Treat viewer nudges as untrusted creative input. A vote may influence a seed word; it must not change caps, witness requirements or write authority.

Relevant laws: 6, 13, 17 and 32.

## 5. Bind the bytes that will actually render

One patch has several legitimate identities: raw model reply, extracted fragment, normalized fragment, fitted fragment, wrapped X3D scene and the final world snapshot. They are not interchangeable.

Record separate full digests and make the transformation chain explicit. The validator must inspect the same wrapped candidate admitted to storage, including the auto-fit transform and any required component declarations. A successful raw-fragment check cannot be reused after normalization or fitting changes its bytes. The world planner's mode, cell, layer and seed are inputs too.

For application release claims, Loom law 17 is broader than a patch digest: it includes runtime, generator, tests, data, docs and vendored dependencies. Keep per-patch admission separate from a build-wide candidate inventory. Name both the validator Git commit and the actual vendored file/schema hashes; a commit label alone cannot prove that the running files were unchanged.

Long-running Python servers add a practical source-identity trap: imported modules may continue executing their old code after files change. Bind the loaded implementation at startup and refuse new collection after source drift, or restart against a frozen build. Hashing new source files while executing cached old modules would misname the instrument.

The new reference now also binds `created_utc` inside the hashed entry payload and requires the separately exported row timestamp to match it. A timestamp edit can no longer survive verification merely because that field sat outside the chain. This binds the recorded clock reading; it does not establish the clock's accuracy. The sequence number defines append order. Timestamps and attempt identities affect later chain-derived seeds, so two fresh runs with identical initial settings need not generate the same history; replay is against the recorded history and its declared inputs.

## 6. Hash chains need an external point of comparison

A hash chain can detect a changed or reordered entry **relative to a retained head/checkpoint**. An operator who controls the entire unsigned chain can rewrite its history and compute new hashes. Internal verification then succeeds on that different history.

Expose the head digest and allow users to retain a checkpoint outside the database. Import/verify should compare against the expected checkpoint when one is supplied. Preserve the canonicalization version and hash algorithm in records. Do not describe a self-consistent chain as authenticated authorship, a signature or proof that a named model ran.

Payload cost, attempt summaries and complexity metadata are outside the draft's content hash. That is acceptable only if they are explicitly nonauthoritative annotations. If they affect budgets, admission or planning, bind them into the relevant append transaction or an independently chained accounting event. Otherwise the value enforcing tomorrow's budget can be edited without breaking the content chain.

Relevant laws: 4, 14, 17, 24 and 35.

## 7. Bound animation over an interval, not one pose

Static transformed geometry is only one part of patch containment. A PositionInterpolator can move it outside its slot; a scale route can enlarge it; rotation can swing a long primitive past a static axis-aligned box. Nested transforms and scale orientation matter. Finite input values can also overflow when composed.

A conservative gate has three honest choices for each supported behavior:

- Compute a safe envelope over the declared key ranges and every supported transform.
- Use an intentionally loose radius/sphere envelope and fit it conservatively.
- Refuse the unsupported combination with a specific diagnostic.

It must not present a sampled or initial-pose bound as a certified whole-animation bound. Auto-fit should report original bounds, the applied scale and fitted bounds separately. Degenerate geometry, negative/zero scales, huge finite axes, nonfinite products, unsupported ROUTE targets and animated hierarchy combinations need explicit controls. Admission should be tested just inside and outside the slot limit.

The browser still needs its own behavior observation. The gate's interval envelope cannot establish event timing, renderer implementation behavior, visible non-emptiness or the appearance of an animation at a particular time.

Relevant laws: 2, 8, 19, 28, 32, 34 and 36.

## 8. Complexity is a rubric, not quality

The node/variety/ROUTE/custom-geometry/reuse score is deterministic and inspectable. It is useful for teaching and for testing a generator against an authored structural ambition. Its number is not a measurement of beauty, coherence, learnability or a human's preference.

The draft's statement that keeping the highest-scoring passing candidate means enrichment can only improve the result is true only for that fixed numeric rubric. A more cluttered patch can score higher and look worse. Call it a structural complexity score, retain the earlier passing candidate and record the selection rule. Human picks can be logged separately as labels without being retroactively inferred from the score.

A future optimizer needs shortcut-killer controls: duplicate tiny primitives, invisible transparent materials, decorative unused interpolators, redundant ROUTEs and more nodes than the silhouette needs. If those improve the score, document what the score measures rather than presenting the metric as universal taste.

Relevant laws: 6, 9, 21 and 25.

## 9. Timing cannot identify hidden thinking tokens

The original meter multiplies time before first visible text by later output throughput. That may be an exploratory correlate, but it cannot uniquely determine hidden tokens. Queue delay, network latency, prompt processing, cache behavior, consent, server scheduling and differing prefill/decode rates can all contribute to the same observed wait.

Keep measured timestamps, reply bytes and provider-reported usage as separate fields. If usage is unavailable, the hidden-token and billed-cost fields should be unknown, not reconstructed as an invoice. An authored budgeting scenario can be shown alongside them with its assumptions and model-price date, but the design's ±25% accuracy claim needs calibration data before it is repeated as measured accuracy.

The new no-model reference can report `model_calls = 0` and avoid a fictional spend meter. Future provider adapters should retain provider usage exactly, pin the returned model identity, separate owner plan usage from API billing, and key caches by the complete request identity. Do not carry the draft's model, effort or pricing claims forward as current facts without rechecking the provider interface.

Relevant laws: 4, 5, 11, 13, 15, 27 and 34.

## 10. Capacity follows serialized bytes

The count ceiling `25,000 documents × 48 patches` is not a demonstrated content capacity. Forty-eight maximum-size 12 KB fragments already total about 576 KB before JSON, above the stated 200 KB shard budget. At that maximum fragment size, the byte cap wins well before the count cap. Escaping, metadata, witnesses, titles and instructions add overhead.

Measure each complete serialized append before committing. Rotate shards when either the item cap or serialized-byte cap would be exceeded. A capacity estimate should use a measured distribution of committed entry sizes and explicitly reserve space for manifests, rejects, indexes and other document types. A million-patch load-time claim needs a measured streaming run; the arithmetic does not establish it.

Likewise, LOD limits visible detail but does not automatically remove parsing cost, event processing, TimeSensors or retained node graphs. A world may preserve all durable history while its viewport retains only a bounded working set. Keep those two meanings of retention separate. Name counts for durable entries, fetched records, proxy instances, full-detail instances and active animations.

### 10.1 Actual backend measurements from this edition

`reports/store-scaling.json` (`accretion.store-scaling/1`, recorded 16 November 2026) now supplies measured checkpoints at 10 and 100 entries. Every append ran the actual restricted fragment gate, pinned XSD/semantic validator and SQLite append transaction: no mock witness or prevalidated bypass was used. The workload began with an empty temporary database, used authored tier-3 procedural content and made zero model calls.

| Entries | Cumulative append wall time | Chain verification | JSON archive | X3D export | SQLite database |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10 | 1.742 s | 3.096 ms | 182,461 B | 27,077 B | 229,376 B |
| 100 | 4.333 s | 28.118 ms | 1,819,603 B | 266,921 B | 1,982,464 B |

These cumulative append timings include the application append method, including its return-time read of the current world. They exclude caller snapshot/detail reads and checkpoint export operations. The first append included lazy schema/validator initialization and took 1,591.718 ms. The 90-append stage from entry 11 through 100 had a median of 27.198 ms and a p95 of 45.225 ms. This is one shared Linux x86-64 runtime, CPython 3.12.14, one process and one writer; filesystem cache and scheduling were not isolated. The adapter records lxml 6.1.1 and jsonschema 4.26.0, plus its repository/schema identities.

**The requested 1,000-entry checkpoint was not run.** The runner's explicitly estimated projection was 154.386 s, above its configured 90 s stop rule. The projection fits a nonnegative per-append trend from early warm entries 2–10 and late entries 81–100, integrates it over entries 101–1,000 and adds projected verification/export overhead. That procedure is a budgeting estimate, not a 1,000-entry measurement or a validated scaling law. Preserve the `not_run` result rather than drawing a measured 1,000-entry point.

This is backend evidence only. It measures neither GPU/browser frame rate, cloud storage, network delivery, concurrent-author throughput, authenticated presence nor model latency/spend. The bundled preview runtime remains X_ITE 16.6.0, distinct from the draft's 16.7.1 claim; neither version changes the scope of this backend run.

### 10.2 The growing work and the bounded next change

Code inspection exposes a growing cost: snapshots and world summaries read and decode full historical payloads, and append returns another current-world view. Placement preparation also reconstructs state from historical plans. The early warm mean was 16.749 ms and the late mean was 39.913 ms in this run, consistent with increasing per-append work. These measurements are not a per-function CPU profile, so the exact share attributable to payload rescans is not isolated. Validator and source-identity checks contribute other costs.

The next change should remove the repeated work while preserving the evidence contract:

1. Maintain compact head, generated-cell count, cell-top and recent-cell indexes **in the same append transaction** as the authoritative entry. Rebuild and check these indexes from verified history; an unchecked cache must not become a second source of truth.
2. Read only the requested ordered entry window for the viewport. Preserve full history for explicit archive/export operations, rather than reconstructing it for each routine response.
3. Store repeated immutable instrument/schema manifests once by content digest and bind that digest in entries. Export every referenced object and verify its bytes so deduplication does not make an archive depend on an absent database.
4. Version the record/index contract and keep old entries interpretable. Do not rewrite historical hashes to obtain a smaller new schema.
5. Repeat the same actual-admission 10/100 workload before attempting 1,000 again. Compare candidate sizes, cold/warm conditions, verification correctness and exact failure controls as well as elapsed time.

This is a concrete backend optimization path, not a claim that the current world has demonstrated million-patch capacity.

## 11. A useful next witness matrix

| Witness/observation | Minimal meaningful control | Blind spot kept visible |
| --- | --- | --- |
| Fragment gate | Forbidden URL, malformed count, wrong-type ROUTE and animated escape each rejected by its own diagnostic; repaired twins pass | Complete standard and renderer behavior |
| Pinned schema/semantics | A deliberately schema-invalid scene and a schema-valid semantic fault are distinguished | Appearance and host timing |
| Append protocol | Concurrent stale-head attempts and duplicate request replay | Multiple machines/distributed service behavior |
| Chain replay | Edited, reordered and deleted entries fail against a retained checkpoint | A completely rewritten unsigned history without that checkpoint |
| Placement replay | Recomputed plan matches every committed entry | A creative generator's intent |
| Export | Decode and load an export with the app absent | Other renderer/version behavior |
| Runtime/eyes | Pinned candidate, camera, time, browser and viewport; visible/invisible controls | Off-camera content and untested hosts |
| Complexity rubric | Redundant/invisible complexity controls reported | Taste and human preference |

The original private application's test counts remain archived claims. Fresh tests must name the new reference implementation and its actual environment. An instrument crash is an error, never a successful negative-control catch. Law 19 gives that rule general scope; law 44's stricter second-reader/preregistered-limit provisions remain explicitly physics-first in the canonical document.

## 12. What this contributes back to Loom

Accretion is a compact laboratory for **incremental acceptance**: a bounded proposal changes a growing world, but each local admission must preserve a durable evidence path. The reusable contribution is not a broad new universal gate. It is a small set of counterexamples and contracts:

1. A stale-head writer must not append under a new plan.
2. A retried append must not grow twice.
3. A source edit must not inherit a stale validator pass.
4. An animation must not escape a static fit envelope.
5. A complete unsigned-chain rewrite must not be called authenticated history.
6. A higher complexity score must not become a human quality claim.
7. A time measurement must not become an unobserved token count.

Return each as a minimal failing fixture, repaired twin, named diagnostic and scoped test. That is the flywheel's useful unit. This review and the delivered source patch are local work; no external repository, private artifact, hosted account or public page was modified.
