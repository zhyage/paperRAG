"""BGE-M3 Embedding — 本地模型。"""

import logging
from ..config import EMBEDDING_MODEL, EMBEDDING_DEVICE, EMBEDDING_BATCH_SIZE, DENSE_DIM

logger = logging.getLogger(__name__)

_encoder = None
_is_flag = False  # True = FlagEmbedding, False = SentenceTransformer


def _get_encoder():
    global _encoder, _is_flag
    if _encoder is not None:
        return _encoder

    logger.info("Loading BGE-M3: %s on %s", EMBEDDING_MODEL, EMBEDDING_DEVICE)
    try:
        from FlagEmbedding import BGEM3FlagModel
        _encoder = BGEM3FlagModel(EMBEDDING_MODEL, use_fp16=False, device=EMBEDDING_DEVICE)
        _is_flag = True
        logger.info("BGE-M3 loaded via FlagEmbedding")
    except Exception:
        logger.warning("FlagEmbedding not available, falling back to sentence-transformers")
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
        _is_flag = False
        logger.info("BGE-M3 loaded via sentence-transformers")
    return _encoder


def _is_flag_encoder():
    _get_encoder()
    return _is_flag


def encode(texts: list[str], batch_size: int = None) -> list[dict]:
    if batch_size is None:
        batch_size = EMBEDDING_BATCH_SIZE
    enc = _get_encoder()
    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        if _is_flag:
            out = enc.encode(batch, batch_size=batch_size, max_length=8192,
                             return_dense=True, return_sparse=True, return_colbert_vecs=False)
            for j in range(len(batch)):
                results.append({"dense": out["dense_vecs"][j].tolist(), "sparse": out["lexical_weights"][j]})
        else:
            out = enc.encode(batch, batch_size=batch_size, show_progress_bar=False)
            for j in range(len(batch)):
                results.append({"dense": out[j].tolist(), "sparse": {}})
    return results


def encode_query(text: str) -> dict:
    enc = _get_encoder()
    if _is_flag:
        out = enc.encode([text], max_length=8192, return_dense=True, return_sparse=True, return_colbert_vecs=False)
        return {"dense": out["dense_vecs"][0].tolist(), "sparse": out["lexical_weights"][0]}
    else:
        out = enc.encode([text], show_progress_bar=False)
        return {"dense": out[0].tolist(), "sparse": {}}


def get_dense_dim() -> int:
    return DENSE_DIM
