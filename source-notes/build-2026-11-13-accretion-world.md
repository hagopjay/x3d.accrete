# Accretion World: a Haiku-grown, append-only X3D world (13 Nov 2026)

**Artifact:** https://claude.ai/artifact/MHgC3NGwRwppwXZcnxpR56 (private to Jason until shared)
**Source:** `accretion-world-src.zip`, sent in chat: gate, page, build, 38 gate tests, e2e harness with a mocked runtime.
**Full design, cost model and roadmap:** `design-2026-11-13-accretion-world.md`.

## Version 2 (13 Nov, 06:40 ET): complexity slider + token/cost meter
- **Complexity slider, 1–5:** Sketch, Study, Structure (default), Mechanism, Organism.
  - The tier sets effort (medium for 1–2, high for 3–5), prompt depth (6–20 recent patches, 2–6 KB augment excerpt, neighbours from tier 3), a node target, an ambition brief, and 1–2 repair/enrich rounds.
  - A deterministic complexity score (0–5) is measured on each accepted patch.
  - At tiers 4–5, a patch that passes the gate but scores below the tier's floor gets an "enrich" round. The best passing version is kept.
- **Effort:** `sample` is called with `effort` from the tier. The bridge exposes low/medium/high; Haiku 5.5 defaults to medium.
- **Cost meter per round trip:** estimated input, output and thinking tokens. Thinking is estimated as the wait before the first text × the measured stream rate.
  - Dollars at Haiku 5.5 list prices: $0.10 in / $0.50 out per MTok for prompts ≤ 100K tokens.
  - Stored as `cost` on each patch (outside the hash), as `world/manifest.spend` (all time), and on rejects.
  - Projected per patch: about $0.0014 (tier 1) to $0.0066 (tier 5). Output plus thinking is 80–93% of the cost.
- **e2e:** owner flow, hash chain OK, a repair round counted as 2 calls, reject cost logged; tier-5 run exercises enrich and repair → enrich.

## What it does (version 1)
- **Alive** means 2 or more distinct signed-in people have the page open, counted by user id rather than by tab; this uses the room capability's presence.
- **Owner only:** Jason presses **Grow**, and Haiku 5.5 (`claude-haiku-5-5`, no cache) writes one patch. The call is billed to the owner's Claude usage.
  - An **opt-in auto mode** grows once every 60 s while the world is alive.
  - A "solo" toggle allows testing alone.
  - Owner-only is enforced by db rules: `world` and `shards` are read at view level and written by the owner only. Verified: a Contributor's write is refused.
- **Pipeline:** Haiku's JSON (`title`, `instruction`, `x3d`) goes through the gate. Failures feed errors back for repair; if the patch still fails, it is logged to `world/rejects` and never stored.
  - The `x3d_mcp` stage slot is there but off. It needs the x3d_mcp validator reachable as a claude.ai connector or as a local MCP in the Claude app; then set server/tool and declare the `mcp` capability.
- **Never erased:** patches are appended to shard docs (`shards/s000000`…, at most 48 patches or 200 KB each), and `world/manifest` caches the head.
  - Each patch is SHA-256 chained: prev, slot, text, gate version, fit and canonical X3D.
  - About 1.2M patches fit under the 25k-document cap.

## Deterministic guardrails (in JS)
- **Placement:** generated patches take the next cell of an outward Ulam square spiral (8 m cells). Augments stack a layer on a recently touched cell, at most 6 layers.
  - Mode, target and seed word come from a PRNG seeded by prevHash and head, so Haiku never picks a position.
- **Gate (x3dgate/1.0.0):** whitelists 31 nodes plus ROUTE, with types and ranges per field.
  - Blocks Text (needs fonts the host CSP blocks), textures/URLs, Script, Viewpoint, Background/Fog/NavigationInfo, PROTOs and LOD.
  - Semantics: IFS/ILS index ranges, ElevationGrid `height` = x×z (the add-on crash case), interpolator key/value counts, typed ROUTEs.
  - Caps: 80 nodes, 1 light (forced `global='false'`), cycleInterval ≥ 0.5 s, 12 KB.
  - Bounds: conservative AABB through Transforms and animated fields; anything over 3 m is auto-fitted down, and anything over 120 m is rejected.
- **Render:** X_ITE 16.7.1. Each patch is isolated in an `Inline` loaded from a `data:` URL, so its DEFs and ROUTEs stay local and its animations run.
  - The newest 240 patches render at full detail behind an LOD (90 m); older ones render as tinted proxy boxes.
  - Views auto-load up to 2,400 patches, then offer a "Load older" button.

## Open
- First live run needs two people on the page (or the solo toggle) and the owner's consent dialog for Claude. The live world holds 3 patches from before the meter existed; spend starts recording at the next Grow.
- Calibrate the token estimator once against the API's `count_tokens` (constants at the top of the script).
- Next steps are in the design doc §12: biomes by ring, eras, viewer nudges, image-in-the-loop critique, x3d_mcp stage, index docs for proxies, headless grower with exact usage and Batch pricing.
