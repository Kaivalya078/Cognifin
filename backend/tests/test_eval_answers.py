import json
from types import SimpleNamespace as NS

import pytest

from tests.eval_answers import RecordingClient, build_metrics, check_flags, judge


def test_check_flags_refuses():
    with pytest.raises(SystemExit):
        check_flags(NS(INTELLIGENT_PARSING_ENABLED=True, MULTI_QUERY_ENABLED=False))
    with pytest.raises(SystemExit):
        check_flags(NS(INTELLIGENT_PARSING_ENABLED=False, MULTI_QUERY_ENABLED=True))
    assert check_flags(NS(INTELLIGENT_PARSING_ENABLED=False, MULTI_QUERY_ENABLED=False)) is None


def _chunk(text):
    return NS(choices=[NS(delta=NS(content=text))], usage=None)


class FakeCompletions:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        return self.replies.pop(0)


def _client(replies, model="gpt-4o-mini"):
    comp = FakeCompletions(replies)
    return NS(model=model, is_configured=True, client=NS(chat=NS(completions=comp))), comp


def test_recording_client_yields_same_text_and_usage():
    stream = iter([_chunk("Hel"), _chunk("lo"),
                   NS(choices=[], usage=NS(prompt_tokens=7, completion_tokens=2))])
    real, comp = _client([stream])
    rc = RecordingClient(real)
    assert "".join(rc.generate_stream("S", "U")) == "Hello"
    assert rc.last == {"system": "S", "user": "U", "in": 7, "out": 2}
    kw = comp.calls[0]
    assert kw["stream_options"] == {"include_usage": True}
    assert kw["temperature"] == 0 and kw["max_tokens"] == 1000 and kw["stream"] is True
    assert kw["messages"] == [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]


def _reply(content, i=10, o=5):
    return NS(choices=[NS(message=NS(content=content))], usage=NS(prompt_tokens=i, completion_tokens=o))


def test_judge_retries_once_then_none():
    real, comp = _client([_reply("nope"), _reply("still nope")])
    parsed, tok = judge(real, "ctx", "ans", "key", "table")
    assert parsed is None and len(comp.calls) == 2 and tok == {"in": 20, "out": 10}

    good = json.dumps({"claims": [], "correct": "yes"})
    real, comp = _client([_reply("nope"), _reply(good)])
    parsed, tok = judge(real, "ctx", "ans", "key", "table")
    assert parsed["correct"] == "yes" and len(comp.calls) == 2
    assert comp.calls[0]["temperature"] == 0
    assert comp.calls[0]["response_format"] == {"type": "json_object"}


def test_build_metrics_shape():
    ans = {"faithfulness": 0.9, "latency_ms": {"p50": 1, "p95": 2},
           "cost_usd": {"per_question": 0.001, "judge_per_question": 0.001}}
    ret = {"overall": {"n": 2, "hit3": 0.5, "hit8": 1.0, "mrr": 0.7, "recall60": 1.0}}
    v1 = {"overall": {"n": 1, "hit3": 0.8, "hit8": 1.0, "mrr": 0.7, "recall60": 1.0}}
    m = build_metrics("x", ans, ret, v1, {"precision": 1.0, "coverage": 0.9},
                      {"chunks": 1, "documents": 1, "companies": 1, "disk_mb": 1.0},
                      {"version": 2, "cases": 2, "companies": 1, "kinds": {}},
                      {"intelligent_parsing": False, "multi_query": False}, "gpt-4o-mini", "gpt-4o-mini")
    assert set(m) == {"generated_at", "label", "model", "judge_model", "settings", "golden_set",
                      "answers", "retrieval", "financials", "latency_ms", "cost_usd", "index"}
    assert set(m["retrieval"]) == {"hit@3", "hit@8", "mrr", "recall@60", "v1_hit@3"}
    assert m["retrieval"]["v1_hit@3"] == 0.8
    assert "latency_ms" not in m["answers"] and m["latency_ms"] == {"p50": 1, "p95": 2}


def test_cited_ids_kept_only_if_in_answer():
    from tests.eval_answers import keep_written_cites
    claims = [{"text": "a", "supported": True, "cited": ["chunk_1", "fin_2", "chunk_9"]}]
    out = keep_written_cites(claims, "Revenue was 10 [chunk_1] and margin 5 (fin_2).")
    assert out[0]["cited"] == ["chunk_1", "fin_2"]
    assert keep_written_cites(claims, "no ids here")[0]["cited"] == []
