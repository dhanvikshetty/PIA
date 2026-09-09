"""
Fast Prep — company + JD + days-left + level → a real, day-by-day study plan.

The student gives us at least one of {company name, JD PDF}, how many days are
left, and how hard they want to go (simple | medium | hard). We answer "what do
I actually study, and when?" in four compartments:

  1. Interview questions  — the most-asked / top-occurring questions REAL students
     got at this company, pulled from the ingested interview_experience corpus,
     frequency-ranked, each with a source citation (file + page). Company-specific,
     so this is the ONLY part the LLM extracts.
  2. Core concepts        — the FULL CS syllabus (OOPS, DBMS, SQL, OS, CN, System
     Design), basics → advanced, from a curated bank. Coverage is guaranteed, not
     JD-gated. `level` decides how deep we go (simple=basics, hard=everything).
  3. DSA                  — named LeetCode problems from a curated bank (~85 across
     every major pattern), selected by `level`. simple≈20, medium≈55, hard≈85.
  4. Schedule             — built deterministically in Python: the whole concept +
     DSA load is distributed across the days, grouped so each day is coherent, with
     the last 1-3 days reserved for revision + mock (drilling the real questions).

Why banks instead of asking the LLM? Because the LLM was returning 2 problems and
a narrow, JD-shaped concept list — "for the sake of doing it". Curated banks give
full, correct coverage and guarantee live LeetCode links (slugs are vetted here,
never emitted by the model). The LLM's job shrinks to what only it can do.

No scores/ratings on the company — we recommend what to study, never rate the
employer. No aptitude, ever.
"""

import json
import time
from typing import Optional
from urllib.parse import quote_plus

try:
    import fitz
except ImportError:
    fitz = None
from loguru import logger

from backend.db.vector_store import vector_store


# ─────────────────────────────────────────────
# Level — how deep / how much to study
# ─────────────────────────────────────────────

_LEVELS = {"simple": 1, "medium": 2, "hard": 3}


def _norm_level(level: str) -> str:
    lv = (level or "").strip().lower()
    return lv if lv in _LEVELS else "medium"


def _density(days: int) -> str:
    """Timeline pressure — drives how tightly the schedule is packed."""
    if days <= 5:
        return "packed"
    if days <= 14:
        return "moderate"
    return "relaxed"


# ─────────────────────────────────────────────
# Curated CORE SUBJECTS syllabus (basics → advanced)
# Every subject is ALWAYS covered. `tier` selects depth by level:
#   simple → basic ; medium → basic+intermediate ; hard → everything
# ─────────────────────────────────────────────

_TIER = {"basic": 1, "intermediate": 2, "advanced": 3}

# subject -> one-line "why it matters"
_WHY = {
    "OOPS": "Asked in nearly every technical round; the vocabulary the rest of the interview assumes.",
    "DBMS": "Core to any backend/data role — normalization, transactions and indexing come up constantly.",
    "SQL": "You will almost certainly be asked to write queries live; joins and window functions are the classics.",
    "Operating Systems": "Process/thread, deadlock and memory questions are interviewer favourites.",
    "Computer Networks": "TCP/UDP, the handshake and HTTP/DNS show up in system-design and fundamentals rounds.",
    "System Design": "Increasingly asked even at entry level — scaling, caching and trade-off reasoning.",
}

