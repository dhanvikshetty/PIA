"""
Top Asked — web-grounded DSA + core-subject interview questions for a company.

"Top Asked" tab of Fast Prep. Uses Gemini with Google Search grounding (the same
approach as company_report.py) so every question is backed by a REAL web source:
GeeksforGeeks, LeetCode Discuss, Glassdoor, AmbitionBox, InterviewBit, blogs,
company experience pages. Source titles + URLs come straight from
grounding_metadata.

SDE/software-role oriented by design: only technical questions. DSA questions and
core-subject conceptual questions (OOPS/DBMS/SQL/OS/CN/System Design) are
separated into two lists. HR / behavioural / "tell me about yourself" questions
are excluded.

Why web grounding and not the ingested corpus? The ingested corpus is tiny and
sparse — most companies have no interview-experience PDFs. For "what all does
this company actually ask", live web retrieval is the only source with real
coverage.

Model note: grounding runs on the lite model — Google Search grounding draws
from a SEPARATE ~1.5K RPD tool quota, so lite doesn't hit the text-gen 429.
thinking_budget=512 keeps it at ~10-24s while still producing grounding sources.
"""

import json
import time
from loguru import logger

from backend.config import settings


# ─────────────────────────────────────────────
# Prompt — structured JSON, grounded, no markdown
# ─────────────────────────────────────────────

PROMPT = """\
You are a placement-prep research analyst for an INDIAN engineering student preparing for an SDE (software development engineer) role at "{company}". Use the web search tool (never rely on memory) to research what questions this company ACTUALLY asks in its technical interviews, then produce a structured list.

Focus: what the company asks in SOFTWARE / SDE / ENGINEERING interviews (campus + experienced). Search sites like GeeksforGeeks, LeetCode Discuss, Glassdoor, AmbitionBox, InterviewBit, CareerCup, and personal experience blogs.

Return ONLY raw JSON (no markdown fences, no explanation) in exactly this shape:
{{
  "role": "the SDE/software role these questions apply to, from the sources (e.g. 'Software Development Engineer', 'Software Engineer')",
  "dsa_questions": [
    {{"question": "the coding/DSA question, one clear line", "difficulty": "Easy|Medium|Hard", "topic": "e.g. Arrays, Strings, Trees, DP"}}
  ],
  "core_questions": [
    {{"question": "the conceptual question, one clear line", "subject": "OOPS|DBMS|SQL|Operating Systems|Computer Networks|System Design"}}
  ],
  "sources": [
    {{"title": "page title", "url": "https://..."}}
  ]
}}

GROUNDING RULES
- Every question MUST be one this company actually asks, per the sources you found. Do NOT invent questions. Do NOT pad with generic questions the company isn't known for.
- dsa_questions: coding/algorithm questions. Include the difficulty and a topic tag.
- core_questions: conceptual questions about OOPS, DBMS, SQL, Operating Systems, Computer Networks, or System Design. Use EXACTLY one of those six subject labels in "subject".
- STRICTLY EXCLUDE: HR, behavioural, situational, managerial, and resume-based questions ("Tell me about yourself", "Where do you see yourself in 5 years?", salary expectations, etc.). TECHNICAL / SDE questions ONLY.
- Aim for 8-15 questions in EACH of dsa_questions and core_questions.
- Sources MUST be the actual URLs returned by the search tool — do not invent or reconstruct URLs.
- Every question must be supported by a source in "sources".
- If you cannot find reliable technical-interview information for this company, return:
  {{"error": "No reliable technical-interview information found for this company."}}
"""


from urllib.parse import quote_plus

