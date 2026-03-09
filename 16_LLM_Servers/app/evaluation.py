import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import tiktoken
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, PyMuPDFLoader
from langchain_core.documents import Document
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.evaluation import EvaluationDataset, EvaluationResult, evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (ContextEntityRecall, ContextPrecision,
                           FactualCorrectness, Faithfulness, LLMContextRecall,
                           ResponseRelevancy)
from ragas.run_config import RunConfig
from ragas.testset import Testset, TestsetGenerator
from ragas.testset.synthesizers.single_hop.specific import \
    SingleHopSpecificQuerySynthesizer

from app.rag import _get_gpt_rag_graph, _get_rag_graph


ROOT_DIR = Path(__file__).resolve().parents[1]
print(f"Loading .env file from {ROOT_DIR / '.env'}")
load_dotenv(ROOT_DIR / ".env", override=True)
print(f"OPENAI_API_KEY: {os.environ['OPENAI_API_KEY'][:20]}...")


def save_dataset(dataset: Testset, path: str) -> None:
    """
    Save a dataset to a JSON file.
    """
    df = dataset.to_pandas()
    df.to_json(path, orient="records")
    print(f"Saved dataset to {path}")

def load_dataset(path: str) -> Testset:
    """
    Load a dataset from a JSON file.
    """
    df = pd.read_json(path, orient="records", dtype_backend="numpy_nullable")
    return Testset.from_pandas(df)

def _tiktoken_len(text: str) -> int:
    """Return token length for chunk sizing (used so RAGAS picks the 101-500 branch)."""
    enc = tiktoken.encoding_for_model("gpt-4o-mini")
    return len(enc.encode(text))


def load_documents(data_dir: str):
    """Load documents from a directory."""
    directory_loader = DirectoryLoader(
        data_dir, glob="**/*.pdf", loader_cls=PyMuPDFLoader
    )
    documents = directory_loader.load()
    return documents


def chunk_documents_for_ragas(documents: list[Document], chunk_size: int = 400, chunk_overlap: int = 50) -> list[Document]:
    """
    Chunk documents so each piece is in the 101-500 token range.

    RAGAS default_transforms uses HeadlineSplitter only when many docs have >500 tokens,
    which requires a 'headlines' property and can fail. Chunking into 101-500 tokens
    forces the alternative pipeline that does not use HeadlineSplitter.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=_tiktoken_len,
    )
    return splitter.split_documents(documents) if documents else []


def generate_sdg_testset(documents: list[Document]):
    """Generate a SDG testset from a list of documents."""

    # Chunk into 101-500 token range so RAGAS uses the pipeline without HeadlineSplitter
    # (avoids "'headlines' property not found in this node" from long docs).
    chunks = chunk_documents_for_ragas(documents)

    rate_limiter = InMemoryRateLimiter(
        requests_per_second=2, check_every_n_seconds=0.1, max_bucket_size=1
    )
    generator_llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4.1-mini", rate_limiter=rate_limiter, max_retries=3))
    generator_embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings())

    generator = TestsetGenerator(llm=generator_llm, embedding_model=generator_embeddings)
    single_hop_distribution = [
        (SingleHopSpecificQuerySynthesizer(llm=generator_llm, llm_context=generator.llm_context), 1.0)
    ]

    run_config = RunConfig(
        max_workers=2,
        timeout=180,
        max_retries=3,
        max_wait=60,
        log_tenacity=True,
    )

    dataset = generator.generate_with_langchain_docs(
        chunks,
        testset_size=5,
        query_distribution=single_hop_distribution,
        run_config=run_config,
        with_debugging_logs=True,
        raise_exceptions=True,
    )

    return dataset


def run_ragas_evaluation(graph: Runnable, chain_name: str, dataset: Testset):
    """
    Run Ragas evaluation for a given retriever chain and return the results.
    """
    metrics = [
        LLMContextRecall(),
        ContextPrecision(),
        ContextEntityRecall(),
        Faithfulness(),
        FactualCorrectness(),
        ResponseRelevancy()
    ]

    evaluator_llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4.1"))

    rows = []
    for row in dataset:
        question = row.eval_sample.user_input

        t_start = time.perf_counter()
        out = graph.invoke({"question": question})
        latency_ms = (time.perf_counter() - t_start) * 1000

        # RAG graph returns response as string and context as list of Documents
        resp = out.get("response")
        if isinstance(resp, str):
            response_text = resp
            usage = {}
        else:
            response_text = resp.content if hasattr(resp, "content") else (resp.get("content", "") if isinstance(resp, dict) else "")
            usage = getattr(resp, "response_metadata", None) or {}
            usage = usage.get("token_usage", {}) if isinstance(usage, dict) else {}

        context_docs = out.get("context", [])
        retrieved_contexts = [c.page_content for c in context_docs]

        # Token usage (assuming OpenAI metadata)
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        rows.append({
            "user_input" : question,
            "retrieved_contexts" : retrieved_contexts,
            "response" : response_text,
            "reference_contexts" : row.eval_sample.reference_contexts,
            "reference" : row.eval_sample.reference,

            # Latency
            "latency_ms": latency_ms,

            # Token usage
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        })
        time.sleep(5)  # Sleep to avoid rate limiting

    eval_df = pd.DataFrame(rows)
    evaluation_dataset = EvaluationDataset.from_pandas(eval_df)
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=metrics,
        llm=evaluator_llm,
    )

    return {
        "chain_name" : chain_name,
        "results" : result,
        "eval_df" : eval_df,
        "summary": {
            "avg_latency_ms": float(eval_df["latency_ms"].mean()),
            "p95_latency_ms": float(eval_df["latency_ms"].quantile(0.95)),
            "avg_total_tokens": float(eval_df["total_tokens"].mean()),
            "total_tokens_sum": int(eval_df["total_tokens"].sum()),
        }
    }


def _filter_result_metrics(result: EvaluationResult, keep_metrics: Iterable):
    df = result.to_pandas()

    # Coerce numeric columns
    df_num = df.apply(pd.to_numeric, errors="coerce")

    out = {}
    for metric in keep_metrics:
        if metric in df_num.columns:
            out[metric] = float(df_num[metric].mean())
    return out


def compare_ragas_results(all_evaluation_results: List[Dict[str, EvaluationResult]]):
    """ 
    Compare RAGAS results for different retriever chains and return a table.
    """
    rows = {}
    for evaluation_result in all_evaluation_results:
        chain_name = evaluation_result["chain_name"]
        eval_result = evaluation_result["results"]
        # metrics = _filter_result_metrics(eval_result, keep_metrics)
        # rows[chain_name] = metrics
        df = eval_result.to_pandas()
        df_num = df.apply(pd.to_numeric, errors="coerce")
        
        rows[chain_name] = df_num.to_dict()

    df = pd.DataFrame.from_dict(rows, orient="index")
    
    return df.round(3)


if __name__ == "__main__":
    # documents = load_documents("data")
    # dataset = generate_sdg_testset(documents)
    # save_dataset(dataset, "data/sdg_testset.json")
    dataset = load_dataset("data/sdg_testset.json")

    rag_graph = _get_rag_graph()
    evaluation_results = run_ragas_evaluation(rag_graph, "Fireworks RAG", dataset)
    print(evaluation_results)
    df = compare_ragas_results([evaluation_results])
    print(df)

    # gpt_rag_graph = _get_gpt_rag_graph()
    # evaluation_results = run_ragas_evaluation(gpt_rag_graph, "GPT RAG", dataset)
    # print(evaluation_results)
    # df = compare_ragas_results([evaluation_results])
    # print(df)