"""
Query Router — the ONE and ONLY place the RAG pipeline runs (Path A).

This backs the "Ask Puddy" chat (POST /api/query). No other feature uses RAG:
About Company / Top Asked use live Google-Search grounding, not this module.
(Ask Puddy is currently WIP-gated in the UI; this backend route stays intact.)

Detects query intent and routes to the appropriate retrieval strategy:
- factual_lookup: hybrid retrieve → rerank → generate (the standard RAG path)
- aggregation:    MongoDB structured query first, supplemented with RAG
- comparison:     parallel retrievals across companies, merged into one context
- roadmap:        same pipeline as factual_lookup with broader context

Not all queries need full RAG — some are better served by the structured store.
"""

from typing import Optional
from loguru import logger

from backend.rag.retriever import hybrid_retrieve
from backend.rag.reranker import rerank
from backend.rag.generator import generate_answer
from backend.db.mongo_store import structured_store


# --- Intent Detection ---

INTENT_KEYWORDS = {
    "aggregation": [
        "all questions", "list all", "how many", "what questions",
        "give all", "show all", "every question", "total",
        "what topics", "which topics", "topic distribution",
        "frequency", "most common", "most asked",
    ],
    "comparison": [
        "compare", "vs", "versus", "difference between",
        "which company", "better", "both",
    ],
    "roadmap": [
        "preparation plan", "roadmap", "study plan",
        "day plan", "week plan", "how to prepare",
        "what should i study", "topics to study",
    ],
}


def detect_intent(query: str) -> str:
    """
    Detect the intent of a query based on keyword matching.

    Returns: "factual_lookup" | "aggregation" | "comparison" | "roadmap"
    """
    query_lower = query.lower()

    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in query_lower:
                return intent

    return "factual_lookup"


def extract_company_from_query(query: str) -> Optional[str]:
    """
    Try to extract a company name from the query by matching
    against known companies in the structured store.
    """
    known_companies = structured_store.distinct("companies", "company")

    # Also check ingested file names for company names
    if not known_companies:
        ingested = structured_store.find("ingested_files")
        for f in ingested:
            name = f.get("file_name", "")
            # Extract company from filename patterns
            for prefix in ["Interview_Experience_", "IE_", ""]:
                if name.startswith(prefix):
                    candidate = name[len(prefix):].replace(".pdf", "").replace("_JD", "").replace("_", " ")
                    if candidate:
                        known_companies.append(candidate)
        known_companies = list(set(known_companies))

    query_lower = query.lower()
    for company in known_companies:
        if company.lower() in query_lower:
            return company

    return None


# --- Query Handlers ---

def handle_factual_lookup(
    query: str,
    company: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> dict:
    """Standard RAG pipeline: hybrid retrieve → rerank → generate."""
    # Retrieve
    chunks = hybrid_retrieve(
        query=query,
        company=company,
        doc_type=doc_type,
    )

    # Rerank
    reranked = rerank(query=query, chunks=chunks)

    # Generate
    result = generate_answer(query=query, chunks=reranked)
    result["intent"] = "factual_lookup"
    result["company_filter"] = company
    return result


def handle_aggregation(
    query: str,
    company: Optional[str] = None,
) -> dict:
    """
    For aggregation queries, try structured store first,
    then supplement with RAG if needed.
    """
    structured_results = []

    if company:
        # Try to answer from structured data first
        questions = structured_store.find(
            "interview_questions",
            {"company": company},
        )
        if questions:
            structured_results = questions

    # Always also do RAG to get additional context
    chunks = hybrid_retrieve(
        query=query,
        company=company,
    )
    reranked = rerank(query=query, chunks=chunks)

    # If we have structured data, add it to the context
    if structured_results:
        # Create a summary of structured data to prepend
        summary_lines = [f"Structured data found for {company}:"]
        for q in structured_results[:20]:  # Limit to 20 for context window
            summary_lines.append(
                f"- [{q.get('round', 'Unknown')}] [{q.get('difficulty', '?')}] "
                f"[{q.get('topic', '?')}] {q.get('question', 'N/A')}"
            )
        structured_context = {
            "id": "structured_data_summary",
            "text": "\n".join(summary_lines),
            "metadata": {
                "source_file": "Structured Database",
                "page_number": 0,
                "company": company or "All",
                "doc_type": "structured_data",
            },
        }
        reranked.insert(0, structured_context)

    result = generate_answer(query=query, chunks=reranked)
    result["intent"] = "aggregation"
    result["company_filter"] = company
    result["structured_results_count"] = len(structured_results)
    return result


def handle_comparison(
    query: str,
    companies: list[str] = None,
) -> dict:
    """
    For comparison queries, retrieve from multiple companies
    and merge context.
    """
    if not companies:
        # Try to detect companies from query
        known = structured_store.distinct("companies", "company")
        companies = [c for c in known if c.lower() in query.lower()]

    all_chunks = []
    for company in companies:
        chunks = hybrid_retrieve(
            query=query,
            company=company,
            top_k=10,  # Fewer per company to fit context
        )
        all_chunks.extend(chunks)

    # Rerank the combined set
    reranked = rerank(query=query, chunks=all_chunks)

    result = generate_answer(query=query, chunks=reranked)
    result["intent"] = "comparison"
    result["companies_compared"] = companies
    return result


# --- Main Router ---

def route_query(
    query: str,
    company: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> dict:
    """
    Main entry point: detect intent, extract company if not provided,
    and route to the appropriate handler.

    Args:
        query: User's question
        company: Optional company filter (auto-detected if not provided)
        doc_type: Optional doc type filter

    Returns:
        Dict with answer, sources, and routing metadata
    """
    # Auto-detect company if not explicitly provided
    if not company:
        company = extract_company_from_query(query)

    # Detect intent
    intent = detect_intent(query)
    logger.info(f"Query routed | intent={intent} | company={company} | query='{query[:60]}...'")

    # Route to handler
    if intent == "aggregation":
        return handle_aggregation(query, company)
    elif intent == "comparison":
        return handle_comparison(query)
    elif intent == "roadmap":
        # Roadmap uses the same pipeline but with a broader context
        return handle_factual_lookup(query, company, doc_type)
    else:
        return handle_factual_lookup(query, company, doc_type)