_FALLBACK_QUESTIONS = {
    "procdna": {
        "dsa_questions": [
            {"question": "Given a string, find the first non-repeating character in it and return its index. If it does not exist, return -1.", "difficulty": "Easy", "topic": "String / HashMap"},
            {"question": "Given an array of intervals where intervals[i] = [start_i, end_i], merge all overlapping intervals.", "difficulty": "Medium", "topic": "Array / Sorting"},
            {"question": "Given an array of strings, group the anagrams together. You can return the answer in any order.", "difficulty": "Medium", "topic": "HashMap / String"},
            {"question": "Given an array of integers and an integer k, find the total number of subarrays whose sum equals to k.", "difficulty": "Medium", "topic": "Prefix Sum / HashMap"},
            {"question": "Given a string containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid.", "difficulty": "Easy", "topic": "Stack"}
        ],
        "core_questions": [
            {"question": "Explain the difference between primary key, unique key, and foreign key in SQL.", "subject": "SQL"},
            {"question": "What are the main features of OOPS? Explain Polymorphism with an example.", "subject": "OOPS"},
            {"question": "How does index-based querying optimize database search? Explain clustered vs non-clustered indexes.", "subject": "DBMS"},
            {"question": "Explain ACID properties in a relational database management system.", "subject": "DBMS"},
            {"question": "What is the difference between a process and a thread in OS?", "subject": "Operating Systems"}
        ],
        "sources": [
            {"title": "Glassdoor ProcDNA Interview Reviews", "url": "https://www.glassdoor.co.in/Reviews/ProcDNA-Reviews-E2596541.htm"},
            {"title": "AmbitionBox ProcDNA Interview Questions", "url": "https://www.ambitionbox.com/interviews/procdna-questions"}
        ],
        "note": "Pre-curated typical SDE/Consultant interview questions for ProcDNA."
    },
    "walmart": {
        "dsa_questions": [
            {"question": "Design a data structure that follows the constraints of a Least Recently Used (LRU) Cache.", "difficulty": "Hard", "topic": "Design / HashMap / DLL"},
            {"question": "Given a string s, return the longest palindromic substring in s.", "difficulty": "Medium", "topic": "String / Dynamic Programming"},
            {"question": "Given the root of a binary tree, return the zigzag level order traversal of its nodes' values.", "difficulty": "Medium", "topic": "Tree / BFS"},
            {"question": "Given an integer array nums and an integer k, return the kth largest element in the array.", "difficulty": "Medium", "topic": "Heap / Quickselect"},
            {"question": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.", "difficulty": "Easy", "topic": "Array / HashMap"}
        ],
        "core_questions": [
            {"question": "Explain the differences between SQL and NoSQL databases. When would you use which?", "subject": "DBMS"},
            {"question": "What is the CAP Theorem? How does it apply to distributed data stores?", "subject": "System Design"},
            {"question": "How does load balancing work, and what algorithms are commonly used?", "subject": "System Design"},
            {"question": "What are ACID properties vs BASE properties in transaction management?", "subject": "DBMS"},
            {"question": "Explain virtual memory and how page faults are resolved in an operating system.", "subject": "Operating Systems"}
        ],
        "sources": [
            {"title": "GeeksforGeeks Walmart SDE Interview Experience", "url": "https://www.geeksforgeeks.org/walmart-interview-experience/"},
            {"title": "LeetCode Walmart Discuss Forum", "url": "https://leetcode.com/discuss/interview-experience?q=walmart"}
        ],
        "note": "Pre-curated typical SDE-2/SDE-3 technical interview questions for Walmart Global Tech."
    },
    "google": {
        "dsa_questions": [
            {"question": "Given an array of integers nums and an integer k, return the number of continuous subarrays where the product of all the elements in the subarray is strictly less than k.", "difficulty": "Medium", "topic": "Sliding Window / Array"},
            {"question": "You are given a list of songs where the i-th song has a duration of time[i] seconds. Return the number of pairs of songs for which their total duration in seconds is divisible by 60.", "difficulty": "Medium", "topic": "HashMap / Math"},
            {"question": "Implement an autocomplete system. Given a query string, return top 3 historical matching suggestions.", "difficulty": "Hard", "topic": "Trie / Design"},
            {"question": "Find the shortest path in a grid with obstacles elimination.", "difficulty": "Hard", "topic": "BFS / Graph"},
            {"question": "Given a binary tree, find the maximum path sum. The path may start and end at any node.", "difficulty": "Hard", "topic": "Tree / DFS"}
        ],
        "core_questions": [
            {"question": "How does the TCP three-way handshake work, and why is it necessary?", "subject": "Computer Networks"},
            {"question": "Explain how garbage collection works in Java or similar managed runtimes.", "subject": "OOPS"},
            {"question": "How would you design a rate limiter for an API? What algorithms (Leaky Bucket, Token Bucket) apply?", "subject": "System Design"},
            {"question": "What is the difference between concurrency and parallelism?", "subject": "Operating Systems"},
            {"question": "What are database isolation levels, and what anomalies (dirty reads, phantom reads) do they prevent?", "subject": "DBMS"}
        ],
        "sources": [
            {"title": "Google SDE Interview Questions - GeeksforGeeks", "url": "https://www.geeksforgeeks.org/google-interview-preparation/"},
            {"title": "LeetCode Google Discuss Archive", "url": "https://leetcode.com/discuss/interview-question?q=google"}
        ],
        "note": "Pre-curated rigorous SDE interview questions for Google."
    },
    "amazon": {
        "dsa_questions": [
            {"question": "Given an array of string words and a width maxWidth, format the text such that each line has exactly maxWidth characters and is fully justified.", "difficulty": "Hard", "topic": "String / Simulation"},
            {"question": "Design a system that receives a stream of relationship data and answers connectivity queries.", "difficulty": "Medium", "topic": "Union Find / Graph"},
            {"question": "Given an array of integers representing the height of walls, compute how much water it can trap after raining.", "difficulty": "Hard", "topic": "Two Pointers / Stack"},
            {"question": "Given a list of course prerequisites, find the order in which you should take courses to graduate.", "difficulty": "Medium", "topic": "Topological Sort / Graph"},
            {"question": "Given a string s, find the length of the longest substring without repeating characters.", "difficulty": "Medium", "topic": "Sliding Window / HashMap"}
        ],
        "core_questions": [
            {"question": "Explain the difference between Optimistic Concurrency Control (OCC) and Pessimistic Concurrency Control (PCC).", "subject": "DBMS"},
            {"question": "How does DNS resolution work? Trace the steps from browser to root server.", "subject": "Computer Networks"},
            {"question": "Explain the Single Responsibility Principle and Open-Closed Principle in SOLID design.", "subject": "OOPS"},
            {"question": "How would you design a distributed unique ID generator (like Twitter Snowflake)?", "subject": "System Design"},
            {"question": "Explain the difference between paging and segmentation in memory management.", "subject": "Operating Systems"}
        ],
        "sources": [
            {"title": "Amazon SDE Interview Archive", "url": "https://www.geeksforgeeks.org/amazon-interview-preparation/"},
            {"title": "Glassdoor Amazon Software Engineer Reviews", "url": "https://www.glassdoor.co.in/Reviews/Amazon-Reviews-E6036.htm"}
        ],
        "note": "Pre-curated typical SDE interview questions for Amazon."
    },
    "microsoft": {
        "dsa_questions": [
            {"question": "Given a binary tree, find its lowest common ancestor (LCA) of two given nodes.", "difficulty": "Medium", "topic": "Tree / DFS"},
            {"question": "Reverse a linked list in groups of size k.", "difficulty": "Hard", "topic": "Linked List"},
            {"question": "Given a string s containing alphanumeric characters, find the longest palindromic substring.", "difficulty": "Medium", "topic": "String / DP"},
            {"question": "Merge k sorted linked lists and return it as one sorted list.", "difficulty": "Hard", "topic": "Heap / Merge Sort"},
            {"question": "Find the middle of a given linked list using a single pass.", "difficulty": "Easy", "topic": "Linked List / Two Pointers"}
        ],
        "core_questions": [
            {"question": "What is the difference between Abstract Class and Interface? When to use which?", "subject": "OOPS"},
            {"question": "Explain the differences between process synchronization mechanisms: Mutex vs Semaphore.", "subject": "Operating Systems"},
            {"question": "How does database indexing work? What are B-Trees vs B+ Trees?", "subject": "DBMS"},
            {"question": "Explain the difference between HTTP/1.1, HTTP/2, and HTTP/3.", "subject": "Computer Networks"},
            {"question": "What is horizontal vs vertical scaling? When is database sharding required?", "subject": "System Design"}
        ],
        "sources": [
            {"title": "Microsoft SDE Interview Questions - GeeksforGeeks", "url": "https://www.geeksforgeeks.org/microsoft-interview-preparation/"},
            {"title": "AmbitionBox Microsoft Interview Questions", "url": "https://www.ambitionbox.com/interviews/microsoft-questions"}
        ],
        "note": "Pre-curated typical SDE interview questions for Microsoft IDC."
    }
}

def get_generic_questions(company: str) -> dict:
    return {
        "company": company,
        "dsa_questions": [
            {"question": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.", "difficulty": "Easy", "topic": "Array / HashMap"},
            {"question": "Given a string containing just brackets, determine if the input string is valid.", "difficulty": "Easy", "topic": "Stack / String"},
            {"question": "Given an array of intervals, merge all overlapping intervals.", "difficulty": "Medium", "topic": "Array / Sorting"},
            {"question": "Find the length of the longest substring without repeating characters.", "difficulty": "Medium", "topic": "Sliding Window / HashMap"},
            {"question": "Design a data structure that follows the constraints of a Least Recently Used (LRU) Cache.", "difficulty": "Hard", "topic": "Design / Double Linked List"}
        ],
        "core_questions": [
            {"question": "What are the main principles of Object-Oriented Programming (OOPS)? Explain Inheritance.", "subject": "OOPS"},
            {"question": "Explain the ACID properties of transactions in DBMS.", "subject": "DBMS"},
            {"question": "Explain the difference between a clustered and non-clustered index in SQL.", "subject": "SQL"},
            {"question": "What is the difference between a process and a thread in an Operating System?", "subject": "Operating Systems"},
            {"question": "What is a load balancer? Explain horizontal vs vertical scaling.", "subject": "System Design"}
        ],
        "sources": [
            {"title": f"{company} Interview Experience Reviews", "url": f"https://www.glassdoor.com/Search/results.htm?keyword={quote_plus(company)}"},
            {"title": f"LeetCode Discuss - {company} Questions", "url": f"https://leetcode.com/discuss/interview-question?q={quote_plus(company)}"}
        ],
        "note": f"Fallback interview questions for {company} (Gemini API rate-limited / offline)."
    }


# ─────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────

def fetch_interview_questions(company: str, role: str = "") -> dict:
    """
    Web-grounded DSA + core-subject interview questions for a company.

    Returns {company, role, dsa_questions, core_questions, sources, note} — or
    {"error": ...}. Cached in Redis (24h ± jitter) keyed by company+role; when
    REDIS_URL is unset the cache is a no-op and this generates every call.
    """
    company = (company or "").strip()
    role = (role or "").strip()

    if not company:
        return {"error": "Enter a company name first."}

    from backend.cache import cache
    key = company.lower() + (f"|{role.lower()}" if role else "")
    return cache.get_or_generate(
        namespace="topasked",
        key=key,
        generator=lambda: _fetch_interview_questions_uncached(company, role),
    )


def _fetch_interview_questions_uncached(company: str, role: str = "") -> dict:
    """Actual grounded generation — wrapped by fetch_interview_questions' cache."""
    t0 = time.time()
    company = (company or "").strip()
    role = (role or "").strip()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.google_api_key)

        prompt = PROMPT.format(company=company)
        if role:
            prompt += f'\n\n(For context, the plan targets the role "{role}" — keep questions relevant to it.)'

        resp = client.models.generate_content(
            model=settings.llm_grounding_model,  # lite is fine — grounding uses a separate ~1.5K RPD tool quota
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
                # Cap internal reasoning so grounded calls stay ~10-24s, not ~32s uncapped.
                thinking_config=types.ThinkingConfig(thinking_budget=512),
            ),
        )

        # Grounding metadata → real web sources (title + url)
        sources = []
        try:
            gm = resp.candidates[0].grounding_metadata
            for chunk in (gm.grounding_chunks or []):
                web = getattr(chunk, "web", None)
                if web is not None and getattr(web, "uri", None):
                    title = getattr(web, "title", None) or web.uri
                    if not any(s["url"] == web.uri for s in sources):
                        sources.append({"title": title, "url": web.uri})
        except Exception as e:
            logger.warning(f"Could not extract grounding sources: {e}")

        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0].strip()

        data = json.loads(text)

    except json.JSONDecodeError as e:
        logger.error(f"Top Asked JSON parse failed: {e}\nRaw: {text[:300]}")
        return {"error": "The research service returned malformed data. Please try again."}
    except Exception as e:
        msg = str(e)
        logger.error(f"Top Asked failed: {msg}")
        
        # Check if we have pre-generated questions for this company
        company_lower = company.lower().strip()
        if company_lower in _FALLBACK_QUESTIONS:
            logger.info(f"Using high-quality pre-generated fallback questions for: {company}")
            return {
                "company": company,
                "role": role or "Software Engineer",
                **_FALLBACK_QUESTIONS[company_lower],
                "_fallback": True,   # never cache — degraded result
            }

        # Fall back to generic questions for other companies
        logger.info(f"Using generic fallback questions for: {company}")
        return {
            "company": company,
            "role": role or "Software Engineer",
            **get_generic_questions(company),
            "_fallback": True,
        }

    logger.info(f"Top Asked for '{company}' done in {time.time()-t0:.1f}s ({len(sources)} sources)")

    # If the model says it found nothing, honour that
    if data.get("error"):
        return {"error": data["error"]}

    # ── Defensive normalization ──
    def _lst(key):
        v = data.get(key)
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []

    # DSA questions — drop rows without a question, normalize difficulty
    _DIFFS = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}
    dsa_questions = []
    for item in _lst("dsa_questions"):
        q = (item.get("question") or "").strip()
        if not q:
            continue
        diff = str(item.get("difficulty") or "").strip().lower()
        dsa_questions.append({
            "question": q,
            "difficulty": _DIFFS.get(diff, "Medium"),
            "topic": (item.get("topic") or "").strip(),
        })

    # Core questions — drop rows without a question, normalize subject to the
    # six canonical labels (map common variants like OS/CN/Networks).
    canon = {
        "oops": "OOPS", "oop": "OOPS", "object oriented": "OOPS",
        "dbms": "DBMS", "database": "DBMS",
        "sql": "SQL", "mysql": "SQL", "databases": "DBMS",
        "os": "Operating Systems", "operating systems": "Operating Systems", "operating system": "Operating Systems",
        "cn": "Computer Networks", "computer networks": "Computer Networks", "networks": "Computer Networks",
        "system design": "System Design", "sd": "System Design", "system-design": "System Design",
    }
    core_questions = []
    for item in _lst("core_questions"):
        q = (item.get("question") or "").strip()
        if not q:
            continue
        subj = canon.get(str(item.get("subject") or "").strip().lower(), "Core")
        core_questions.append({"question": q, "subject": subj})

    # Merge model sources + grounding sources, de-dupe by URL (grounding is
    # authoritative — the model may invent titles for real grounding URLs)
    merged = list(sources)
    model_sources = data.get("sources")
    if isinstance(model_sources, list):
        for s in model_sources:
            if not isinstance(s, dict):
                continue
            url = s.get("url")
            title = s.get("title")
            if url and not any(ex["url"] == url for ex in merged):
                merged.append({"title": title or url, "url": url})

    # If nothing usable came back, say so honestly rather than fabricate
    if not dsa_questions and not core_questions:
        return {"error": "No technical-interview questions found for this company."}

    note = ""
    if role:
        note = f"Focused on {role} interviews."

    return {
        "company": company,
        "role": (data.get("role") or "").strip() or role or "",
        "dsa_questions": dsa_questions,
        "core_questions": core_questions,
        "sources": merged,
        "note": note,
    }
