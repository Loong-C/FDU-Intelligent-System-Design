# Generalized plane tracking baseline

Fetched `origin/main` on 2026-10-22; commit `2c3f77b59fa4fe6c1ce08b276f33224c436626c1`.
Clean worktree; isolated branch `codex/generalized-board-tracking`.

Windows 11 build 26100, project venv Python 3.12.9, OpenCV 4.12.0,
NumPy 2.2.6, Node 24.16.0. Existing 33 tests passed (6.398 s);
`python -m pip check`: no broken requirements. Includes local official hand
photograph ONNX regression; no physical camera/board or Jetson acceptance.

Compatibility constraints from executable tests: the zero-argument tracker
retains strict four-center legacy tracking; the application opts into learning
all corners on the first complete legacy frame. Unversioned HTTP state endpoints
retain schema 2 via an explicit adapter; snapshot and versioned endpoints expose
schema 3 with reliable projection semantics. Existing tests remain unmodified.
