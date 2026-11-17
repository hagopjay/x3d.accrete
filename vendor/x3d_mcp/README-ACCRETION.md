# Pinned direct-validation subset

Upstream: https://github.com/hagopjay/x3d_mcp  
Commit: `b5c9956917714747fe1d034c729612e99b0f09c9`

The 19 files listed in `ORIGIN.json` are byte-for-byte copies from that commit, including the repository's licence. The subset supports the application adapter's direct calls to `validation.validate.validate_xml(xml, version="4.0")` and `validation.semantic.semantic_diagnostics(xml)`. It is not the full MCP server, does not expose a connector, and does not ship unrelated server tools.

Runtime dependencies for these calls are `lxml>=6,<7` and `jsonschema>=4.26,<5`. The upstream XML module imports jsonschema even when only XML validation is requested. Numpy is not needed for the application's small primitive fragments; the upstream optional oversize/splat branches are not exposed by the adapter's 128 KiB per-candidate cap and fragment policy.

The bundled 4.0 XSD and its local includes/signature schema are used for XSD validation. The upstream semantic checks consult their default 4.1 UOM/profile vocabulary. That mixed version scope is recorded in every result rather than relabelled as pure 4.0 semantic certification.

The adapter preserves warning and informational diagnostics, and semantic pass means only that no error-level diagnostic was emitted. It measures neither visibility nor performance and cannot mint a Loom acceptance record. The adapter verifies every vendored file against `ORIGIN.json` before invocation and refuses source drift. Hashes identify local bytes; they do not by themselves authenticate a publisher or establish independent provenance.