# subject -> list of (concept, tier)
_SYLLABUS: dict[str, list[tuple[str, str]]] = {
    "OOPS": [
        ("Classes & Objects", "basic"),
        ("Encapsulation", "basic"),
        ("Abstraction", "basic"),
        ("Inheritance", "basic"),
        ("Polymorphism (compile-time vs run-time)", "basic"),
        ("Constructors & Destructors", "intermediate"),
        ("Method Overloading vs Overriding", "intermediate"),
        ("Access Modifiers (public/private/protected)", "intermediate"),
        ("Static vs Instance members", "intermediate"),
        ("Interfaces vs Abstract classes", "intermediate"),
        ("SOLID Principles", "advanced"),
        ("Composition vs Inheritance", "advanced"),
        ("Design Patterns (Singleton, Factory, Observer)", "advanced"),
        ("Virtual functions & vtables", "advanced"),
        ("Deep copy vs Shallow copy", "advanced"),
    ],
    "DBMS": [
        ("DBMS vs RDBMS", "basic"),
        ("ER Model & Diagrams", "basic"),
        ("Keys (primary, foreign, candidate, super)", "basic"),
        ("Normalization — 1NF, 2NF, 3NF", "basic"),
        ("Relational algebra basics", "basic"),
        ("BCNF", "intermediate"),
        ("Transactions & ACID properties", "intermediate"),
        ("Indexing (clustered vs non-clustered)", "intermediate"),
        ("Joins (inner, outer, self, cross)", "intermediate"),
        ("Concurrency control basics", "intermediate"),
        ("Isolation levels & read anomalies", "advanced"),
        ("Locking & Two-Phase Locking (2PL)", "advanced"),
        ("Deadlock detection & prevention", "advanced"),
        ("B-Tree vs B+ Tree indexes", "advanced"),
        ("Query optimization & execution plans", "advanced"),
        ("Sharding vs Partitioning", "advanced"),
    ],
    "SQL": [
        ("SELECT / WHERE / ORDER BY", "basic"),
        ("Aggregate functions (COUNT, SUM, AVG)", "basic"),
        ("GROUP BY vs HAVING", "basic"),
        ("INNER vs LEFT / RIGHT / FULL JOIN", "basic"),
        ("DISTINCT & LIMIT", "basic"),
        ("Subqueries & nested queries", "intermediate"),
        ("CASE expressions", "intermediate"),
        ("Set operations (UNION, INTERSECT, EXCEPT)", "intermediate"),
        ("Constraints (NOT NULL, UNIQUE, CHECK)", "intermediate"),
        ("Window functions (RANK, ROW_NUMBER, LEAD/LAG)", "advanced"),
        ("CTEs & recursive CTEs", "advanced"),
        ("Nth highest salary patterns", "advanced"),
        ("Correlated subqueries", "advanced"),
        ("Views & Stored procedures", "advanced"),
    ],
    "Operating Systems": [
        ("Process vs Thread", "basic"),
        ("Process states & PCB", "basic"),
        ("CPU scheduling (FCFS, SJF, Round Robin)", "basic"),
        ("Context switching", "basic"),
        ("Critical section problem", "intermediate"),
        ("Semaphores & Mutex", "intermediate"),
        ("Deadlock (conditions, prevention, Banker's)", "intermediate"),
        ("Producer-Consumer problem", "intermediate"),
        ("Paging & Segmentation", "advanced"),
        ("Virtual memory & Page replacement (LRU/FIFO/Optimal)", "advanced"),
        ("Thrashing", "advanced"),
        ("Disk scheduling (SCAN, C-SCAN)", "advanced"),
    ],
    "Computer Networks": [
        ("OSI vs TCP/IP model", "basic"),
        ("IP addressing & subnetting", "basic"),
        ("TCP vs UDP", "basic"),
        ("DNS", "basic"),
        ("HTTP / HTTPS", "basic"),
        ("TCP 3-way handshake", "intermediate"),
        ("Flow control vs Congestion control", "intermediate"),
        ("ARP & DHCP", "intermediate"),
        ("NAT (public vs private IP)", "intermediate"),
        ("TLS / SSL handshake", "advanced"),
        ("Sliding window protocol", "advanced"),
        ("Load balancing & CDN", "advanced"),
        ("WebSockets vs long-polling", "advanced"),
    ],
    "System Design": [
        ("Client-server model", "basic"),
        ("Latency vs Throughput", "basic"),
        ("Vertical vs Horizontal scaling", "basic"),
        ("Load balancer basics", "basic"),
        ("Caching basics (TTL, eviction)", "basic"),
        ("SQL vs NoSQL trade-offs", "intermediate"),
        ("Database replication & indexing", "intermediate"),
        ("Message queues (Kafka/RabbitMQ)", "intermediate"),
        ("Rate limiting", "intermediate"),
        ("REST API design", "intermediate"),
        ("Consistent hashing", "advanced"),
        ("CAP theorem", "advanced"),
        ("Microservices vs Monolith", "advanced"),
        ("Design a URL shortener", "advanced"),
        ("Design a news feed / rate limiter", "advanced"),
        ("Eventual consistency & Pub/Sub", "advanced"),
    ],
}

