# Third-party notices and source provenance

## x3d_mcp

Repository: https://github.com/hagopjay/x3d_mcp

Pinned commit: `b5c9956917714747fe1d034c729612e99b0f09c9`.

The required validation Python modules and X3D specification assets are copied
without modification into `vendor/x3d_mcp/`. `ORIGIN.json` lists every upstream
path and SHA-256. The adapter verifies those bytes before validation. The
original Web3D license is retained as `vendor/x3d_mcp/LICENSE`. Read it for
redistribution terms. This edition calls the upstream validation functions
directly; it does not expose or claim a running MCP transport service.

## X_ITE

Repository: https://github.com/create3000/x_ite

Bundled distribution: **16.6.0**, in `web/vendor/x_ite/`. The distribution and
its required assets were reused from the existing local JEV Loom project.
The retained `LICENSE.md` contains the MIT license and component notices.
The supplied Accretion draft mentions 16.7.1; that is not the version used here.

## x3d.loom

Repository: https://github.com/hagopjay/x3d.loom

Inspected documentation revision:
`7a7d65709c16633afecc5b5e482d28202707db13`.

Conceptual alignment only: candidate-bound evidence, instrument identity,
explicit policy, replayable decisions, and no promotion of an incomplete
render check into acceptance. This project does not implement the formal
Loom receipt schema or claim conformance to its entire protocol.

## Python dependencies

`requirements.txt` pins lxml 6.1.1 and jsonschema 4.26.0. Their distributions and
transitive dependencies are installed from the Python package registry, not
vendored in this archive. Consult those distributions for their licenses.

## User source material

`source-notes/ACCRETION.md` and
`source-notes/build-2026-11-13-accretion-world.md` are the supplied attachments,
preserved unchanged. Their statements about a private Claude artifact are
historical design context, not evidence that its unavailable source was run.
