# Phase 5.1 — LICENSE and ruff

Date: 2026-11-24 · Branch: `phase-5-lint` · Size: small change

**Intent:** the public repo has no license and Python has no linting. Phase 5 makes the
engineering visible at zero running cost; this is its first piece (then CI, bigger eval,
`/engineering` page).

**Approaches:** ruff's defaults in 0.17 (572 findings, 211 of them `UP006` annotation churn)
vs the classic core set (84) vs core + bugbear + import sorting. **Picked: core + `B` + `I`**
(my call, approved): catches real bugs, skips pure-style churn.

**Design**
- `LICENSE`: MIT, "Copyright (c) 2026 Kaivalya Patel" (approved).
- `backend/pyproject.toml` `[tool.ruff]`: `select = ["E4","E7","E9","F","B","I"]`;
  `flake8-bugbear.extend-immutable-calls` for FastAPI `Depends/File/Form/Query`;
  `per-file-ignores` `tests/*` → `E402` (they edit `sys.path` before importing); exclude `venv`.
- `ruff==0.17.6` pinned in `requirements.txt`.
- Safe auto-fixes first; the rest by hand, each read; a real bug gets a test first.
- Done when `ruff check .` is clean and the 351 tests pass. ESLint's 2 leftovers move to the CI piece.
