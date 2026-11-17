# Accretion World

*A persistent X3D world that Claude Haiku 5.5 grows one validated patch at a time, but only while people are there to watch it grow.*

**Live:** https://claude.ai/artifact/MHgC3NGwRwppwXZcnxpR56 (version 2, private to Jason until shared)
**Source:** `/home/claude/x3dworld`: `src/x3dgate.js` (the gate), `src/page.html` (the world), `build.js`, `test/`
**Status, 13 Nov 2026:**
- Gate: 38 tests passing.
- End to end, against a mocked runtime: the owner flow, a viewer on a phone, the dormant gate, and a tier-5 enrich run all pass.
- Hash chain verified.
- Not yet done: a live round trip with real Haiku, which needs two people on the page or the solo toggle.

---

## 1. The idea in one breath

A world that **only grows**. Each growth step is one *patch*: a small X3D 4.0 fragment that Haiku writes and a deterministic gate checks. It is then stamped into a hash-chained ledger and placed on a spiral that the world chooses, not the model. Nothing is ever erased.

The world is **alive** only when two or more distinct people have it open. Growth is a human act: the owner presses **Grow**, or opts into auto-grow, which runs only while the world is alive.

Three authorities, cleanly separated:

| Who | Decides | Can't decide |
|---|---|---|
| **The world** (deterministic JS) | where the patch goes, generate vs. augment, which cell, which layer, the seed word, the tier budget, whether it's stored | what the patch looks like |
| **Haiku 5.5** | the content: geometry, materials, animation, title, and a one-line note to the next builder | position, size beyond its slot, anything outside the whitelist |
| **The gate** (deterministic JS) | valid or not, auto-fit scale, canonical form, complexity score | taste |

This is the Loom's principle in miniature. The generator is untrusted ("S", suspected). The gate is a named, measuring witness ("C", measured). The ledger is the receipt.

## 2. How one patch is born

```mermaid
flowchart LR
  A[Owner presses Grow<br/>world alive ≥ 2 people] --> B[Lease world/lock<br/>one writer tab]
  B --> C[Read tail shards<br/>head, prevHash, cells]
  C --> D[Plan: PRNG of prevHash+head<br/>generate | augment, cell, layer, seed]
  D --> E[Prompt: directive + world so far<br/>+ neighbours + complexity tier]
  E --> F[Haiku 5.5 via sample<br/>effort from tier]
  F --> G{Gate x3dgate/1.0.0}
  G -- reject --> R[Repair round<br/>errors fed back]
  R --> F
  G -- pass, below tier floor<br/>tiers 4–5 --> N[Enrich round<br/>metrics fed back]
  N --> F
  G -- pass --> H[Best passing patch]
  H --> I[SHA-256 over prev + slot + text + X3D]
  I --> J[Append to shard doc<br/>then manifest + spend]
  J --> K[Every open view:<br/>onSnapshot → Inline → LOD]
  R -. still failing .-> X[world/rejects ring<br/>cost logged, never stored]
```

## 3. Platform mapping (what the artifact runtime gives us)

