# Generalized plane development validation — 2026-10-22

## Environment and scope

Windows 11 10.0.26100 AMD64; project `.venv` Python 3.12.9,
OpenCV 4.12.0 (opencv-python 4.12.0.88), NumPy 2.2.6; Node 24.16.0.
No runtime dependency added or upgraded. Baseline main was fetched at
`2c3f77b59fa4fe6c1ce08b276f33224c436626c1`. Original 33 tests passed before edits.
All original test files/fixtures/assertions are unchanged in the branch diff.

**Physical camera, rigid board performance, subjective acoustic evaluation and
Jetson Xavier NX: NOT TESTED.** The existing read-only Jetson preflight ran on
this Windows PC and correctly reports hardware_acceptance NOT TESTED; it is not
a Jetson deployment test. No OS/Python/OpenCV replacement or device installation.

## Automated verification

`python -m unittest discover -s tests -v`: **57 tests passed** in 19.554 s (33 original + 24 new).
`python -m pip check`: **No broken requirements found**.
`node --check web/app.js`, `node --check web/calibration.js`: **PASS**.
`node tests/frontend_coordinates.cjs`: **PASS** (mirror, scale, horizontal and
vertical letterboxing all recover the identical original camera point).
`git diff --check`: **PASS**.

New coverage includes:

- Board schema round trips for 1–12 IDs; no UV clipping; duplicate keys, invalid
  dictionary/IDs, overlaps, nonfinite points, unsafe names and degenerate shapes.
- Real generated six-marker raster images with rotated/arbitrary layouts, marker
  outside the reference square, three perspective poses and a hand point moving
  rigidly with the board. Known UV points recover within **.004 UV per coordinate**.
- Real 12-marker detection yielding 48 correspondences. Two dispersed markers
  remain valid; small single marker is degraded. Narrow coverage is rejected
  regardless of marker count. None → held → lost → valid is tested.
- Duplicate IDs, ignored unknown IDs, nonfinite corners, displaced wrong matches,
  extreme projective horizon, sudden transform jumps and stable reacquisition.
  Five of six consistent markers can reject the sixth outlier; two bad markers
  fall below the configured inlier ratio. Bad legacy corner geometry fails safely.
- v3 held/degraded projection semantics, v2 adapter compatibility, and action
  resets/rearming for all unreliable states. Original four chords, up/down,
  velocity, cooldown, event deduplication, mirrors and anatomical roles still pass.
- Frozen frame independence from later image mutation, save/load mapping equality,
  session replacement/expiry, preview-token save, contrast failures, atomic filename
  conflict, same-origin access and live activation.
- Concave/outside-unit regions, shared backend overlay/hit geometry, directed
  vertical strum normal and mirrored direction compatibility.
- Lossless PNG alignment/checksums, relative replay clock, raw-buffer copying,
  mock default, actual optional ONNX rerun, recording beginning mid-held,
  encoding failure, deterministic queue overflow and restart after recorder failure.

## Reproducible software runs

`tools/generate_synthetic_experiment.py --frames 210` generated raw PNGs and
scripted hand data with moving plane, six/four/two/one/zero visible markers.
`tools/replay_experiment.py` recomputed detection, fusion and logic from those
PNGs. Original and replay had **210/210 identical pose states and hand UV arrays**:
150 valid, 30 degraded, 30 lost. Both generated 8 events; mock audio consumed all
8 once, with zero dropped events/frames. This sequence has no held frames because
the last valid pose had already expired during the single-marker phase; short
held/recovery is separately covered by automated tests.

Synthetic reprojection RMSE: median .311 px, p95 .355 px. These raster results
are not real-camera accuracy measurements. UV displacement analysis explicitly
includes intentional hand motion and must not be advertised as sensor jitter.

`tools/verify_runtime.py --seconds 13 --mode synthetic --audio mock`: 385 frames,
385 valid board frames, 385 dual-hand frames, 21 unique events covering C/G/Am/F
and both directions. All 385 packets recorded; no recorder error, no dropped or
duplicate mock events. Its paced ~29.6 FPS is a scripted software run, not camera
throughput, acoustic latency or Jetson FPS. Real ONNX checks continue to use the
pre-existing official hand photograph; no personal imagery is committed.

## Tracking overhead

`tools/benchmark_tracking.py --iterations 300` warms each tracker for 20 frames,
then compares detection plus geometry with four OpenCV CPU threads. The legacy
algorithm remains in `LegacyArucoBoardTracker`, preserving the baseline path.
Raw measurements and environment are in [tracking_benchmark.json](tracking_benchmark.json).

| Synthetic case | p50 ms | p95 ms |
|---|---:|---:|
| Old four marker centers, 640×480 | 1.525 | 1.994 |
| Joint four marker corners, same image | 1.748 | 2.289 |
| Joint six markers, 960×720 | 2.540 | 3.211 |

Same-input median overhead: **+.224 ms (~14.7%)**. The six-marker row has a larger
image and is not an isolated marker-count comparison. Timings are PC software
microbenchmarks subject to load, not end-to-end performance guarantees.
inference_ms / aruco_ms / vision_total_ms retain their existing stage boundaries.

## Browser QA

Browser plugin not available; used cached Playwright CLI and installed Microsoft
Edge without installing dependencies. Local URL `http://127.0.0.1:8766/`;
desktop 1280×720 / 1280×900 and mobile 390×844. Screenshots are kept outside the repository
in the Codex visualization workspace; they contain generated markers only.

Flow: dashboard → board calibration → capture → four mirrored image points →
preview → undo (save becomes disabled) → replace point → preview → save and
activate → new capture → cancel. The backend activated the saved synthetic board;
the temporary UI-test configuration was removed after the check. Cancel was
verified after awaiting the asynchronous response. No horizontal mobile overflow.

| Check | Result |
|---|---|
| URL/title and meaningful app content | PASS |
| Blank page / framework error overlay | None |
| Console errors and warnings | 0 / 0 during exercised flow |
| Same frozen frame during point selection | PASS |
| Backend-rendered preview / desktop + mobile screenshots | PASS |
| Undo, save, activation, capture and cancel | PASS |
| Local shutdown control | PASS |

Final-page check also verified `--record-video` checks the UI preference, then
started and stopped a short raw experiment through the browser. The persisted
manifest reported complete with aligned PNG/data counts and no errors or drops.

## Remaining physical acceptance

Use actual printed markers and a single RGB camera to evaluate blur, glare,
print quality, lens distortion, oblique views, multiple user motion speeds,
coordinate drift, planar rigidity, audio output latency and listening quality.
Tune heuristics on recorded experimental sequences rather than treating them as
probabilities. The initial four-point choice sets a projective coordinate frame;
it cannot prove the object is planar or measure physical contact. Very fast true
board motion may conservatively pause while the new pose stabilizes.

Jetson must be inventoried with `tools/jetson_preflight.py` on the actual device;
use an ARM64-compatible environment per the existing [deployment notes](../integration/JETSON.md).
Windows wheels, synthetic rates and PC timing results are not Jetson acceptance.
