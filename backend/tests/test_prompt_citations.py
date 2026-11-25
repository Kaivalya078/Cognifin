import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generation.intent_prompts import _INTENT_PROMPTS, build_intent_prompt  # noqa: E402
from generation.prompt_builder import CITE_REMINDER, build_prompt  # noqa: E402


def test_generic_prompt_reminder_and_format():
    system, user = build_prompt("[chunk_1]: x", "Q?")
    assert user.startswith("Q?")
    assert user.endswith(CITE_REMINDER)
    assert "[chunk_12]" in system


@pytest.mark.parametrize("intent", sorted(set(_INTENT_PROMPTS) | {"compare", "trend", "unknown-intent"}))
def test_intent_prompt_reminder(intent):
    system, user = build_intent_prompt("[chunk_1]: x", "Q?", intent)
    assert user.startswith("Q?")
    assert user.endswith(CITE_REMINDER)
    assert "[chunk_12]" in system
