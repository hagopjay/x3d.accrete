# Patch baseline

`Accretion-Observatory-reference.patch` adds the new reference implementation
against a baseline containing only these exact two supplied notes:

```
source-notes/ACCRETION.md
source-notes/build-2026-11-13-accretion-world.md
```

The first is the original `ACCRETION (1).md`, renamed without altering its
contents. The private `accretion-world-src.zip` mentioned in the build note was
not supplied; this is not a patch against that unavailable source tree.

To use the patch, create a clean directory with the two baseline files at those
paths, initialize a Git repository, and run:

```sh
git apply --check /path/to/Accretion-Observatory-reference.patch
git apply /path/to/Accretion-Observatory-reference.patch
```

If integrating into an existing application, first read `docs/DESIGN-REVIEW.md`
and port the contracts and tests deliberately. Do not apply this additive
reference patch blindly over unrelated paths. The ZIP already contains the
finished patched tree. Runtime databases, author capabilities, virtual
environments and Python caches are excluded.

Patch verification uses an independent reconstruction of this baseline,
`git apply --check`, an actual apply, and byte hashes of every distributed file.
The patch is delivered alongside the ZIP rather than embedding itself.
