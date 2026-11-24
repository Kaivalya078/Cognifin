"""Server-sent-event framing and the [FOLLOW_UP] hold-back for streamed answers."""

import json
from typing import Iterable, Iterator

_MARK = "[FOLLOW_UP]"


def sse(event: str, data: dict) -> str:
    """One SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def hold_follow_ups(deltas: Iterable[str]) -> Iterator[str]:
    """Pass LLM text through, dropping [FOLLOW_UP] lines.

    A line is held only while it could still become a follow-up line (it is a
    prefix of the marker, or starts with it); anything else is released at once.
    The final answer from extract_follow_ups stays authoritative.
    """
    line, sent = "", 0
    for delta in deltas:
        out = []
        for ch in delta:
            if ch == "\n":
                if not line.startswith(_MARK):
                    out.append(line[sent:] + "\n")
                line, sent = "", 0
                continue
            line += ch
            if sent == 0 and (_MARK.startswith(line) or line.startswith(_MARK)):
                continue  # undecided or a follow-up line: hold
            out.append(line[sent:])
            sent = len(line)
        if out:
            yield "".join(out)
    if not line.startswith(_MARK) and line[sent:]:
        yield line[sent:]
