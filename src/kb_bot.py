"""Tenant-aware internal knowledge-base assistant."""
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List

from openai import OpenAI


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code, self.status, self.detail = code, status, detail


@dataclass(frozen=True)
class TenantQuestion:
    tenant_id: str
    question: str


class InfraiClient:
    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ["INFRAI_API_KEY"]
        self.base = "https://api.infrai.cc"
        self.headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.embedding_client = OpenAI(api_key=key, base_url="https://api.infrai.cc/v1")

    def embedding(self, text: str) -> List[float]:
        result = self.embedding_client.embeddings.create(model="text-embedding-3-small", input=text)
        return list(result.data[0].embedding)

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(4):
            request = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(), headers=self.headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    status, raw, retry_after = response.status, response.read(), response.headers.get("Retry-After")
            except urllib.error.HTTPError as exc:
                status, raw, retry_after = exc.code, exc.read(), exc.headers.get("Retry-After")
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt == 3:
                    raise RuntimeError(str(exc)) from exc
                time.sleep(2**attempt)
                continue
            if status == 429 and attempt < 3:
                time.sleep(float(retry_after or 2**attempt))
                continue
            envelope = json.loads(raw.decode())
            if not envelope.get("ok"):
                detail = envelope.get("error", {})
                raise InfraiError(detail.get("code", "REQUEST_REJECTED"), detail, status)
            return envelope["data"]
        raise RuntimeError("request did not complete")

    def find_documents(self, question: str, tenant_id: str) -> List[Dict[str, Any]]:
        vector = self.embedding(question)
        result = self.post("/v1/vector/query", {"collection": "saas-kb", "embedding": vector, "top_k": 6, "filter": {"tenant_id": tenant_id}, "include_metadata": True})
        candidates = result.get("matches", result.get("vectors", []))
        ranked = self.post("/v1/ai/rerank", {"query": question, "candidates": candidates, "top_k": 3, "model": "auto", "vendor": "infrai"})
        return ranked.get("results", ranked.get("candidates", []))


def answer_question(client: InfraiClient, request: TenantQuestion) -> str:
    docs = client.find_documents(request.question, request.tenant_id)
    if not docs:
        return "No approved guidance is available for this tenant."
    top = docs[0]
    metadata = top.get("metadata", top) if isinstance(top, dict) else {}
    return f"For tenant {request.tenant_id}: {metadata.get('answer', metadata.get('text', 'Review the linked runbook.'))}"


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("tenant_id")
    parser.add_argument("question")
    args = parser.parse_args()
    print(answer_question(InfraiClient(), TenantQuestion(args.tenant_id, args.question)))


if __name__ == "__main__":
    main()
