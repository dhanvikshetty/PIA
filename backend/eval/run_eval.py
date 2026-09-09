"""
Evaluation Harness

Measures retrieval quality and answer quality across the labeled eval set.
Runs before/after comparisons to quantify the impact of hybrid search
and re-ranking.

Retrieval metrics: precision@k, recall@k, MRR
Answer metrics: faithfulness (LLM-as-judge)

Usage:
    python -m backend.eval.run_eval
"""

import json
import os
import time
import argparse
from pathlib import Path
from datetime import datetime
from loguru import logger

from backend.config import settings
from backend.rag.retriever import hybrid_retrieve, dense_only_retrieve
from backend.rag.reranker import rerank
from backend.rag.generator import generate_answer


def load_eval_set(path: str = None) -> list[dict]:
    """Load the labeled evaluation set."""
    if path is None:
        path = Path(__file__).parent / "eval_set.json"
    else:
        path = Path(path)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Retrieval Metrics
# ============================================================

def precision_at_k(retrieved_sources: list[str], expected_sources: list[str], k: int) -> float:
    """
    Precision@K: fraction of top-k retrieved chunks that are relevant.
    A retrieved chunk is "relevant" if its source_file matches any expected source.
    """
    if not expected_sources or k == 0:
        return 0.0

    top_k = retrieved_sources[:k]
    relevant = sum(1 for s in top_k if any(exp in s for exp in expected_sources))
    return relevant / k


def recall_at_k(retrieved_sources: list[str], expected_sources: list[str], k: int) -> float:
    """
    Recall@K: fraction of expected source chunks that appear in top-k.
    """
    if not expected_sources:
        return 0.0

    top_k = retrieved_sources[:k]
    found = sum(1 for exp in expected_sources if any(exp in s for s in top_k))
    return found / len(expected_sources)


def mean_reciprocal_rank(retrieved_sources: list[str], expected_sources: list[str]) -> float:
    """
    MRR: 1 / position of the first relevant retrieved chunk.
    """
    for i, source in enumerate(retrieved_sources):
        if any(exp in source for exp in expected_sources):
            return 1.0 / (i + 1)
    return 0.0


# ============================================================
# Answer Metrics (LLM-as-Judge)
# ============================================================

FAITHFULNESS_PROMPT = """You are an evaluator. Given a question, the retrieved context, and a generated answer, assess whether the answer is FAITHFUL to the context.

Faithfulness means: every claim in the answer is supported by information in the context. The answer should NOT contain information that isn't in the context.

Question: {question}

Context (retrieved chunks):
{context}

Generated Answer:
{answer}

Score the faithfulness from 1 to 5:
1 = Completely unfaithful (hallucinated, no basis in context)
2 = Mostly unfaithful (major claims not supported)
3 = Partially faithful (some claims supported, some not)
4 = Mostly faithful (minor unsupported details)
5 = Fully faithful (every claim traceable to context)

Return ONLY a JSON object: {{"score": <1-5>, "reasoning": "<brief explanation>"}}"""


