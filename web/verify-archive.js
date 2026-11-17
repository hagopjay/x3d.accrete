/* Accretion archive verifier, browser/Node port of accretion.world.verify_archive.
 *
 * Re-computes, with the Web Crypto SHA-256 and a port of accretion-c14n/1:
 *   genesis, sequence and prev-hash links, entry payload digests, deterministic
 *   placement replay (spiral + augment planner), candidate byte digests, the
 *   exact wrap_scene identity, witness summary, policy digest, pipeline identity
 *   digest and the declared checkpoint.
 * It does NOT re-run the fragment gate, the pinned XSD or the semantic validator
 * (those need the Python/lxml instruments), and it cannot pin POLICY to the source
 * of a particular Python release: it only checks that the recorded policy is
 * self-consistent and identical on every entry. Scope text is returned with the verdict.
 *
 * Parity with the Python verifier is tested in tests/test_static_export.py.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.AccretionVerify = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const subtle = (globalThis.crypto && globalThis.crypto.subtle) || null;
  const WORDS = ['orrery', 'mycelium', 'ziggurat', 'tide', 'beacon', 'lattice', 'coral', 'helix', 'turbine', 'lotus', 'astrolabe', 'reef',
    'spindle', 'crystal', 'canopy', 'resonance', 'cairn', 'gyroscope', 'seed', 'aurora', 'vessel', 'ripple', 'spire', 'orbit'];
  const BIOMES = [['basalt-brass', [0.81, 0.57, 0.24]], ['coral-glass', [0.21, 0.77, 0.70]], ['verdant', [0.23, 0.57, 0.71]], ['noctilucent', [0.62, 0.39, 0.79]]];

  async function sha256Hex(text) {
    if (!subtle) throw new Error('Web Crypto (secure context) is required to verify the archive in this browser.');
    const bytes = typeof text === 'string' ? new TextEncoder().encode(text) : text;
    const digest = await subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
  }

  // Python repr(float) for a finite non-integral double.
  function pyFloat(x) {
    const [mant, exp] = x.toExponential().split('e');
    const e = parseInt(exp, 10);
    if (e < -4 || e >= 16) {
      const sign = e < 0 ? '-' : '+';
      return mant + 'e' + sign + String(Math.abs(e)).padStart(2, '0');
    }
    return String(x);
  }
  function codePointCompare(a, b) {
    const x = Array.from(a), y = Array.from(b);
    for (let i = 0; i < Math.min(x.length, y.length); i++) {
      const d = x[i].codePointAt(0) - y[i].codePointAt(0);
      if (d) return d;
    }
    return x.length - y.length;
  }
  function c14n(value) {
    if (value === null) return 'null';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') {
      if (!Number.isFinite(value)) throw new Error('Nonfinite JSON number');
      return Number.isInteger(value) ? String(value) : pyFloat(value);
    }
    if (typeof value === 'string') return JSON.stringify(value);
    if (Array.isArray(value)) return '[' + value.map(c14n).join(',') + ']';
    if (typeof value === 'object') {
      return '{' + Object.keys(value).sort(codePointCompare).map(k => JSON.stringify(k) + ':' + c14n(value[k])).join(',') + '}';
    }
    throw new Error('Unsupported JSON value');
  }
  const sha = value => sha256Hex(typeof value === 'string' ? value : c14n(value));

  function spiral(index) {
    if (index === 0) return [0, 0];
    const ring = Math.ceil((Math.sqrt(index + 1) - 1) / 2);
    const side = 2 * ring, top = (2 * ring + 1) ** 2 - 1;
    if (index >= top - side) return [ring - (top - index), -ring];
    if (index >= top - 2 * side) return [-ring, -ring + (top - side - index)];
    if (index >= top - 3 * side) return [-ring + (top - 2 * side - index), ring];
    return [ring, ring - (top - 3 * side - index)];
  }
  async function planNext(placements, previousHash, forceMode) {
    if (![null, undefined, 'auto', 'generate', 'augment'].includes(forceMode)) throw new Error('Unknown growth mode');
    const n = placements.length + 1;
    const seed = await sha(previousHash + ':' + n);
    const tops = new Map(), key = c => c[0] + ',' + c[1];
    for (const row of placements) tops.set(key(row.cell), Math.max(tops.has(key(row.cell)) ? tops.get(key(row.cell)) : -1, row.level));
    const recent = [];
    for (const row of placements.slice(-32).reverse()) {
      if (tops.get(key(row.cell)) < 5 && !recent.some(c => key(c) === key(row.cell))) recent.push(row.cell);
    }
    let augment = recent.length > 0 && parseInt(seed.slice(0, 8), 16) % 100 < 42;
    if (forceMode === 'generate' || forceMode === 'augment') augment = forceMode === 'augment';
    if (augment && !recent.length) throw new Error('No cell can be augmented yet; generate a new cell first');
    let cell, level;
    if (augment) {
      cell = recent[parseInt(seed.slice(8, 16), 16) % recent.length].slice();
      level = tops.get(key(cell)) + 1;
    } else {
      cell = spiral(placements.filter(r => r.mode === 'generate').length);
      level = 0;
    }
    const ring = Math.max(Math.abs(cell[0]), Math.abs(cell[1]));
    const [biome, color] = BIOMES[Math.floor(ring / 2) % BIOMES.length];
    return {
      n, mode: augment ? 'augment' : 'generate', requested_mode: forceMode || 'auto', cell, level, seed,
      seed_word: WORDS[parseInt(seed.slice(16, 24), 16) % WORDS.length], biome, era: Math.floor((n - 1) / 32), color,
      translation: [cell[0] * 8, level * 6.6, cell[1] * 8],
    };
  }
  function witnessRows(a) {
    const instrument = (a.mcp && a.mcp.instrument) || {};
    const brief = {};
    for (const k of ['repository', 'commit', 'code_sha256']) if (k in instrument) brief[k] = instrument[k];
    return [
      { id: 'fragment', status: a.fragment.status, instrument: a.fragment.instrument || {}, scope: 'Restricted local fragment checks and conservative containment.' },
      { id: 'xsd', status: a.mcp.xsd.status, instrument: brief, scope: 'Pinned upstream XSD 4.0 on exact wrapped scene bytes.' },
      { id: 'semantic', status: a.mcp.semantic.status, instrument: brief, scope: 'Pinned upstream semantics using its default 4.1 UOM tables.' },
      { id: 'render', status: a.render.status, required: false, scope: a.render.scope },
    ];
  }
  const wrapScene = f => '<?xml version="1.0" encoding="UTF-8"?>\n<X3D profile="Immersive" version="4.0"><Scene>' + f + '</Scene></X3D>\n';
  const same = (a, b) => c14n(a) === c14n(b);
  const isInt = v => Number.isInteger(v);

  async function verifyArchive(archive, checkpoint) {
    const errors = [];
    if (!archive || archive.schema !== 'accretion.archive/1' || archive.hash_profile !== 'accretion-c14n/1') throw new Error('Not a supported Accretion archive');
    let previous = await sha('accretion-observatory-v1:genesis:accretion-c14n/1');
    if (archive.genesis !== previous) errors.push({ code: 'GENESIS_MISMATCH' });
    if (archive.world_id !== 'accretion-observatory-v1') errors.push({ code: 'WORLD_ID_MISMATCH' });
    if (!Array.isArray(archive.entries)) throw new Error('Archive entries must be an array');
    const entries = archive.entries, placements = [];
    let firstPolicy = null;
    for (let index = 1; index <= entries.length; index++) {
      const item = entries[index - 1];
      try {
        const body = item.payload;
        if (item.created_utc !== body.created_utc) throw new Error('entry timestamp binding mismatch');
        if (!isInt(item.n) || !isInt(body.n) || item.n !== index || body.n !== index || item.prev_hash !== previous || body.prev_hash !== previous) throw new Error('sequence or previous hash mismatch');
        if (await sha(body) !== item.hash) throw new Error('entry payload digest mismatch');
        const p = body.plan;
        if (!same(await planNext(placements, previous, p.requested_mode), p)) throw new Error('deterministic placement replay mismatch');
        const c = body.candidate;
        for (const [k, f] of [['raw_sha256', 'raw_x3d'], ['canonical_sha256', 'canonical_x3d'], ['scene_sha256', 'scene_x3d']]) {
          if (c[k] !== await sha256Hex(item[f])) throw new Error('candidate bytes mismatch');
        }
        if (item.scene_x3d !== wrapScene(item.canonical_x3d)) throw new Error('stored scene is not the exact wrapped fragment');
        const a = body.admission;
        if (!same(body.witnesses, witnessRows(a))) throw new Error('displayed witness summary mismatch');
        for (const k of ['bounds', 'fit', 'metrics']) if (!same(body[k], a.fragment[k])) throw new Error('displayed fragment measurements mismatch');
        if (a.policy_sha256 !== await sha(a.policy)) throw new Error('admission policy mismatch');
        if (firstPolicy === null) firstPolicy = a.policy_sha256;
        else if (a.policy_sha256 !== firstPolicy) throw new Error('admission policy differs between entries');
        const g = a.fragment, m = a.mcp;
        if (g.status !== 'pass' || g.raw_sha256 !== c.raw_sha256 || g.canonical_sha256 !== c.canonical_sha256) throw new Error('fragment witness binding mismatch');
        if (m.status !== 'pass' || m.candidate_sha256 !== c.scene_sha256 || m.xsd.status !== 'pass' || m.semantic.status !== 'pass') throw new Error('pinned validator witness binding mismatch');
        if (body.pipeline.code_sha256 !== await sha(body.pipeline.files)) throw new Error('pipeline identity digest mismatch');
        placements.push(p);
        previous = item.hash;
      } catch (error) {
        errors.push({ n: index, code: 'ENTRY_MISMATCH', message: String(error.message || error) });
        break;
      }
    }
    const claimed = archive.checkpoint || {};
    const last = entries.length ? (entries[entries.length - 1] || {}).hash : archive.genesis;
    if (typeof claimed !== 'object' || !isInt(claimed.head) || claimed.head !== entries.length || claimed.hash !== last) errors.push({ code: 'CHECKPOINT_HEADER_MISMATCH' });
    if (checkpoint) {
      const n = checkpoint.head, rec = isInt(n) && n > 0 && n <= entries.length ? entries[n - 1] : null;
      const observed = rec ? rec.hash : (n === 0 ? archive.genesis : null);
      if (!isInt(n) || n < 0 || n > entries.length || observed !== checkpoint.hash) errors.push({ code: 'TRUSTED_CHECKPOINT_MISMATCH' });
    }
    return {
      valid: errors.length === 0, head: entries.length, checked: placements.length, tail_hash: previous, errors, engine: 'browser-js',
      scope: 'Browser re-computation of: hash chain, placement replay, candidate byte digests, witness/policy/pipeline bindings. Not re-run here: the fragment gate and the pinned XSD/semantic validators (Python + lxml), signatures, authorship, or any render.',
    };
  }
  return { verifyArchive, c14n, sha, planNext, spiral, pyFloat };
});