_DEFAULT_SUBJECT_ORDER = [
    "DBMS", "SQL", "OOPS", "Operating Systems", "Computer Networks", "System Design",
]


# ─────────────────────────────────────────────
# Curated DSA bank — vetted LeetCode slugs (links can't be dead)
# lvl: 1 = core (simple+), 2 = medium+, 3 = hard-only
# ─────────────────────────────────────────────

_DSA_BANK: list[tuple[str, list[tuple[str, str, str, int]]]] = [
    ("Arrays & Hashing", [
        ("Two Sum", "two-sum", "Easy", 1),
        ("Contains Duplicate", "contains-duplicate", "Easy", 1),
        ("Valid Anagram", "valid-anagram", "Easy", 1),
        ("Group Anagrams", "group-anagrams", "Medium", 1),
        ("Top K Frequent Elements", "top-k-frequent-elements", "Medium", 2),
        ("Product of Array Except Self", "product-of-array-except-self", "Medium", 2),
        ("Longest Consecutive Sequence", "longest-consecutive-sequence", "Medium", 3),
    ]),
    ("Two Pointers", [
        ("Valid Palindrome", "valid-palindrome", "Easy", 1),
        ("Two Sum II", "two-sum-ii-input-array-is-sorted", "Medium", 1),
        ("3Sum", "3sum", "Medium", 2),
        ("Container With Most Water", "container-with-most-water", "Medium", 2),
        ("Trapping Rain Water", "trapping-rain-water", "Hard", 3),
    ]),
    ("Sliding Window", [
        ("Best Time to Buy and Sell Stock", "best-time-to-buy-and-sell-stock", "Easy", 1),
        ("Longest Substring Without Repeating Characters", "longest-substring-without-repeating-characters", "Medium", 1),
        ("Longest Repeating Character Replacement", "longest-repeating-character-replacement", "Medium", 2),
        ("Minimum Window Substring", "minimum-window-substring", "Hard", 3),
    ]),
    ("Stack", [
        ("Valid Parentheses", "valid-parentheses", "Easy", 1),
        ("Min Stack", "min-stack", "Medium", 2),
        ("Daily Temperatures", "daily-temperatures", "Medium", 2),
        ("Largest Rectangle in Histogram", "largest-rectangle-in-histogram", "Hard", 3),
    ]),
    ("Binary Search", [
        ("Binary Search", "binary-search", "Easy", 1),
        ("Search a 2D Matrix", "search-a-2d-matrix", "Medium", 2),
        ("Koko Eating Bananas", "koko-eating-bananas", "Medium", 2),
        ("Find Minimum in Rotated Sorted Array", "find-minimum-in-rotated-sorted-array", "Medium", 2),
        ("Search in Rotated Sorted Array", "search-in-rotated-sorted-array", "Medium", 2),
        ("Median of Two Sorted Arrays", "median-of-two-sorted-arrays", "Hard", 3),
    ]),
    ("Linked List", [
        ("Reverse Linked List", "reverse-linked-list", "Easy", 1),
        ("Merge Two Sorted Lists", "merge-two-sorted-lists", "Easy", 1),
        ("Linked List Cycle", "linked-list-cycle", "Easy", 1),
        ("Remove Nth Node From End of List", "remove-nth-node-from-end-of-list", "Medium", 2),
        ("Reorder List", "reorder-list", "Medium", 2),
        ("LRU Cache", "lru-cache", "Medium", 2),
        ("Merge k Sorted Lists", "merge-k-sorted-lists", "Hard", 3),
    ]),
    ("Trees", [
        ("Invert Binary Tree", "invert-binary-tree", "Easy", 1),
        ("Maximum Depth of Binary Tree", "maximum-depth-of-binary-tree", "Easy", 1),
        ("Diameter of Binary Tree", "diameter-of-binary-tree", "Easy", 1),
        ("Same Tree", "same-tree", "Easy", 1),
        ("Binary Tree Level Order Traversal", "binary-tree-level-order-traversal", "Medium", 2),
        ("Validate Binary Search Tree", "validate-binary-search-tree", "Medium", 2),
        ("Lowest Common Ancestor of a BST", "lowest-common-ancestor-of-a-binary-search-tree", "Medium", 2),
        ("Kth Smallest Element in a BST", "kth-smallest-element-in-a-bst", "Medium", 2),
        ("Construct Binary Tree from Preorder and Inorder", "construct-binary-tree-from-preorder-and-inorder-traversal", "Medium", 3),
        ("Binary Tree Maximum Path Sum", "binary-tree-maximum-path-sum", "Hard", 3),
        ("Serialize and Deserialize Binary Tree", "serialize-and-deserialize-binary-tree", "Hard", 3),
    ]),
    ("Tries", [
        ("Implement Trie (Prefix Tree)", "implement-trie-prefix-tree", "Medium", 3),
        ("Word Search II", "word-search-ii", "Hard", 3),
    ]),
    ("Heap / Priority Queue", [
        ("Kth Largest Element in a Stream", "kth-largest-element-in-a-stream", "Easy", 2),
        ("Last Stone Weight", "last-stone-weight", "Easy", 2),
        ("Find Median from Data Stream", "find-median-from-data-stream", "Hard", 3),
    ]),
    ("Backtracking", [
        ("Subsets", "subsets", "Medium", 2),
        ("Combination Sum", "combination-sum", "Medium", 2),
        ("Permutations", "permutations", "Medium", 2),
        ("Word Search", "word-search", "Medium", 3),
        ("N-Queens", "n-queens", "Hard", 3),
    ]),
    ("Graphs", [
        ("Number of Islands", "number-of-islands", "Medium", 1),
        ("Clone Graph", "clone-graph", "Medium", 2),
        ("Course Schedule", "course-schedule", "Medium", 2),
        ("Rotting Oranges", "rotting-oranges", "Medium", 2),
        ("Pacific Atlantic Water Flow", "pacific-atlantic-water-flow", "Medium", 3),
        ("Word Ladder", "word-ladder", "Hard", 3),
    ]),
    ("Dynamic Programming", [
        ("Climbing Stairs", "climbing-stairs", "Easy", 1),
        ("House Robber", "house-robber", "Medium", 2),
        ("Coin Change", "coin-change", "Medium", 2),
        ("Longest Increasing Subsequence", "longest-increasing-subsequence", "Medium", 2),
        ("Longest Common Subsequence", "longest-common-subsequence", "Medium", 2),
        ("Maximum Product Subarray", "maximum-product-subarray", "Medium", 2),
        ("Unique Paths", "unique-paths", "Medium", 2),
        ("Word Break", "word-break", "Medium", 3),
        ("Edit Distance", "edit-distance", "Medium", 3),
    ]),
    ("Greedy", [
        ("Maximum Subarray", "maximum-subarray", "Medium", 1),
        ("Jump Game", "jump-game", "Medium", 2),
        ("Gas Station", "gas-station", "Medium", 3),
    ]),
    ("Intervals", [
        ("Merge Intervals", "merge-intervals", "Medium", 2),
        ("Insert Interval", "insert-interval", "Medium", 2),
        ("Non-overlapping Intervals", "non-overlapping-intervals", "Medium", 3),
    ]),
    ("Bit Manipulation", [
        ("Single Number", "single-number", "Easy", 1),
        ("Number of 1 Bits", "number-of-1-bits", "Easy", 2),
        ("Counting Bits", "counting-bits", "Easy", 2),
        ("Reverse Bits", "reverse-bits", "Easy", 3),
    ]),
    ("Math & Matrix", [
        ("Roman to Integer", "roman-to-integer", "Easy", 1),
        ("Rotate Image", "rotate-image", "Medium", 2),
        ("Spiral Matrix", "spiral-matrix", "Medium", 2),
        ("Pow(x, n)", "powx-n", "Medium", 3),
    ]),
]