def evaluate_faithfulness(question: str, context_text: str, answer: str) -> dict:
    """Use LLM-as-judge to score answer faithfulness."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)

        llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=0.0,
        )

        prompt = FAITHFULNESS_PROMPT.format(
            question=question,
            context=context_text[:3000],  # Truncate for efficiency
            answer=answer,
        )
        response = llm.invoke(prompt)
        content = response.content.strip()

        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0]

        return json.loads(content)
    except Exception as e:
        logger.warning(f"Faithfulness evaluation failed: {e}")
        return {"score": 0, "reasoning": f"Evaluation failed: {str(e)}"}


# ============================================================
# Evaluation Runner
# ============================================================

def run_single_eval(
    eval_item: dict,
    mode: str = "hybrid_reranked",
) -> dict:
    """
    Run evaluation for a single question.

    Modes:
        - "dense_only": Dense retrieval only (baseline)
        - "hybrid": BM25 + Dense with RRF (no reranking)
        - "hybrid_reranked": Full pipeline (hybrid + rerank)
    """
    question = eval_item["question"]
    expected_sources = eval_item.get("expected_source_chunks", [])
    company = eval_item.get("company")

    k_values = [3, 5, 10]

    # --- Retrieval ---
    start_time = time.time()

    if mode == "dense_only":
        chunks = dense_only_retrieve(query=question, company=company)
    elif mode == "hybrid":
        chunks = hybrid_retrieve(query=question, company=company)
    elif mode == "hybrid_reranked":
        chunks = hybrid_retrieve(query=question, company=company)
        chunks = rerank(query=question, chunks=chunks)
    else:
        raise ValueError(f"Unknown mode: {mode}")

    retrieval_time = time.time() - start_time

    # Extract source files from retrieved chunks
    retrieved_sources = [
        c.get("metadata", {}).get("source_file", "") for c in chunks
    ]

    # --- Retrieval Metrics ---
    metrics = {
        "mode": mode,
        "question_id": eval_item["id"],
        "retrieval_time_ms": round(retrieval_time * 1000, 1),
        "chunks_retrieved": len(chunks),
    }

    for k in k_values:
        metrics[f"precision@{k}"] = precision_at_k(retrieved_sources, expected_sources, k)
        metrics[f"recall@{k}"] = recall_at_k(retrieved_sources, expected_sources, k)

    metrics["mrr"] = mean_reciprocal_rank(retrieved_sources, expected_sources)

    return metrics, chunks


def run_full_eval(
    eval_set_path: str = None,
    modes: list[str] = None,
    include_faithfulness: bool = False,
    output_path: str = None,
) -> dict:
    """
    Run full evaluation across all modes and the entire eval set.

    Args:
        eval_set_path: Path to eval_set.json
        modes: List of retrieval modes to evaluate
        include_faithfulness: Whether to run LLM-as-judge faithfulness scoring
        output_path: Where to save results JSON

    Returns:
        Complete evaluation results dict
    """
    if modes is None:
        modes = ["dense_only", "hybrid", "hybrid_reranked"]

    eval_set = load_eval_set(eval_set_path)
    logger.info(f"Running evaluation: {len(eval_set)} questions × {len(modes)} modes")

    results = {
        "timestamp": datetime.now().isoformat(),
        "eval_set_size": len(eval_set),
        "modes": {},
    }

    for mode in modes:
        logger.info(f"\n{'='*60}\nEvaluating mode: {mode}\n{'='*60}")

        mode_metrics = []
        for item in eval_set:
            try:
                metrics, chunks = run_single_eval(item, mode=mode)

                # Optional faithfulness scoring (expensive — requires LLM calls)
                if include_faithfulness and chunks:
                    answer_result = generate_answer(query=item["question"], chunks=chunks[:5])
                    context_text = "\n".join(c["text"] for c in chunks[:5])
                    faith = evaluate_faithfulness(
                        item["question"], context_text, answer_result["answer"]
                    )
                    metrics["faithfulness_score"] = faith.get("score", 0)
                    metrics["faithfulness_reasoning"] = faith.get("reasoning", "")

                mode_metrics.append(metrics)
                logger.debug(
                    f"  [{item['id']}] P@5={metrics.get('precision@5', 0):.2f} "
                    f"R@5={metrics.get('recall@5', 0):.2f} MRR={metrics['mrr']:.2f}"
                )

            except Exception as e:
                logger.error(f"  [{item['id']}] Error: {e}")
                mode_metrics.append({
                    "mode": mode,
                    "question_id": item["id"],
                    "error": str(e),
                })

        # --- Aggregate metrics ---
        valid_metrics = [m for m in mode_metrics if "error" not in m]
        if valid_metrics:
            agg = {}
            numeric_keys = [k for k in valid_metrics[0] if isinstance(valid_metrics[0][k], (int, float))]
            for key in numeric_keys:
                values = [m[key] for m in valid_metrics if key in m]
                agg[f"avg_{key}"] = round(sum(values) / len(values), 4) if values else 0

            results["modes"][mode] = {
                "aggregated": agg,
                "per_question": mode_metrics,
                "questions_evaluated": len(valid_metrics),
                "questions_failed": len(mode_metrics) - len(valid_metrics),
            }
        else:
            results["modes"][mode] = {
                "aggregated": {},
                "per_question": mode_metrics,
                "questions_evaluated": 0,
                "questions_failed": len(mode_metrics),
            }

    # --- Print comparison table ---
    logger.info("\n" + "=" * 80)
    logger.info("EVALUATION RESULTS COMPARISON")
    logger.info("=" * 80)

    header = f"{'Metric':<25}"
    for mode in modes:
        header += f"{mode:<20}"
    logger.info(header)
    logger.info("-" * 80)

    key_metrics = ["avg_precision@5", "avg_recall@5", "avg_mrr", "avg_retrieval_time_ms"]
    if include_faithfulness:
        key_metrics.append("avg_faithfulness_score")

    for metric in key_metrics:
        row = f"{metric:<25}"
        for mode in modes:
            val = results["modes"].get(mode, {}).get("aggregated", {}).get(metric, "N/A")
            if isinstance(val, float):
                row += f"{val:<20.4f}"
            else:
                row += f"{val:<20}"
        logger.info(row)

    # --- Save results ---
    if output_path is None:
        output_path = Path(__file__).parent / "eval_results.json"
    else:
        output_path = Path(output_path)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info(f"\nResults saved to: {output_path}")
    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="PIA Evaluation Harness")
    parser.add_argument(
        "--eval-set", type=str, default=None,
        help="Path to eval_set.json",
    )
    parser.add_argument(
        "--modes", type=str, nargs="+",
        default=["dense_only", "hybrid", "hybrid_reranked"],
        help="Retrieval modes to evaluate",
    )
    parser.add_argument(
        "--faithfulness", action="store_true",
        help="Include LLM-as-judge faithfulness scoring (requires API key)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output path for results JSON",
    )

    args = parser.parse_args()
    run_full_eval(
        eval_set_path=args.eval_set,
        modes=args.modes,
        include_faithfulness=args.faithfulness,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
