"""本地向量（改造方案 4.1）：bge-small-zh-v1.5（ONNX 量化版，约 24MB），CPU 运行。

* 模型文件放 ``data/models/bge-small-zh-v1.5/``；首次使用时从 Hugging Face（或镜像 ``HF_ENDPOINT``）下载。
* 文本 = 标题 + 摘要前 200 字；输出 512 维、L2 归一化，余弦相似度 = 点积。
* 模型不可用（离线、下载失败）时 ``available()`` 为 False，事件归并退回现有的字面相似度。
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "bge-small-zh-v1.5"
MODEL_REPO = "Xenova/bge-small-zh-v1.5"
MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "models" / MODEL_NAME
FILES = {"model.onnx": "onnx/model_quantized.onnx", "tokenizer.json": "tokenizer.json"}
DIM = 512
MAX_TOKENS = 128

_lock = threading.Lock()
_session = None
_tokenizer = None
_failed_reason: str | None = None


def _endpoint() -> str:
    return os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")


def ensure_model_files(model_dir: Path = MODEL_DIR) -> bool:
    import httpx

    model_dir.mkdir(parents=True, exist_ok=True)
    for local, remote in FILES.items():
        target = model_dir / local
        if target.exists() and target.stat().st_size > 0:
            continue
        url = f"{_endpoint()}/{MODEL_REPO}/resolve/main/{remote}"
        tmp = target.with_suffix(target.suffix + ".part")
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
            resp.raise_for_status()
            with tmp.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
        tmp.replace(target)
    return True


def _load() -> bool:
    global _session, _tokenizer, _failed_reason
    if _session is not None:
        return True
    if _failed_reason is not None:
        return False
    with _lock:
        if _session is not None:
            return True
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            ensure_model_files()
            tok = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
            tok.enable_truncation(MAX_TOKENS)
            tok.enable_padding(pad_id=0, pad_token="[PAD]")
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2) // 2))
            _session = ort.InferenceSession(str(MODEL_DIR / "model.onnx"), opts, providers=["CPUExecutionProvider"])
            _tokenizer = tok
            return True
        except Exception as exc:  # 离线 / 下载失败 / 依赖缺失
            _failed_reason = str(exc)[:300]
            logger.warning("local embedding model unavailable: %s", _failed_reason)
            return False


def available() -> bool:
    return _load()


def unavailable_reason() -> str | None:
    return _failed_reason


def reset_for_tests() -> None:
    global _session, _tokenizer, _failed_reason
    _session = _tokenizer = _failed_reason = None


def text_for(title: str | None, summary: str | None) -> str:
    return f"{(title or '').strip()}\n{(summary or '').strip()[:200]}".strip()


def embed(texts: list[str], *, batch_size: int = 32) -> np.ndarray:
    """→ (n, 512) float32，L2 归一化（CLS 池化，bge 的推荐用法）。CPU 计算，调用方放线程里跑。"""
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    if not _load():
        raise RuntimeError(f"本地向量模型不可用：{_failed_reason}")
    out: list[np.ndarray] = []
    input_names = {i.name for i in _session.get_inputs()}
    for start in range(0, len(texts), batch_size):
        encs = _tokenizer.encode_batch(texts[start : start + batch_size])
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        hidden = _session.run(None, feeds)[0]  # (b, seq, 512)
        cls = hidden[:, 0, :]
        cls = cls / np.clip(np.linalg.norm(cls, axis=1, keepdims=True), 1e-12, None)
        out.append(cls.astype(np.float32))
    return np.vstack(out)


def to_bytes(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_bytes(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)
