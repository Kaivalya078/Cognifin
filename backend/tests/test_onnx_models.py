"""ONNX runtime wrappers reproduce sentence-transformers' outputs (1 GB server, no PyTorch)."""
from types import SimpleNamespace

import numpy as np

from core.onnx_models import OnnxCrossEncoder, OnnxEmbedder


class FakeTok:
    def encode_batch(self, items):
        return [SimpleNamespace(ids=[1, 2, 3], attention_mask=[1, 1, 1], type_ids=[0, 0, 0]) for _ in items]


class FakeSession:
    def __init__(self, out):
        self.out, self.feeds = out, []

    def get_inputs(self):
        return [SimpleNamespace(name=n) for n in ("input_ids", "attention_mask", "token_type_ids")]

    def run(self, names, feeds):
        self.feeds.append(feeds)
        return [self.out(len(feeds["input_ids"]))]


def test_embedder_takes_cls_token_and_l2_normalises():
    def hidden(b):
        return np.stack([[[3.0, 4.0], [9.0, 9.0], [9.0, 9.0]]] * b)   # CLS = (3, 4)

    e = OnnxEmbedder(FakeTok(), FakeSession(hidden), dim=2)
    v = e.encode(["a", "b", "c"], batch_size=2)
    assert v.shape == (3, 2) and np.allclose(v, [[0.6, 0.8]] * 3)
    assert e.get_sentence_embedding_dimension() == 2


def test_cross_encoder_returns_sigmoid_of_logits_like_predict():
    """sentence-transformers' CrossEncoder.predict applies a sigmoid for one-label models."""
    logits = iter([0.0, 2.0])
    c = OnnxCrossEncoder(FakeTok(), FakeSession(lambda b: np.array([[next(logits)] for _ in range(b)])))
    assert np.allclose(c.predict([("q", "d1"), ("q", "d2")]), [0.5, 1 / (1 + np.exp(-2.0))])


def test_feeds_are_int64_and_only_the_inputs_the_model_declares():
    s = FakeSession(lambda b: np.zeros((b, 3, 2)))
    OnnxEmbedder(FakeTok(), s, dim=2).encode(["x"])
    assert set(s.feeds[0]) == {"input_ids", "attention_mask", "token_type_ids"}
    assert all(a.dtype == np.int64 for a in s.feeds[0].values())


def test_batches_are_capped_to_bound_peak_memory():
    """The ONNX graph materialises full attention; 30 pairs at once spiked a 1 GB container."""
    from core.onnx_models import MAX_BATCH
    s = FakeSession(lambda b: np.zeros((b, 1)))
    OnnxCrossEncoder(FakeTok(), s).predict([("q", "d")] * 30)
    assert max(len(f["input_ids"]) for f in s.feeds) == MAX_BATCH == 1
