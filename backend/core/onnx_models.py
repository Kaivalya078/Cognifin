"""
ONNX Runtime stand-ins for the two sentence-transformers models, so the API runs without
PyTorch (1 GB server). They reproduce what sentence-transformers computes:

- OnnxEmbedder.encode: BERT last_hidden_state -> CLS token -> L2 normalise (bge-base's
  Transformer / Pooling(cls) / Normalize modules), max 512 tokens.
- OnnxCrossEncoder.predict: logits[:, 0] -> sigmoid (CrossEncoder.predict's default
  activation for a one-label model), max 512 tokens, longest-first truncation.

Exports come from ingestion/export_onnx.py; settings.MODEL_BACKEND selects them.
"""
from pathlib import Path

import numpy as np

MAX_TOKENS = 512
# One text (pair) per run. The exported graph materialises full attention (batch x 12 heads
# x seq x seq floats), so batches spiked a 1 GB container; one-at-a-time also skips padding
# (faster on 1 vCPU) and makes int8 scores independent of what shares a batch
# (dynamic quantisation scales activations per run).
MAX_BATCH = 1


def _load(model_dir: str, int8: bool, threads: int = 0):
    import onnxruntime as ort
    from tokenizers import Tokenizer

    d = Path(model_dir)
    tok = Tokenizer.from_file(str(d / "tokenizer.json"))
    tok.enable_truncation(MAX_TOKENS, strategy="longest_first")
    tok.enable_padding(pad_id=tok.token_to_id("[PAD]") or 0, pad_token="[PAD]")
    opts = ort.SessionOptions()
    opts.enable_cpu_mem_arena = False          # the arena keeps peak buffers; we want RAM back
    opts.intra_op_num_threads = threads        # 0 = one per core ONNX Runtime sees
    session = ort.InferenceSession(str(d / ("model_int8.onnx" if int8 else "model.onnx")),
                                   opts, providers=["CPUExecutionProvider"])
    return tok, session


def _feeds(session, encodings) -> dict:
    cols = {"input_ids": "ids", "attention_mask": "attention_mask", "token_type_ids": "type_ids"}
    return {i.name: np.array([getattr(e, cols[i.name]) for e in encodings], dtype=np.int64)
            for i in session.get_inputs()}


class OnnxEmbedder:
    def __init__(self, tokenizer, session, dim: int = 768):
        self.tok, self.session, self.dim = tokenizer, session, dim

    @classmethod
    def from_dir(cls, model_dir: str, int8: bool = False, threads: int = 0) -> "OnnxEmbedder":
        return cls(*_load(model_dir, int8, threads))

    def get_sentence_embedding_dimension(self) -> int:
        return self.dim

    def encode(self, texts, batch_size: int = 32, **_) -> np.ndarray:
        batch_size = min(batch_size, MAX_BATCH)
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tok.encode_batch(list(texts[i:i + batch_size]))
            cls_vec = self.session.run(None, _feeds(self.session, enc))[0][:, 0, :]
            out.append(cls_vec / np.maximum(np.linalg.norm(cls_vec, axis=1, keepdims=True), 1e-12))
        return np.concatenate(out).astype(np.float32) if out else np.zeros((0, self.dim), np.float32)


class OnnxCrossEncoder:
    def __init__(self, tokenizer, session):
        self.tok, self.session = tokenizer, session

    @classmethod
    def from_dir(cls, model_dir: str, int8: bool = False, threads: int = 0) -> "OnnxCrossEncoder":
        return cls(*_load(model_dir, int8, threads))

    def predict(self, pairs, batch_size: int = MAX_BATCH, **_) -> np.ndarray:
        batch_size = min(batch_size, MAX_BATCH)
        scores = []
        for i in range(0, len(pairs), batch_size):
            enc = self.tok.encode_batch([tuple(p) for p in pairs[i:i + batch_size]])
            logits = self.session.run(None, _feeds(self.session, enc))[0][:, 0]
            scores.append(1.0 / (1.0 + np.exp(-logits)))
        return np.concatenate(scores) if scores else np.zeros(0)
