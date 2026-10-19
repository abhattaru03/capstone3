"""
Retrieval agent solution — same underlying logic as
building-the-orchestrator-main/agents/retrieval_agent.py, wrapped in the
retrieval_agent()/check_grounding() interface that
shared-tool-registry-lab-solution's run_retrieval_agent() expects, per its
own import: `from retrieval_agent_solution import retrieval_agent, check_grounding`.
"""
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import os
import onnx_embed
from bedrock_client import invoke_claude

HOST = os.environ.get("OS_HOST", "search-orchestrator-search-ab-gokhchn2ej4vp6lyvtfwr5qdce.us-east-1.es.amazonaws.com")
REGION = "us-east-1"

_embed_model = None


def get_embedding(text: str) -> list[float]:
    import inspect
    names = ("get_embedding", "embed_text", "embed", "encode", "get_embeddings", "embed_texts")
    fn = next((getattr(onnx_embed, n) for n in names if hasattr(onnx_embed, n)), None)
    if fn is None:
        fn = next(f for n, f in inspect.getmembers(onnx_embed, inspect.isfunction)
                  if not n.startswith("_") and f.__module__ == "onnx_embed")
    v = fn(text)
    v = v.tolist() if hasattr(v, "tolist") else list(v)
    return v[0] if v and isinstance(v[0], list) else v


def get_opensearch_client():
    credentials = boto3.Session().get_credentials()
    auth = AWS4Auth(credentials.access_key, credentials.secret_key,
                     REGION, "es", session_token=credentials.token)
    return OpenSearch(
        hosts=[{"host": HOST, "port": 443}],
        http_auth=auth, use_ssl=True, verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


def retrieve(question: str, top_k: int = 5) -> list[dict]:
    query_vector = get_embedding(question)
    client = get_opensearch_client()
    response = client.search(
        index="documents",
        body={"size": top_k, "query": {"knn": {"embedding": {"vector": query_vector, "k": top_k}}}}
    )
    return [
        {"content": hit["_source"]["content"], "source": hit["_source"]["source"], "score": hit["_score"]}
        for hit in response["hits"]["hits"]
    ]


def generate_cited_answer(question: str, chunks: list[dict]) -> str:
    context = "\n\n".join([f"[Source {i+1}: {c['source']}]\n{c['content']}" for i, c in enumerate(chunks)])
    prompt = (
        "Answer the question using ONLY the context provided below. "
        "If the answer is not in the context, say 'I cannot find this information in the provided documents.' "
        "Always cite the source number(s) you used.\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER:"
    )
    return invoke_claude(prompt, max_tokens=500)["text"]


def check_grounding(answer: str, chunks: list[dict]) -> bool:
    import re
    cited_sources = re.findall(r"Source (\d+)", answer)
    if not cited_sources:
        return "cannot find" in answer.lower()
    return all(1 <= int(s) <= len(chunks) for s in cited_sources)


def retrieval_agent(question: str) -> dict:
    chunks = retrieve(question)
    if not chunks:
        return {"answer": "No relevant documents found.", "sources": [], "chunks": []}

    answer = generate_cited_answer(question, chunks)
    return {
        "answer": answer,
        "sources": [c["source"] for c in chunks],
        "chunks": chunks
    }