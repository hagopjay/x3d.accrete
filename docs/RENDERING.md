# Rendering the local reference world

The browser viewport is an illustrative X3D view of the admitted store. It is not a candidate-bound renderer witness, a visibility test, a GPU benchmark or a formal Loom acceptance result. That boundary remains visible in normal and focus modes.

## What is assembled

The application reads a bounded window from `/api/world`, currently at most 512 entries. Its geometry uses the stored deterministic cell/layer translations and fitted bounds. The real world head and cell totals remain distinct from the history-preview cutoff.

The selected latest 24, 48 or 96 entries in the preview window receive an X3D `Inline`. Each loads the exact wrapped patch scene from its local `/patches/NNNNNN.x3d` resource. Its DEF/USE names, ROUTEs and TimeSensors live in that Inline execution context. Older entries receive tinted proxy boxes only, with no Inline created for them.

Each detail Inline also has a distance LOD that can display a proxy. **LOD is a presentation choice, not a claim that its TimeSensors or resources were unloaded.** The quota bounds detail contexts per assembled world. During asynchronous replacement the old and new scenes may temporarily coexist; the UI does not claim a measured peak memory or live-context bound across that transition.

World-owned plinths, grid, support markers, light, fog, navigation and camera are presentation outside the patch admission gate. They are not added archaeological/physical evidence or model-generated candidate content.

## Base URLs and loading

`scene_uri` must match the allowlisted path derived from the entry number. The UI resolves that path to a full same-origin URL before writing the Inline MFString. This avoids dependence on the default or transient base URL of a scene created from a string. The local author capability is stored in this tab's session storage and is not included in those resource URLs.

The pinned X_ITE 16.6.0 implementation of `browser.createX3DFromString()` waits for scene load-count completion and a browser frame before resolving. The application awaits that scene, then calls `replaceWorld()`. The loading caption describes resource assembly; it is not a render verdict. A stale asynchronously built scene is disposed instead of replacing a newer requested preview.

Animation-frame waits can be delayed in hidden, occluded or offscreen browser surfaces. Bring the actual WebGL window/canvas into view when diagnosing a stalled preview. The source inspector, history verifier and growth controls remain independently usable if WebGL is unavailable. No timeout is converted into a successful renderer witness.

## History and camera

Scrubbing changes only this browser's preview. It never deletes entries. When the API reports a truncated window, the timeline is clamped to the available window and the UI names that limitation. A selected addition later than the preview cutoff is explicitly marked outside the preview.

Orbit and Fly are X3D navigation modes. Overview fits the loaded geometry window, while “Frame selected addition” moves to its stored cell/layer. Routine rebuilds preserve the root viewpoint's user position, orientation, orbit centre and effective field of view when available. These are preview controls; no camera/capture record is minted by using them.

The “Selection” count is UI bookkeeping for detailed entries and proxy entries. It is not a triangle count, a GPU draw-call measurement, a frame-time estimate or a performance guarantee.
