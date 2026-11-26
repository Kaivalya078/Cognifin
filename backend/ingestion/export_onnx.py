"""
Export the embedding model and the reranker to ONNX (fp32 + dynamic int8), so the API
can run without PyTorch (1 GB VM target). Run where torch is installed: locally or in
the Docker build stage.

    python -m ingestion.export_onnx [--out models_onnx]

Writes <out>/{embedder,reranker}/{model.onnx, model_int8.onnx, tokenizer.json}.
Each fp32 export is checked against the PyTorch model on sample text before it is kept.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings  # noqa: E402

SAMPLES = ["Revenue from operations rose to ₹2,40,893 crore in FY2024.",
           "What was HDFC Bank's gross NPA ratio for the quarter ended September 2025?"]


class _ByName(torch.nn.Module):
    """Positional ONNX inputs -> keyword call (BertModel.forward's positional order varies by version)."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask, token_type_ids):
        return self.model(input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids)[0]


def _export(model, tok, out: Path, pair: bool, output: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    tok.save_pretrained(out)            # tokenizer.json (fast tokenizer) is what the runtime reads
    enc = tok(SAMPLES, SAMPLES[::-1], return_tensors="pt", padding=True) if pair else \
        tok(SAMPLES, return_tensors="pt", padding=True)
    names = ["input_ids", "attention_mask", "token_type_ids"]
    axes = {n: {0: "batch", 1: "seq"} for n in names}
    axes[output] = {0: "batch"} if pair else {0: "batch", 1: "seq"}
    fp32 = out / "model.onnx"
    with torch.no_grad():
        ref = model(**{n: enc[n] for n in names})[0].numpy()
        # eval(): export restores the wrapper's mode afterwards, recursively; a train-mode
        # wrapper would switch dropout back on in the model.
        torch.onnx.export(_ByName(model).eval(), tuple(enc[n] for n in names), str(fp32), input_names=names,
                          output_names=[output], dynamic_axes=axes, opset_version=17, dynamo=False)
    import onnxruntime as ort
    got = ort.InferenceSession(str(fp32), providers=["CPUExecutionProvider"]).run(
        [output], {n: enc[n].numpy() for n in names})[0]
    err = float(np.abs(got - ref).max())
    assert err < 1e-3, f"{out.name}: ONNX differs from PyTorch by {err}"
    quantize_dynamic(str(fp32), str(out / "model_int8.onnx"), weight_type=QuantType.QInt8)
    sizes = {p.name: f"{p.stat().st_size / 1e6:.0f} MB" for p in out.glob("*.onnx")}
    print(f"{out.name}: max |onnx - torch| = {err:.2e}; {sizes}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=settings.ONNX_DIR)
    out = Path(ap.parse_args().out)
    emb = settings.EMBEDDING_MODEL
    _export(AutoModel.from_pretrained(emb).eval(), AutoTokenizer.from_pretrained(emb),
            out / "embedder", pair=False, output="last_hidden_state")
    rr = settings.RERANKER_MODEL
    _export(AutoModelForSequenceClassification.from_pretrained(rr).eval(), AutoTokenizer.from_pretrained(rr),
            out / "reranker", pair=True, output="logits")


if __name__ == "__main__":
    main()
