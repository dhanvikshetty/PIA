"""
Structured Extractor

Uses Gemini LLM to extract structured data from interview experience
and JD chunks. Stores extracted records in the structured data store.

Guaranteed parsing accuracy using Pydantic schemas and concurrent processing.
"""

import os
import asyncio
from loguru import logger
from pydantic import BaseModel, Field

from backend.config import settings
from backend.ingestion.pdf_loader import Document
from backend.db.mongo_store import structured_store


# --- Pydantic Models for Structured Output ---

class InterviewQuestion(BaseModel):
    question: str = Field(description="The actual question text asked in the interview")
    round: str = Field(description="The round, e.g. Technical, HR, Aptitude, Coding, OA, GD. If not clear, use 'Unknown'.")
    difficulty: str = Field(description="Difficulty level: Easy, Medium, Hard. If not clear, use 'Medium'.")
    topic: str = Field(description="Topic tag, e.g. SQL, Python, DSA, DBMS, System Design, Behavioral. If not clear, use 'General'.")


class InterviewQuestionsList(BaseModel):
    questions: list[InterviewQuestion] = Field(description="List of extracted interview questions")


class CompanyMetadata(BaseModel):
    company: str = Field(description="Company name")
    package: str = Field(description="Salary/CTC if mentioned, e.g. 16 LPA. Use 'Not mentioned' if not found.")
    role: str = Field(description="Job role/position if mentioned. Use 'Not specified' if not found.")
    skills: list[str] = Field(description="List of required/tested skills mentioned")
    rounds: list[str] = Field(description="List of interview rounds mentioned")
    eligibility: str = Field(description="Eligibility criteria if mentioned. Use 'Not mentioned' if not found.")


def _get_llm():
    """Lazy-load the Gemini LLM."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        temperature=0.1,  # Low temp for extraction
    )


EXTRACT_QUESTIONS_PROMPT = """You are a structured data extractor. Given text from an interview experience document, extract all interview questions mentioned.

Only extract actual interview questions. Do not fabricate or add questions that aren't in the text.

Text:
{text}"""


EXTRACT_COMPANY_PROMPT = """You are a structured data extractor. Given text from an interview experience or job description document for company "{company}", extract company metadata.

Text:
{text}"""


def extract_company_info(chunks: list[Document], company: str) -> dict:
    """
    Extract company metadata from the first few chunks of a company's documents.
    Uses Pydantic structured output validation.
    """
    combined_text = "\n\n".join(
        c.text for c in chunks[:3]
    )

    try:
        from backend.rag.llm_client import chat_invoke
        prompt = EXTRACT_COMPANY_PROMPT.format(
            company=company, text=combined_text[:6000]
        )
        # Groq (primary) → Gemini lite (fallback), structured output validated.
        response = chat_invoke(prompt, structured_schema=CompanyMetadata, temperature=0.1)
        return response.model_dump()

    except Exception as e:
        logger.error(f"Error extracting company info for {company}: {e}")
        return {
            "company": company,
            "package": "Not mentioned",
            "role": "Not specified",
            "skills": [],
            "rounds": [],
            "eligibility": "Not mentioned",
        }


async def extract_questions_from_chunk_async(chunk: Document, sem: asyncio.Semaphore) -> list[dict]:
    """
    Extract structured questions from a single chunk asynchronously using ThreadPool executor
    to prevent blocking. Guaranteed type safety with Pydantic.
    """
    async with sem:
        loop = asyncio.get_running_loop()
        try:
            from backend.rag.llm_client import chat_invoke
            prompt = EXTRACT_QUESTIONS_PROMPT.format(text=chunk.text)

            # LangChain invoke is synchronous and network-blocking, run in executor.
            # Groq (primary) → Gemini lite (fallback); structured output validated.
            result = await loop.run_in_executor(
                None,
                lambda: chat_invoke(prompt, structured_schema=InterviewQuestionsList, temperature=0.1),
            )
            questions = [q.model_dump() for q in result.questions]

            # Enrich with metadata
            for q in questions:
                q["company"] = chunk.metadata.get("company", "Unknown")
                q["source_doc"] = chunk.metadata.get("source_file", "")
                q["source_page"] = chunk.metadata.get("page_number", 0)
                q["chunk_id"] = chunk.metadata.get("chunk_id", "")

            return questions

        except Exception as e:
            logger.error(f"Error extracting questions: {e}")
            return []


async def extract_and_store_async(chunks: list[Document]) -> dict:
    """Async engine for chunk grouping and concurrent LLM extraction."""
    if not chunks:
        return {"questions": 0, "companies": 0}

    # Group chunks by company
    company_chunks: dict[str, list[Document]] = {}
    for chunk in chunks:
        company = chunk.metadata.get("company", "Unknown")
        doc_type = chunk.metadata.get("doc_type", "")
        if doc_type in ("interview_experience", "job_description"):
            company_chunks.setdefault(company, []).append(chunk)

    total_questions = 0
    total_companies = 0

    # Limit concurrent Gemini requests to 5 to avoid API rate limiting
    sem = asyncio.Semaphore(5)

    for company, c_chunks in company_chunks.items():
        logger.info(f"Extracting structured data for: {company} ({len(c_chunks)} chunks)")

        # Extract company info
        existing = structured_store.find_one("companies", {"company": company})
        if not existing:
            company_info = extract_company_info(c_chunks, company)
            structured_store.insert("companies", company_info)
            total_companies += 1
            logger.info(f"  Stored company info: {company}")

        # Extract questions concurrently from all interview experiences
        ie_chunks = [c for c in c_chunks if c.metadata.get("doc_type") == "interview_experience"]
        if ie_chunks:
            tasks = [extract_questions_from_chunk_async(chunk, sem) for chunk in ie_chunks]
            results = await asyncio.gather(*tasks)

            # Flatten results and insert unique items
            for questions_list in results:
                for q in questions_list:
                    existing_q = structured_store.find_one(
                        "interview_questions",
                        {"question": q["question"], "company": q["company"]},
                    )
                    if not existing_q:
                        structured_store.insert("interview_questions", q)
                        total_questions += 1

        logger.info(f"  Extracted {total_questions} questions for {company}")

    return {"questions": total_questions, "companies": total_companies}


def extract_and_store(chunks: list[Document]) -> dict:
    """
    Sync entrypoint to execute the async extraction engine safely,
    compatible with both CLI and running ASGI/FastAPI event loops.
    """
    from concurrent.futures import ThreadPoolExecutor

    coro = extract_and_store_async(chunks)

    try:
        # Check if an event loop is already running
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop running, simple run
        return asyncio.run(coro)

    # A loop is running (FastAPI), launch in a separate thread to prevent blocking
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(coro))
        return future.result()