# ─────────────────────────────────────────────
# PDF extraction (same approach as the resume analyzer)
# ─────────────────────────────────────────────

def _extract_text(pdf_bytes: bytes, label: str) -> str:
    try:
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [p.get_text("text").strip() for p in pdf if p.get_text("text").strip()]
        pdf.close()
        text = "\n\n".join(pages)
        logger.info(f"{label}: {len(text)} chars, {len(pages)} pages")
        return text
    except Exception as e:
        logger.error(f"PDF extract failed [{label}]: {e}")
        return ""


# ─────────────────────────────────────────────
# Corpus gathering (interview experiences + JD chunks)
# ─────────────────────────────────────────────

def _where(company: str, doc_type: str) -> dict:
    return {"$and": [{"company": company}, {"doc_type": doc_type}]}


def _gather_interview_corpus(company: str) -> tuple[str, list[dict]]:
    """All interview_experience chunks for `company`, source-marked. -> (text, sources)."""
    if not company:
        return "", []
    try:
        chunks = vector_store.get_all_chunks(where=_where(company, "interview_experience"))
    except Exception as e:
        logger.warning(f"IE corpus fetch failed for {company}: {e}")
        return "", []

    parts, sources = [], []
    for ch in chunks:
        m = ch.get("metadata", {})
        src_file = m.get("source_file", "Unknown")
        page = m.get("page_number", "?")
        parts.append(f"[Source: {src_file}, Page {page}]\n{ch['text']}")
        sources.append({"file": src_file, "page": page})
    return "\n\n---\n\n".join(parts), sources


