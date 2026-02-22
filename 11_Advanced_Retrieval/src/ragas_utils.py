# Need to make functions for the following:
# - running ragas evaluation
# - processing ragas results

from langchain_openai import ChatOpenAI
from typing import Dict, Iterable
import pandas as pd
from langchain_core.runnables import Runnable
from ragas.dataset_schema import EvaluationResult
from ragas.testset import Testset
from ragas import evaluate, EvaluationDataset
from ragas.metrics import (
    LLMContextRecall,
    FactualCorrectness,
    ContextEntityRecall,
    NoiseSensitivity,
)
from ragas.llms import LangchainLLMWrapper

evaluator_llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4.1-mini"))


def run_ragas_evaluation(retriever_chain: Runnable, chain_name: str, dataset: Testset):
    metrics = [
        LLMContextRecall(),
        FactualCorrectness(),
        ContextEntityRecall(),
        NoiseSensitivity(),
    ]

    rows = []
    for row in dataset:
        question = row.eval_sample.user_input
        out = retriever_chain.invoke({"question" : question})

        resp = out["response"]
        response_text = resp.content if hasattr(resp, "content") else resp.get("content", "")
        retrieved_contexts = [c.page_content for c in out["context"]]

        rows.append({
            "user_input" : question,
            "retrieved_contexts" : retrieved_contexts,
            "response" : response_text,
            "reference_contexts" : row.eval_sample.reference_contexts,
            "reference" : row.eval_sample.reference,
        })

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


def compare_ragas_results(results: Dict[str, EvaluationResult]):
    """ 
    Compare RAGAS results for different retriever chains and return a table.

    """
    keep_metrics = [
        "llm_context_recall",
        "factual_correctness",
        "context_entity_recall",
        "noise_sensitivity",
    ]
    
    rows = {}
    for chain_name, result in results.items():
        metrics = _filter_result_metrics(result, keep_metrics)
        rows[chain_name] = metrics

    df = pd.DataFrame.from_dict(rows, orient="index")
    
    return df.round(3)


# def process_ragas_results(eval_results: EvaluationResult, chain_name: str):
#     """ Process the Ragas results for a given chain and 
