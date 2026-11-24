"""SSE framing, follow-up hold-back and the LLM delta stream."""

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from generation.streaming import sse, hold_follow_ups
from generation.openai_client import OpenAIClient


def test_sse_frame():
    assert sse("token", {"text": "hi ₹"}) == 'event: token\ndata: {"text": "hi ₹"}\n\n'


def test_hold_follow_ups_drops_follow_up_lines():
    out = "".join(hold_follow_ups(["Revenue rose.\n", "[FOLLOW_UP]: Why?\n", "[FOLLOW_UP]: And?"]))
    assert "FOLLOW_UP" not in out and out.startswith("Revenue rose.")


def test_hold_follow_ups_split_across_deltas():
    out = "".join(hold_follow_ups(["A\n[FOL", "LOW_UP]: x", "\n[FOLLOW", "_UP]: y"]))
    assert "FOLLOW" not in out and "x" not in out and "y" not in out and out.startswith("A")


def test_hold_follow_ups_releases_other_brackets():
    out = "".join(hold_follow_ups(["[fin", "_1] revenue 10\n", "[F", "Y26] ok"]))
    assert out == "[fin_1] revenue 10\n[FY26] ok"


def test_hold_follow_ups_streams_plain_text_unbuffered():
    assert list(hold_follow_ups(["ab", "cd"])) == ["ab", "cd"]


def _client(create):
    c = OpenAIClient.__new__(OpenAIClient)
    c.is_configured, c.model = True, "test"
    c.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return c


def _chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def test_generate_stream_yields_deltas():
    c = _client(lambda **kw: iter([_chunk("a"), _chunk(None), _chunk("b")]))
    assert list(c.generate_stream("s", "u")) == ["a", "b"]


def test_generate_stream_maps_errors():
    resp = httpx.Response(429, request=httpx.Request("POST", "https://x"))

    def chunks(**kw):
        yield _chunk("a")
        raise openai.RateLimitError("slow down", response=resp, body=None)

    with pytest.raises(RuntimeError, match="rate limit"):
        list(_client(chunks).generate_stream("s", "u"))


def test_generate_stream_closes_upstream_when_abandoned():
    """Closing the generator early must close the OpenAI stream, or the model
    keeps generating (and billing) after the user has gone."""
    class Upstream:
        closed = False
        def __iter__(self):
            yield _chunk("a")
            yield _chunk("b")
        def close(self):
            Upstream.closed = True

    g = _client(lambda **kw: Upstream()).generate_stream("s", "u")
    assert next(g) == "a"
    g.close()
    assert Upstream.closed