def _gather_jd_text(company: str, jd_text: str) -> str:
    """Uploaded JD wins; otherwise fall back to the company's ingested JD chunks."""
    if jd_text.strip():
        return jd_text.strip()
    if not company:
        return ""
    try:
        chunks = vector_store.get_all_chunks(where=_where(company, "job_description"))
    except Exception as e:
        logger.warning(f"JD corpus fetch failed for {company}: {e}")
        return ""
    return "\n\n".join(ch["text"] for ch in chunks).strip()


# ─────────────────────────────────────────────
# Link builders — deterministic, never dead
# ─────────────────────────────────────────────

def _leetcode_url(slug: str) -> str:
    return f"https://leetcode.com/problems/{slug.strip().strip('/').lower()}/"


def _concept_url(name: str, bucket: str) -> str:
    """A targeted reference link that always resolves to the best explainer."""
    return f"https://www.google.com/search?q={quote_plus(f'{name} {bucket} geeksforgeeks')}"


# ─────────────────────────────────────────────
# Selection by level
# ─────────────────────────────────────────────

def _select_concepts(level: str, emphasis: list[str]) -> list[dict]:
    """
    Build the FULL leveled syllabus grouped by subject. Every subject is always
    present; `level` decides depth. Emphasised subjects come first and are marked
    high priority. Returns response-shaped bucket dicts.
    """
    max_tier = _LEVELS[level]

    # Order: emphasised subjects first (LLM), then the rest in default order.
    emph = [s for s in emphasis if s in _SYLLABUS]
    order = emph + [s for s in _DEFAULT_SUBJECT_ORDER if s not in emph]

    buckets = []
    for subject in order:
        names = [c for (c, tier) in _SYLLABUS[subject] if _TIER[tier] <= max_tier]
        if not names:
            continue
        buckets.append({
            "bucket": subject,
            "priority": "high" if subject in emph else "medium",
            "concepts": [{"name": n, "link": _concept_url(n, subject)} for n in names],
            "why": _WHY.get(subject, ""),
        })
    return buckets


def _select_dsa(level: str) -> list[dict]:
    """Curated DSA bank filtered by level. simple≈20, medium≈55, hard≈all."""
    max_lvl = _LEVELS[level]
    out = []
    for pattern, problems in _DSA_BANK:
        picked = [
            {"name": name, "difficulty": diff, "link": _leetcode_url(slug)}
            for (name, slug, diff, lvl) in problems
            if lvl <= max_lvl
        ]
        if picked:
            out.append({"pattern": pattern, "problems": picked})
    return out


# ─────────────────────────────────────────────
# Deterministic schedule builder
# ─────────────────────────────────────────────

