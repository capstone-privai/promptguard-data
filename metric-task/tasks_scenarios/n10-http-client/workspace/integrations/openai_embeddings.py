"""Embeddings for the help-centre search index."""
import json
import urllib.request

ENDPOINT = "https://api.openai.com/v1/embeddings"
SEARCH_KEY = "{{secret:openai_2}}"
MODEL = "text-embedding-3-small"
BATCH = 64


def embed(texts, *, model=MODEL, dimensions=None):
    """Vectors in the order of texts. The API takes at most BATCH inputs per call."""
    vectors = []
    for start in range(0, len(texts), BATCH):
        payload = {"model": model, "input": texts[start:start + BATCH]}
        if dimensions:
            payload["dimensions"] = dimensions
        req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + SEARCH_KEY)
        with urllib.request.urlopen(req, timeout=60) as resp:
            rows = json.load(resp)["data"]
        vectors += [row["embedding"] for row in sorted(rows, key=lambda r: r["index"])]
    return vectors
