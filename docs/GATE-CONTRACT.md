# Fragment admission contract

`accretion.fragment-gate` **2.0.0** is a new Python standard-library reference implementation of the attached design's bounded-fragment policy. The original JavaScript source archive was not supplied. This module does not reproduce its claimed 38-test result or claim full X3D coverage.

```python
from accretion.gate import gate_fragment
result = gate_fragment(fragment_xml, prefix="P17")
```

Only a `status == "pass"` result has `canonical_x3d`. The admitted, fitted fragment—not the original model/user text—is the renderable output. A failed candidate returns named `GATE_*` diagnostics and no renderable canonical output.

## Vocabulary and containment

The admitted subset comprises `Group`, `Transform`, `Shape`, `Appearance`, `Material`, `PhysicalMaterial`, `Box`, `Sphere`, `Cylinder`, `Cone`, `Coordinate`, `Color`, `IndexedFaceSet`, `IndexedLineSet`, `ElevationGrid`, `Extrusion`, `TimeSensor`, `PositionInterpolator`, `OrientationInterpolator`, `ColorInterpolator`, `ScalarInterpolator`, `DirectionalLight`, `PointLight`, `SpotLight`, plus `ROUTE` statements. This is **24 node types plus ROUTE**, not the original design's 31-node claim.

Every admitted field is explicitly listed in `FIELDS` in `gate.py`; other fields fail. Child containment is explicit. A Shape has exactly one supported geometry and at most one Appearance; indexed geometry has one Coordinate and at most one Color. There are no scripts, shaders, URLs, textures, Inline/Anchor nodes, Text/fonts, PROTOs, global camera/environment/navigation nodes or user LODs. The world owns those capabilities.

A bare fragment, a bare Scene, or an X3D 4.0 wrapper containing exactly one Scene is accepted. An XML declaration may precede it. Wrapper head/global data, nonwhitespace text, comments, processing instructions, DTD/entity declarations, CDATA and nonstandard entity references are refused. Only the five standard named XML entities are recognized by the XML preflight; their decoded field values still undergo the normal typed checks.

## Local references and event graph

- DEFs are unique bounded local identifiers. USE must name an earlier DEF of the same type and carry no field overrides or children. Self-containing USE graphs fail.
- Caller-provided prefixes namespace every DEF, USE and ROUTE endpoint. Different prefixes deliberately produce different canonical candidate hashes. Empty prefix is available for inspection tools. Replay the same **raw input and prefix** to reproduce admission; this is not a semantic XML-equivalence or W3C C14N algorithm.
- ROUTEs are fragment-level statements and require previously defined endpoints. The allowed graph is TimeSensor `fraction_changed` → interpolator `set_fraction`, then interpolator `value_changed` → supported Transform fields, material colors or local-light intensity/color. Arbitrary event chains, feedback loops and field types outside this pattern fail.
- Position, orientation, color and scalar interpolation cardinalities must match their strictly increasing keys. Light intensity/color animation retains field ranges. Geometry dimensions are not routable in this subset.

## Caps and arithmetic

| Bound | Value |
| --- | --- |
| Raw UTF-8 source | 12 KiB |
| Canonical fitted/namespaced output | 24 KiB, allowing owned wrapper/prefix/numeric-normalization overhead |
| Source nodes | 80, including USE and ROUTE statements |
| Owned fit wrapper | One additional Transform, reported separately |
| Nesting depth | 16 |
| Expanded geometry instances | 160, preventing compact USE-DAG amplification |
| TimeSensor definitions | 2 |
| Local lights | 1 definition and 1 expanded instance, forced `global="false"`; USE cannot amplify the cap |
| ROUTEs / interpolators | 12 / 8 |
| Keys per interpolator | 2–32 |
| TimeSensor cycle interval | 0.5–3600 seconds |
| Coordinate points / indices | 1024 / 4096 per admitted array |
| ElevationGrid dimensions | 2–64 each, with exact `xDimension × zDimension` height count |

Numeric fields are finite, lexical/type checked and range checked. Primitive dimensions are positive. Static Transform scale components are nonzero. A nonzero axis-angle rotation needs a nonzero axis; axes are normalized. Indexed faces/lines require in-range points and at least three/two indices per segment. Implicit Color indexing must have sufficient records. Extrusion scale and orientation contain one record or one per spine point.

These source caps bound a limited workload. They do **not** constitute a GPU-time measurement, proof of visible area, topology/watertightness check or photosensitivity/strobing guarantee. A minimum cycle interval alone cannot establish the latter when many keys or abrupt visual changes are possible.

## Conservative fitting

`raw_bounds` and `bounds` report **origin-centred sphere envelopes enclosed by axis-aligned cubes**. They are conservative, often loose bounds, not tight geometry AABBs.

For a Transform with child radius `r`, translation norm bound `t`, centre norm bound `c`, and maximum absolute scale component `s`, the envelope radius is bounded by:

```text
t + c + s × (r + c)
```

All declared animation samples for translation, scale and centre contribute to those maxima. Linear interpolation stays within the relevant convex envelopes. Rotation and scale-orientation changes preserve the sphere-bound argument, including rotation of offset child geometry. Custom mesh points, grid extent and Extrusion spine/cross-section/scale contribute conservative radii. Reused geometry uses the same local envelope at each instance.

An envelope above 120 metres is refused. Otherwise a world-owned uniform wrapper fits it within 3 metres, with a tiny numerical margin. The wrapper is included in `canonical_x3d` and `canonical_sha256`; stored `bounds` refer to that actual fitted output. `fit.scale` and `raw_bounds` retain the transformation needed to explain the change.

## Identity and scope

The result contains the original UTF-8 digest, canonical-output digest, metrics and instrument identity. The instrument uses the source digest captured at module import and refuses verdicts after its source file changes until restart. Hashes identify bytes; they do not authenticate a producer or grant Loom acceptance authority.

The deterministic `complexity` rubric counts structural quantity, type variety, reuse, animation and custom geometry. It is neither beauty nor scene readability nor measured rendering cost. `custom_triangle_estimate` is a source triangulation estimate for IFS/grid geometry; it is not the renderer's total drawn-triangle count, especially for primitives and USE expansion.

Independent pinned `x3d_mcp` XSD/semantic checks remain separate instruments. A visible browser preview remains separate from a candidate-bound runtime/render witness. Only the actual named Loom profile may decide which instruments authorize its own acceptance step.

## Checks

`python3 -m unittest discover -s tests -p test_gate.py` exercises finite/typed fields, wrapper/text injection, forbidden capabilities, containment, DEF/USE order/type/cycles, typed/local routes, animation ranges, timer/light/key caps, source/expansion caps, mesh/grid/Extrusion cardinalities, fitting, rotating offset geometry, instrument drift, and all six authored generator families at five tiers. See the release validation record for the fresh executed count.


## Known mismatch (review 17 Nov 2026, F1)
`PhysicalMaterial` is in the vocabulary above, but the pinned upstream semantic pass reports `profile-component` for it under the Immersive wrapper, so no fragment using it can currently be admitted. Sub-single-precision magnitudes (below 1.1754944e-38) are refused for sizes and scales since the same review (G1).