| Need | Capability | How it's used |
|---|---|---|
| "Alive" = ≥ 2 people | `room` presence | Distinct people counted by `by` (user id), not by tab. Presence also carries the owner's phase ("Haiku is writing #12…") to every viewer. |
| Haiku 5.5 | `sample` | `model: "claude-haiku-5-5"`, `modelTier: "quick"` as fallback, `effort` from the tier, `cache: false`. Billed to the **owner's** Claude usage after a one-time consent prompt. |
| Persistence | `db` | `world/manifest`, `world/rejects`, `world/lock`, `shards/s000000…`. Rules: `world` and `shards` readable at view level, writable by the owner only (verified: a Contributor's write is refused). |
| Who's the owner | `user` | `isOwner()` gates every write control. |
| One writer | `db.acquire` lease | `world/lock`, 180 s TTL, so two owner tabs can't race the chain. |

Growth is **button-driven**, which fits the platform's guidance that a page asks Claude on a person's action, not on a timer. Auto-grow (one patch every 60 s) is opt-in per visit, stops when the world goes dormant, and turns itself off on a usage limit.

## 4. The gate: x3dgate/1.0.0

A deterministic pipeline. The same bytes always give the same verdict, the same canonical X3D and the same hash.

1. **Extract.** It accepts a bare fragment or an `<X3D><Scene>` wrapper and keeps only the scene children.
2. **Parse.** Strict XML with no DTD, no entities beyond the five standard ones, no CDATA, and no text content.
3. **Whitelist.** 31 node types from X_ITE's core bundle, plus `ROUTE`. Each field is typed (SFVec3f, MFInt32, SFRotation and so on) and range-checked, then clamped or rejected.
   - **Forbidden, each with a named reason:**
     - `Text` and `FontStyle`: the fonts are blocked by the host's content security policy (CSP);
     - textures, URLs, `Inline`, `Anchor`: no external loads;
     - `Script`, shaders, PROTOs;
     - `Viewpoint`, `Background`, `Fog`, `NavigationInfo`: global state;
     - `LOD`: the world owns LOD.
4. **Semantics.**
   - IndexedFaceSet and IndexedLineSet indices must point at real points.
   - ElevationGrid `height` must have exactly x×z values. This is the add-on crash case from the BLACKBOX lab.
   - Interpolator key and keyValue counts must match, with keys ascending in [0, 1].
   - ROUTEs are typed end to end, and only DEFs inside the patch can be routed.
5. **Caps.** 80 nodes, 1 light (forced `global='false'`), 2 TimeSensors with `cycleInterval ≥ 0.5 s` (no strobing), 12 ROUTEs, 32 keys, 12 KB.
6. **Bounds.** A conservative bounding box through every Transform, including animated translation and scale ranges.
   - Anything that reaches past 3 m from its slot centre is **auto-fit**: scaled down, not rejected.
   - Anything past 120 m is nonsense and is rejected.
7. **Canonical form.** Attributes are written in a fixed order, numbers normalised, and DEFs prefixed. That output is what gets hashed and stored.

**Isolation at render time.** Each patch renders inside its own X3D `Inline`, loaded from a `data:` URL (an in-page fetch shim gets around the CSP). Its DEFs, ROUTEs and TimeSensors therefore live in their own execution context. Two patches can both say `DEF='Spin'` and never meet.

**The MCP slot.** The pipeline is a list of stages, `{name, enabled, run(candidate, ctx)}`. `x3d_mcp` already sits there, switched off. To turn it on, make x3d_mcp reachable as a claude.ai connector, or as a local MCP in the Claude app. Then declare the `mcp` capability with that server and its validate tool, and set `enabled: true`. Its verdict then joins the XSD and semantic checks as a second, independent witness.

## 5. Determinism and placement

- **Seed:** `rng(prevHash + ":" + head)`. The ledger itself is the entropy, so replaying the chain replays every directive.
- **Generate:** the next cell of an outward Ulam square spiral, with 8 m cells.
- **Augment:** about 42% of the time, a cell touched recently gets a new layer stacked 6.6 m above, up to 6 layers.
  - Towers grow where activity is, and ground expands outward. The world gets a skyline and a frontier.
- **Seed word:** one of 48 nouns (tide, orrery, mycelium, ziggurat…), picked by the same PRNG. A loose theme, freely interpreted.
- **Instruction chain:** every patch leaves one imperative sentence for the next builder. The ledger reads as a story told by many hands.

## 6. Storage and growth math (it never erases)

- **Shards:** `shards/s000000` and on, each holding at most 48 patches or 200 KB, under the store's 256 KiB document cap. The shard is written first and is the source of truth. The manifest is a cache.
- **Capacity:** 25,000 documents × 48 patches ≈ **1.2 million patches** before the cap. At auto-grow speed (60 an hour), that is about 2.3 years of continuous life.
- **Hash chain:**

  ```
  hash = SHA-256(prev, n, mode, cell, level, target, title, instruction, gate, fit, x3d)
  ```

  Changing any byte of history breaks every hash after it. Cost and complexity metadata sit **outside** the hash: they are estimates, not content.
- **Rejects:** a 40-item ring in `world/rejects`, holding each reject's errors, a 400-character excerpt and its cost. Rejected patches are never stored as world content.

## 7. Render budget

- The newest 240 patches render at **full detail** behind an LOD (90 m). Older ones render as **tinted proxy boxes**, sized and coloured from stored metadata.
- Views auto-load up to 2,400 patches, then offer **Load older**.
- Big loads are spread over animation frames, at most 40 node builds per frame.
- The ground grid grows ring by ring, and the overview camera reframes itself from the tallest stack and the widest ring.

## 8. The complexity slider

One control moves five things together: **effort, context depth, ambition, node target and retry budget.**

| Tier | Name | Effort | Nodes | Context (recent patches · augment excerpt) | Repair / enrich rounds | Score floor | Brief to Haiku |
|---|---|---|---|---|---|---|---|
| 1 | Sketch | medium | 8–20 | 6 · 2,000 chars | 1 | — | A few well-placed primitives, one palette |
| 2 | Study | medium | 18–36 | 10 · 3,000 | 1 | 1.5 | Clear silhouette, ≥ 2 materials, maybe one gentle animation |
| 3 | Structure *(default)* | high | 30–55 | 12 · 4,000 + neighbours | 1 | 2.5 | DEF/USE reuse plus a TimeSensor → interpolator → ROUTE animation |
| 4 | Mechanism | high | 45–70 | 16 · 5,000 + neighbours | 2 | 3.2 | ≥ 2 independently animated parts, custom geometry, one local light |
| 5 | Organism | high | 60–80 | 20 · 6,000 + neighbours | 2 | 3.8 | Layered custom geometry, one shared clock, repetition with variation, a visual answer to its neighbours |

- **Neighbours (tiers 3 to 5):** the prompt lists the cells to the north, east, south and west: their height in layers and the title of the top patch, so pieces can answer each other.
- **Planning nudge (tiers 4 and 5):** "This task involves multistep spatial reasoning. Plan the parts, their coordinates and the animation clock before writing any X3D." The effort docs recommend this kind of targeted guidance.

**Complexity score (0 to 5, deterministic, measured on the accepted fragment):**

```
nodes      ≥10 → 1   ≥25 → 2   ≥45 → 3   ≥65 → 3.5
variety    ≥8 types → +0.5     ≥12 → +1
animation  ≥2 ROUTEs → +0.5    ≥4 ROUTEs and ≥2 interpolators → +1
custom     1 kind (Extrusion/IFS/ElevationGrid/…) → +0.5   ≥2 → +0.75
reuse      any USE → +0.25                                   (capped at 5)
```

**The enrich loop (tiers 4 and 5).** Suppose a patch *passes* the gate but scores below the tier's floor. Haiku gets one more round, with its own measurements and the scoring rubric fed back ("keep the idea, make it richer").
- The **best passing** version is always kept, so enriching can only improve the result.
- If an enrich round breaks validity, the earlier passing patch is stored instead.
- Every attempt (first, repair, enrich) shows in the Gate tab with its score and its cost.

## 9. What it costs: Haiku 5.5 per round trip

### Prices (verified 13 Nov 2026)

| Claude Haiku 5.5 | Input | Output (thinking included) | Cache read | Batch in / out |
|---|---|---|---|---|
| Prompts ≤ 100,000 tokens | **$0.10 / MTok** | **$0.50 / MTok** | $0.01 / MTok | $0.05 / $0.25 |
| Prompts > 100,000 tokens | $0.50 / MTok | $2.50 / MTok | $0.05 / MTok | $0.25 / $1.25 |

Our prompts are about 2–4K tokens. The page's Claude bridge caps a prompt at 256 KiB, which is also our practical ceiling. **The 100K-token cliff is never reached by construction.**

### How the page measures a call (it sees text, not usage)

The `sample` bridge returns the answer text and the model that answered. It returns **no token counts**. So the meter builds a *correlate* from things it can observe:

```
in_tok    ≈ est(prompt) + 300                     (300 = assumed platform framing)
out_tok   ≈ est(reply)
est(s)    = prose_chars / 3.1 + code_chars / 2.2  (newer tokenizer; X3D numbers and markup are denser)
tps       = out_tok / (t_end − t_first_text)      (measured stream rate)
think_tok ≈ max(0, (t_first_text − t_send − 0.8 s) × tps)
usd       = (in_tok × 0.10 + (out_tok + think_tok) × 0.50) / 1e6
```

The thinking estimate rests on one fact. With effort on, Haiku thinks silently *before* its first visible token. So the wait before the first text, multiplied by the measured streaming rate, approximates the hidden thinking tokens.

- The first call in a visit includes the consent dialog in that wait. For it, the meter uses the tier's **prior** instead and says so.
- Accuracy: about ±25% on text tokens. Thinking is a correlate, not an invoice.

**Where it shows:**
- **Gate tab:** the last round trip, with every call in it (first, repair, enrich): tokens in, out and thinking, the waits, and dollars.
- **Ledger:** a cost tag on each patch, with the token split on hover.
- **World tab:** all-time spend, kept in `world/manifest.spend`; the average per round trip; a projection per 1,000 patches; and this visit's spend.
- **Slider:** the projected cost of the selected tier.

**Two honest caveats:**
1. On claude.ai the call spends the owner's **plan usage**, not dollars. The dollar figures are *API-equivalent*, for budgeting and for the off-artifact version (§12).
2. For exact numbers, run a few real prompts through the Messages API `count_tokens` endpoint. Then tune the 3.1 and 2.2 divisors and the 300-token framing constant, all three named constants at the top of the script.

### Projected cost by tier (priors; the live meter replaces them with measurements)

| Tier | Effort | Input tok | Output tok | Thinking tok | One call | Round trip* | Per 1,000 patches | Auto-grow, per alive hour (60 patches) | Input share |
|---|---|---|---|---|---|---|---|---|---|
| 1 Sketch | medium | 2,278 | 900 | 1,000 | $0.00118 | **$0.00135** | $1.35 | $0.08 | 19% |
| 2 Study | medium | 2,612 | 1,500 | 1,500 | $0.00176 | **$0.00203** | $2.03 | $0.12 | 15% |
| 3 Structure | high | 2,855 | 2,400 | 3,500 | $0.00324 | **$0.00372** | $3.72 | $0.22 | 9% |
| 4 Mechanism | high | 3,189 | 3,200 | 4,500 | $0.00417 | **$0.00542** | $5.42 | $0.33 | 8% |
| 5 Organism | high | 3,523 | 4,000 | 5,500 | $0.00510 | **$0.00663** | $6.63 | $0.40 | 7% |

\*A round trip includes the expected repair and enrich rounds: +15% per allowed round.

**What the table says:**
- **Output and thinking are 80–93% of the bill.** Effort is the cost knob, not prompt size. Trimming context saves pennies per thousand patches; dropping from high to medium effort roughly halves the cost.
- **A whole tier-5 world of 10,000 patches is about $66** API-equivalent. A tier-3 world of the same size is about $37.
- **The worst case per call is bounded** by the platform's ~5-minute call limit and by the gate's 12 KB reply cap. Thinking spikes on hard directives are the main variance. Watch the "Thinking tokens" row after the first few real presses.

## 10. Effort: what's possible

- Haiku 5.5 supports `low`, `medium` (its **default**), `high`, `xhigh` and `max`.
- The docs recommend `high` for "strict instruction following". That describes our gate, so tiers 3 to 5 use `high`.
- The artifact's `sample` bridge exposes **`low | medium | high`** only. `xhigh` and `max` need the direct API (§12).
- With effort on, Haiku thinks before answering. That thinking is billed as output, and it is why the wait before the first text grows with the tier.

## 11. Trust and safety model

- **Model output is untrusted input.** Only canonical, whitelisted X3D reaches the renderer.
  - No scripts, URLs, textures or global nodes.
  - Every light is local.
  - Animation is bounded (≥ 0.5 s cycles, ≤ 32 keys).
- **Presence and room data are untrusted**, used for display only, never for authority. Authority is `isOwner()` plus the db rules.
- **Viewers can't write.** The rules are `world/*` and `shards/*` write: owner.
- **Titles and instructions** are stripped of control and bidirectional characters and set as `textContent`, never as HTML.
- **No secrets anywhere.** The page holds no keys, because Claude is reached through the viewer's own consented session.

## 12. Ideas for what comes next

### Generation
1. **Biomes by ring.** The spiral ring index picks a deterministic palette and material family: ring 0–2 basalt and brass, 3–5 coral and glass, and so on. The world gets geography for free.
2. **Strata and eras.** Every 256 patches the world names an era, chosen by PRNG from the hash at the boundary. Each era tints its patches' plinths and is labelled in the ledger, so the skyline reads like rock layers.
3. **Viewer nudges.** Viewers put a seed word in their presence. At each Grow the owner tab tallies the words deterministically (ties broken by hash) and offers the winner as a second seed. People steer without writing.
4. **Image-in-the-loop critique (tier 6?).**
   - Snapshot the canvas around the new patch with `canvas.toBlob()`.
   - Send it with `sample({images: true})` for a one-paragraph critique.
   - Run one enrich round on what the *render* shows rather than what the XML says. It costs about +1 call, but it is the first time the generator *sees* its work.
5. **Dialogue between layers.** An augment prompt already receives the patch below. Also send the instruction chain of that whole stack, so a tower becomes one long conversation.

### Validation (more witnesses)
6. **x3d_mcp as the second judge.** It adds the XSD check, about 50 semantic rules, and fix hints that can feed the repair prompt directly.
7. **Runtime witness.** Load the candidate in a hidden X_ITE canvas before storing it. Require no console errors and a frame within budget (for example under 4 ms extra), and count drawn triangles. This catches what static analysis can't.
8. **Visual non-emptiness.** Require ≥ 0.5% pixel coverage in a 128×128 render from the slot camera. Invisible patches get rejected.
9. **Claims ledger.** Write each verdict as a Loom-style claim graded C, L or S, so world history doubles as accountability history.

### Scale (still never erasing)
10. **Index docs.** One small document per shard holding `{n, x, z, level, color, radius}` per patch. Proxies then render from about 2 KB per 48 patches without loading full shards, so a million-patch skyline loads in seconds.
11. **Merged proxies.** One IndexedFaceSet per shard means one draw call for 48 distant patches.
12. **Spatial loading.** Load full detail only for cells within N rings of the camera. Proxies cover everywhere else.
13. **Cold storage with continuity.** Near the document cap, move old shards into the artifact's asset store as JSON and keep an index document pointing at them. The hash chain is unchanged and nothing is erased; the data has moved, not been deleted.
14. **Deterministic spend guardrails.** A daily cap in API-equivalent dollars, kept in the manifest, beyond which Grow disables itself until midnight. Also a per-hour patch cap for auto mode.

### Experience
15. **Time-lapse.** A scrubber that replays the ledger from patch #0, with the camera following each patch as it lands.
16. **Verify chain.** A button that recomputes every hash in the browser and shows the first break, if there is one.
17. **Provenance card.** Click a patch to see its directive, seed, tier, every attempt and its cost, the gate's verdict, and its canonical X3D (copyable).
18. **Comment pins on patches.** The comments capability with custom anchors, so a thread lives at a cell.
19. **Snapshot export.** A PNG of the current view through the downloads capability.

### Off-artifact companion (for exact costs and higher effort)
20. **Headless grower.**
    - A small Python job on the Messages API, run from a scheduled task (hourly at most) or from Colab with your key in Colab Secrets, never in the notebook.
    - It writes patches through the same db rules, using the same gate code, run under Node.
    - It gets **exact** token usage from `usage.input_tokens` and `usage.output_tokens`.
    - It can use `xhigh` or `max` effort.
    - It can use the **Batch API** for half price.
    - It can cache the static rules block (about 1,700 tokens) at $0.01/MTok on reads.
21. **World export.** Write the whole world out as one X3D file, then glTF and USD through the x3d.lab Blender leg, and on to Unreal. The world becomes a fidelity test scene: hundreds of model-made, gate-certified X3D pieces flowing through every engine.

## 13. Open decisions for Jason

- **Default tier:** 3 (Structure, high effort, about $0.0037 a patch) or 2 (Study, medium, about $0.0020).
- **Auto-grow:** keep it as an opt-in toggle, or remove it so that every patch is a deliberate press.
- **x3d_mcp:** where should it run so the page can reach it? A claude.ai connector, or a local MCP in the desktop app.
- **Sharing:** the page is private now. Viewers need Viewer access or above to count toward "alive". Contributor isn't needed, because only the owner writes.

## Sources

- [Claude pricing: model and long-context pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Effort parameter: levels, Haiku 5.5 default and recommendations](https://platform.claude.com/docs/en/build-with-claude/effort)
- [Token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting)
- The artifact runtime contract 0.2.96 type definitions (`sample`, `room`, `db`): the bundled `artifact-capabilities` skill.
