"""本地 Embedding 封装。"""

from typing import Iterable

from sentence_transformers import SentenceTransformer


class Embedder:
    """使用本地 SentenceTransformer 模型生成向量。"""

    def __init__(
        self,
        model: str = "BAAI/bge-small-zh-v1.5",
        batch_size: int = 32,
    ):
        self._model = model
        self._batch_size = batch_size

        print(f"正在加载本地 Embedding 模型: {model}")

        self._encoder = SentenceTransformer(model)

    @property
    def model(self) -> str:
        return self._model

    def encode(self, texts: Iterable[str]) -> list[list[float]]:
        """批量编码文本。"""
        texts = list(texts)

        if not texts:
            return []

        vectors = self._encoder.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
        )

        return vectors.tolist()

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]