def _chunks(lst: list, n: int) -> list[list]:
    """Split lst into n groups as evenly as possible (earlier groups get the extra)."""
    if n <= 0:
        return []
    k, m = divmod(len(lst), n)
    out, idx = [], 0
    for i in range(n):
        size = k + (1 if i < m else 0)
        out.append(lst[idx:idx + size])
        idx += size
    return out


def _dominant(labels: list[str]) -> str:
    if not labels:
        return ""
    counts = {}
    for x in labels:
        counts[x] = counts.get(x, 0) + 1
    return max(counts, key=counts.get)


def _build_schedule(
    days_left: int,
    concept_items: list[dict],   # {subject, name}
    dsa_items: list[dict],       # {name, pattern}
    questions: list[dict],
) -> list[dict]:
    """
    Distribute the whole concept + DSA load across the days, grouped so each study
    day is coherent, reserving the last 1-3 days for revision + mock.
    """
    # Reserve revision days, scaled to the timeline.
    if days_left <= 2:
        revision_days = 0
    elif days_left <= 4:
        revision_days = 1
    elif days_left <= 10:
        revision_days = 2
    else:
        revision_days = 3
    study_days = max(1, days_left - revision_days)

    concept_slices = _chunks(concept_items, study_days)
    dsa_slices = _chunks(dsa_items, study_days)

    schedule = []
    for i in range(study_days):
        cs = concept_slices[i] if i < len(concept_slices) else []
        ds = dsa_slices[i] if i < len(dsa_slices) else []
        subj = _dominant([c["subject"] for c in cs])
        patt = _dominant([d["pattern"] for d in ds])
        focus = " + ".join([x for x in (subj, patt) if x]) or "Study"
        schedule.append({
            "day": i + 1,
            "focus": focus,
            "concepts": [c["name"] for c in cs],
            "dsa": [d["name"] for d in ds],
            "revise_questions": [],
        })

    # Revision days — drill the real company questions (or generic revision).
    q_texts = [q["question"] for q in questions]
    q_slices = _chunks(q_texts, revision_days) if revision_days else []
    for j in range(revision_days):
        day = study_days + j + 1
        is_last = (j == revision_days - 1)
        revise = q_slices[j] if j < len(q_slices) else []
        if not revise:
            revise = (["Full mock interview — timed", "Re-solve every Hard problem you flagged"]
                      if is_last else
                      ["Re-derive tricky concepts from memory", "Redo Medium problems you struggled with"])
        schedule.append({
            "day": day,
            "focus": "Final Mock + Company Questions" if is_last else "Revision & Weak Spots",
            "concepts": [],
            "dsa": ["Re-solve flagged / Hard problems"],
            "revise_questions": revise,
        })

    return schedule


# ─────────────────────────────────────────────
# Prompt — company-specific extraction ONLY (fast, reliable)
# ─────────────────────────────────────────────

PROMPT = """\
You extract company-specific interview facts for an Indian placement-prep tool.
You do NOT design the study syllabus (that is handled separately). Only extract
what the sources below actually say.

- Company: {company}

=== PAST INTERVIEW EXPERIENCES (real students; may be empty) ===
{ie_corpus}

=== JOB DESCRIPTION (uploaded or from corpus; may be empty) ===
{jd_text}

Return ONLY raw JSON (no markdown, no prose) in EXACTLY this shape:
{{
  "role": "the role this targets (from JD/experiences; 'General SDE' if unknown)",
  "rounds": ["ordered interview rounds if known, e.g. 'Online Assessment','Technical','HR' — [] if unknown"],
  "emphasis": ["which of these EXACT subjects this company leans on, most first: OOPS, DBMS, SQL, Operating Systems, Computer Networks, System Design — [] if unclear"],
  "interview_questions": [
    {{
      "question": "a distinct question REAL students reported, cleaned into one clear line",
      "asked_in": 2,
      "round": "which round, or 'Technical' if unclear",
      "source_file": "the [Source: FILE ...] it came from",
      "source_page": 1
    }}
  ]
}}

RULES
- interview_questions: ONLY from the past experiences above. Merge near-duplicates and sum counts. Rank by asked_in desc. Cap 15. If experiences are empty, return [].
- emphasis: infer from the JD skills and the questions students were actually asked. Use ONLY the six exact subject names listed. Empty list if you genuinely cannot tell.
- Never invent questions. Never rate the company. If BOTH experiences and JD are empty, but the company name is provided, use your general knowledge of SDE interviews at this company to estimate the typical SDE role, rounds, and subject emphasis (and return [] for interview_questions). Only return {{"error": "Provide a company name or upload a JD PDF (at least one)."}} if BOTH the company name and JD are empty.
"""


