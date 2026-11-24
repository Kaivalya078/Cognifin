# LICENSE and ruff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** MIT license + a clean `ruff check` on the backend. **Spec:** `docs/superpowers/specs/2026-11-24-license-ruff-design.md`

## Global Constraints
- Rules exactly `E4, E7, E9, F, B, I`; `ruff==0.17.6`. Suite (`venv/Scripts/python.exe -m pytest tests/test_*.py -q`) stays at 351 passed after every step.

## Review Focus
1. An "unused" import that is a side-effect/re-export (`__init__.py`, fixtures imported by tests) must not be deleted — run the suite after `--fix`.
2. `B023` loop-variable closures: decide per site whether it is a real bug; real ones get a test.
3. `F811` redefinitions: the surviving definition must be the one callers use.

### Task 1: LICENSE, config, fixes
- [ ] Add `LICENSE`, `backend/pyproject.toml`, pin in `requirements.txt`.
- [ ] `ruff check . --fix` (safe only); run suite → 351 passed.
- [ ] Fix remaining findings by hand; suite after each batch.
- [ ] `ruff check .` → "All checks passed!"; commit `chore: MIT license and ruff lint (E4,E7,E9,F,B,I)`.