# ─────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────

def generate_fast_prep_plan(
    company: str,
    jd_pdf_bytes: Optional[bytes],
    days_left: int,
    level: str = "medium",
) -> dict:
    """Build a day-by-day study plan. Returns FastPrepResponse-shaped dict or {'error':...}."""
    t0 = time.time()
    company = (company or "").strip()
    days_left = max(1, min(int(days_left or 1), 90))
    level = _norm_level(level)

    jd_text = _extract_text(jd_pdf_bytes, "JD") if jd_pdf_bytes else ""
    if not company and not jd_text.strip():
        return {"error": "Enter a company name or upload a JD PDF (at least one)."}

    ie_corpus, ie_sources = _gather_interview_corpus(company)
    jd_final = _gather_jd_text(company, jd_text)
    density = _density(days_left)
    has_corpus_questions = bool(ie_corpus.strip())

    # ── LLM: company-specific extraction only ──
    role, rounds, emphasis, raw_questions = "General SDE", [], [], []
    llm_error = None
    if company or jd_final:
        try:
            from backend.rag.llm_client import chat_invoke

            prompt = PROMPT.format(
                company=company or "(not provided — rely on the JD)",
                ie_corpus=ie_corpus[:8000] or "(none)",
                jd_text=jd_final[:4000] or "(none)",
            )
            logger.info(f"Fast Prep: company='{company}' days={days_left} level={level} "
                        f"ie_chars={len(ie_corpus)} jd_chars={len(jd_final)}")
            # Groq (primary) → Gemini lite (fallback).
            resp = chat_invoke(prompt, temperature=0.1)

            raw = resp.content
            if isinstance(raw, list):
                raw = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
            content = (raw or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(f"Fast Prep primary JSON parse failed: {e}. Attempting manual Gemini fallback...")
                from backend.rag.llm_client import _gemini_model
                gemini = _gemini_model(temperature=0.1)
                resp = gemini.invoke(prompt)
                raw = resp.content
                if isinstance(raw, list):
                    raw = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
                content = (raw or "").strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                data = json.loads(content)
                logger.info("Fast Prep manual Gemini fallback successfully parsed JSON.")

            if data.get("error"):
                if not company and not jd_final and not has_corpus_questions:
                    return {"error": data["error"]}
                # Otherwise, clear the error key so downstream keys parse normally
                data.pop("error", None)

            role = str(data.get("role") or "General SDE").strip() or "General SDE"
            rounds = [str(r).strip() for r in (data.get("rounds") or []) if str(r).strip()]
            emphasis = [str(e).strip() for e in (data.get("emphasis") or []) if str(e).strip()]
            raw_questions = data.get("interview_questions") or []
        except json.JSONDecodeError as e:
            llm_error = f"parse: {e}"
            logger.error(f"Fast Prep JSON parse failed: {e}")
        except Exception as e:
            msg = str(e)
            llm_error = msg
            logger.error(f"Fast Prep LLM failed: {msg}")
            try:
                from backend.rag.interview_questions import _FALLBACK_QUESTIONS
                company_lower = (company or "").lower().strip()
                if company_lower in _FALLBACK_QUESTIONS:
                    logger.info(f"Fast Prep falling back to pre-generated questions for {company}")
                    fb = _FALLBACK_QUESTIONS[company_lower]
                    raw_questions = []
                    for q in fb.get("dsa_questions", []):
                        raw_questions.append({
                            "question": q["question"],
                            "asked_in": 3,
                            "round": "Technical Coding",
                            "source_file": fb.get("sources", [{"title": "Source"}])[0]["title"],
                            "source_page": 1
                        })
                    for q in fb.get("core_questions", []):
                        raw_questions.append({
                            "question": q["question"],
                            "asked_in": 2,
                            "round": q["subject"],
                            "source_file": fb.get("sources", [{"title": "Source"}])[0]["title"],
                            "source_page": 1
                        })
                    role = "Software Engineer"
                    rounds = ["Online Assessment", "Technical Coding", "System Design"]
                    emphasis = [q["subject"] for q in fb.get("core_questions", [])]
                else:
                    raw_questions = []
                    role = "General SDE"
                    rounds = ["Technical Interview"]
                    emphasis = []
            except Exception as fe:
                logger.error(f"Failed loading fast prep fallback: {fe}")
                raw_questions = []
                role = "General SDE"
                rounds = ["Technical Interview"]
                emphasis = []
        # A failed extraction is NOT fatal — the syllabus/DSA/schedule are curated
        # and don't depend on the LLM. We just lose company-specific questions.

    # ── Interview questions: normalize, validate sources, rank, cap ──
    known_files = {s["file"] for s in ie_sources}

    def _s(v, default=""):
        return str(v).strip() if v not in (None, "") else default

    questions = []
    for item in raw_questions:
        if not isinstance(item, dict):
            continue
        q = _s(item.get("question"))
        if not q:
            continue
        try:
            asked = max(1, int(item.get("asked_in", 1)))
        except (TypeError, ValueError):
            asked = 1
        src_file = _s(item.get("source_file"))
        if src_file not in known_files:
            src_file = ie_sources[0]["file"] if ie_sources else ""
        try:
            src_page = int(item.get("source_page", 1))
        except (TypeError, ValueError):
            src_page = 1
        questions.append({
            "question": q,
            "asked_in": asked,
            "round": _s(item.get("round"), "Technical"),
            "source": {"file": src_file, "page": src_page} if src_file else None,
        })
    questions.sort(key=lambda x: x["asked_in"], reverse=True)
    questions = questions[:15]

    # ── Curated coverage (always full; scaled by level) ──
    # Map loose emphasis strings onto our canonical subjects.
    canon = {}
    for s in _SYLLABUS:
        canon[s.lower()] = s
    aliases = {"os": "Operating Systems", "cn": "Computer Networks",
               "networks": "Computer Networks", "oop": "OOPS", "oops": "OOPS",
               "dbms": "DBMS", "sql": "SQL", "system design": "System Design",
               "sd": "System Design"}
    mapped_emph = []
    for e in emphasis:
        key = e.strip().lower()
        subj = canon.get(key) or aliases.get(key)
        if subj and subj not in mapped_emph:
            mapped_emph.append(subj)

    core_concepts = _select_concepts(level, mapped_emph)
    dsa = _select_dsa(level)

    # Flat item lists for the scheduler
    concept_items = [
        {"subject": b["bucket"], "name": c["name"]}
        for b in core_concepts for c in b["concepts"]
    ]
    dsa_items = [
        {"name": p["name"], "pattern": grp["pattern"]}
        for grp in dsa for p in grp["problems"]
    ]
    schedule = _build_schedule(days_left, concept_items, dsa_items, questions)

    # ── Honest note ──
    note = ""
    if company and not has_corpus_questions:
        note = (f"No past interview write-ups are ingested for {company} yet — the "
                f"study plan below is the full curated syllabus. Company-specific "
                f"questions will appear here once experiences are added.")
    elif not company:
        note = "JD-only plan — add a company name to pull real past interview questions."
    if llm_error and (company or jd_final):
        note = (note + " ").strip() + "(Company-question extraction hit a snag this run; the study plan is unaffected.)"

    logger.info(f"Fast Prep '{company or 'JD-only'}' level={level}: "
                f"{len(concept_items)} concepts, {len(dsa_items)} DSA, "
                f"{len(questions)} questions, {len(schedule)} days in {time.time()-t0:.1f}s")

    return {
        "company": company or "Your target",
        "role": role,
        "days_left": days_left,
        "level": level,
        "density": density,
        "rounds": rounds,
        "note": note,
        "interview_questions": questions,
        "core_concepts": core_concepts,
        "dsa": dsa,
        "schedule": schedule,
    }
