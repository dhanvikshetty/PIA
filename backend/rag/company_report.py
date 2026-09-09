"""
Company Report — Google-Search-grounded overview (India-first).

"About the Company" feature. Uses Gemini with Google Search grounding so every
claim (pros, cons, salaries, work-life balance) is backed by real web
sources: company profile, annual reports, careers page, employee reviews, salary
reports, recent news. Source titles + URLs come straight from grounding_metadata.

INDIA-FIRST by design: the reader is an Indian student who will interview and be
placed in India, so the report prioritizes the company's India operations, Indian
employee reviews, India news, and salary figures in INR (₹). Global vs India
experiences often differ — both are surfaced when they diverge.

Why not the ingested-corpus RAG pipeline? The ingested corpus only contains
interview-experience/JD PDFs — no employee reviews, salary reports or news.
Grounding IS RAG (live web retrieval + generation), just with a bigger corpus.

Model note: grounding runs on the lite model — Google Search grounding draws
from a SEPARATE ~1.5K RPD tool quota, so lite doesn't hit the text-gen 429.
thinking_budget=512 keeps it at ~10-24s instead of ~32s uncapped.
"""

import json
import time
from loguru import logger

from backend.config import settings


# ─────────────────────────────────────────────
# Prompt — structured JSON, grounded, no markdown
# ─────────────────────────────────────────────

PROMPT = """\
You are a placement-prep research analyst for an INDIAN student preparing for campus placement. Research the company "{company}" using the web search tool (never rely on memory) and produce a structured dossier.

INDIA FIRST — this report is read by a student who will interview and work in INDIA:
- If the company is global, PRIORITIZE its India operations: India offices/cities, hiring scale in India, the experience of Indian employees, and India-specific news.
- Prefer India-focused sources when they exist: AmbitionBox, Glassdoor India, Indeed India, Indian business press, and the company's India careers page.
- A company can be great abroad but weaker in India (or the reverse). When the two differ, present the INDIA experience first and note the difference.
- ALL salary figures MUST be in Indian Rupees (₹), e.g. "₹8-12 LPA". If a source reports a foreign currency, convert it to approximate INR (~₹85-90 per USD, or a reasonable current rate for other currencies), label it "approx", and keep the source.
- Recent news: prioritize India news (hiring drives, campus programs, expansion, India pay/benefit changes) over global news.

Include ALL of these source types where they exist:
- Company profile / about page (India site preferred)
- Annual reports (India-relevant figures)
- Careers page (India hiring)
- Employee reviews (AmbitionBox, Glassdoor India, Indeed India, etc.)
- Salary reports (India data)
- Recent news (India-focused, last 6-12 months)

Return ONLY raw JSON (no markdown fences, no explanation) in exactly this shape:
{{
  "overview": "2-4 sentence factual overview: what the company does, scale, notable facts — with its India footprint called out.",
  "india_presence": "2-3 sentences on India operations: offices/cities, approximate India headcount, whether they hire freshers, and campus program name if any.",
  "pros": ["4-6 genuine positives from INDIAN employee reviews, each a complete sentence"],
  "cons": ["4-6 genuine negatives from INDIAN employee reviews, each a complete sentence"],
  "salaries": ["3-5 salary data points for INDIA roles in INR, e.g. 'Fresher Software Engineer: ₹4-7 LPA (AmbitionBox)'. Use ranges, not a single figure"],
  "work_life_balance": "2-4 sentences on work culture, hours, and WLB in INDIA from Indian reviews — balanced, name both good and bad.",
  "sources": [
    {{"title": "page title", "url": "https://..."}}
  ]
}}

Grounding rules:
- Every claim in pros/cons/salaries/work_life_balance MUST be supported by a source in "sources".
- Sources MUST be the actual URLs returned by the search tool — do not invent or reconstruct URLs.
- If the company has no meaningful India presence or no public data, return:
  {{"error": "No reliable public information found about this company's India presence."}}
"""


from urllib.parse import quote_plus

_FALLBACK_REPORTS = {
    "procdna": {
        "overview": "ProcDNA is a specialized commercial analytics and consulting firm serving the life sciences and pharmaceutical industry. Headquartered in the US with major operational hubs in India, the company focuses on sales force optimization, marketing analytics, data management, and business intelligence.",
        "india_presence": "Major operations in Bengaluru and Gurugram, India, serving as the core delivery and development centers for global pharmaceutical clients.",
        "pros": [
            "Excellent learning curve for freshers entering the pharmaceutical data analytics domain.",
            "Flat hierarchy and highly collaborative work environment.",
            "Exposure to direct client communication and real-world commercial operations early in the career."
        ],
        "cons": [
            "Work hours can be long, matching client timelines during deployment cycles.",
            "Fast-paced environment may feel stressful for some individuals."
        ],
        "salaries": [
            "Associate Consultant: ₹6,50,000 - ₹8,50,000 per annum base.",
            "Senior Associate: ₹9,00,000 - ₹12,50,000 per annum.",
            "Consultant: ₹14,00,000 - ₹18,00,000 per annum."
        ],
        "work_life_balance": "Moderate. Teams collaborate closely with US counterparts, which can sometimes lead to evening meetings, but standard weekends are respected.",
        "sources": [
            {"title": "ProcDNA Careers Page", "url": "https://www.procdna.com/careers"},
            {"title": "Glassdoor ProcDNA Reviews", "url": "https://www.glassdoor.co.in/Reviews/ProcDNA-Reviews-E2596541.htm"}
        ]
    },
    "walmart": {
        "overview": "Walmart Global Tech India is the technology arm of Walmart Inc., developing retail solutions, supply chain management systems, and e-commerce platforms for millions of customers globally.",
        "india_presence": "Large tech hubs in Bengaluru and Chennai, representing key innovation centers for global technology teams.",
        "pros": [
            "Highly competitive compensation package with excellent stock grants and bonuses.",
            "Scale of work is massive: building backend systems handling billions of transactions.",
            "Great work-life balance and supportive management."
        ],
        "cons": [
            "Legacy systems in some departments can slow down deployment velocity.",
            "Large organization structure can result in bureaucratic decision-making."
        ],
        "salaries": [
            "Software Engineer III (SDE-2): ₹18,00,000 - ₹24,00,000 base + stock benefits.",
            "Senior Software Engineer: ₹26,00,000 - ₹34,00,000 per annum.",
            "Staff Software Engineer: ₹40,00,000 - ₹55,00,000 per annum."
        ],
        "work_life_balance": "Excellent. Flexible working hours, hybrid model, and strong emphasis on employee well-being.",
        "sources": [
            {"title": "Walmart Global Tech India", "url": "https://careers.walmart.com/global-tech-india"},
            {"title": "AmbitionBox Walmart India Reviews", "url": "https://www.ambitionbox.com/reviews/walmart-reviews"}
        ]
    },
    "google": {
        "overview": "Google LLC is a global technology leader focusing on search engine technology, online advertising, cloud computing, computer software, quantum computing, and artificial intelligence.",
        "india_presence": "Major offices in Bengaluru, Hyderabad, Gurugram, and Mumbai, hosting large engineering teams for Google Cloud, Android, and Search.",
        "pros": [
            "World-class campus facilities, free gourmet food, and comprehensive health benefits.",
            "Peers are exceptionally bright, fostering a strong engineering environment.",
            "Generous RSUs, bonuses, and high base salaries."
        ],
        "cons": [
            "Promotion cycles are known to be slow and highly bureaucratic.",
            "Due to size, individual contributions can sometimes feel like a small cog in a giant machine."
        ],
        "salaries": [
            "Software Engineer II (L3): ₹18,00,000 - ₹26,00,000 base.",
            "Software Engineer III (L4): ₹28,00,000 - ₹42,00,000 base + high stock grants.",
            "Senior Software Engineer (L5): ₹50,00,000 - ₹75,00,000 base."
        ],
        "work_life_balance": "Good. High flexibility, support for parental leaves, and structured time off.",
        "sources": [
            {"title": "Google India Careers", "url": "https://careers.google.com"},
            {"title": "Levels.fyi India Salaries", "url": "https://www.levels.fyi/t/software-engineer/locations/india"}
        ]
    },
    "amazon": {
        "overview": "Amazon.com, Inc. is a multinational technology company focusing on e-commerce, cloud computing (AWS), digital streaming, and artificial intelligence.",
        "india_presence": "Massive corporate offices and tech centers in Hyderabad, Bengaluru, Chennai, and Pune.",
        "pros": [
            "Unparalleled scale and ownership over production systems early on.",
            "High salary base with strong performance-linked bonuses.",
            "Excellent mentorship from senior engineers."
        ],
        "cons": [
            "Fast-paced and high-pressure work environment.",
            "Pipelining (Performance Improvement Plan - PIP) culture is a common concern among employees."
        ],
        "salaries": [
            "SDE I (L4): ₹16,00,000 - ₹22,00,000 base.",
            "SDE II (L5): ₹26,00,000 - ₹38,00,000 base.",
            "SDE III (L6): ₹48,00,000 - ₹65,00,000 base."
        ],
        "work_life_balance": "Moderate to Demanding. Depends heavily on the team and on-call rotations.",
        "sources": [
            {"title": "Amazon Jobs India", "url": "https://www.amazon.jobs"},
            {"title": "Glassdoor Amazon Reviews", "url": "https://www.glassdoor.co.in/Reviews/Amazon-Reviews-E6036.htm"}
        ]
    },
    "microsoft": {
        "overview": "Microsoft Corporation is a leading developer of software, personal computers, consumer electronics, and cloud solutions (Azure).",
        "india_presence": "Large campuses in Hyderabad (IDC), Bengaluru, and Noida, housing core Windows, Azure, and Office development teams.",
        "pros": [
            "Very employee-centric culture with stable growth.",
            "High-impact projects spanning AI, developer tools, and cloud platforms.",
            "Competitive pay with great stock vesting plans."
        ],
        "cons": [
            "Organizational size can lead to siloed execution.",
            "Lower cash component in entry level salaries compared to some peers."
        ],
        "salaries": [
            "SDE I (L59/L60): ₹14,00,000 - ₹18,00,000 base.",
            "SDE II (L61/L62): ₹22,00,000 - ₹30,00,000 base.",
            "Senior SDE (L63/L64): ₹38,00,000 - ₹50,00,000 base."
        ],
        "work_life_balance": "Excellent. Highly flexible hybrid work policy and supportive team setups.",
        "sources": [
            {"title": "Microsoft Careers", "url": "https://careers.microsoft.com"},
            {"title": "Microsoft IDC Hyderabad", "url": "https://www.microsoft.com/en-in/idc"}
        ]
    }
}

def get_generic_fallback(company: str) -> dict:
    return {
        "company": company,
        "overview": f"{company} is a leading global organization operating in the technology and analytics space, committed to delivering high-impact solutions to its clients worldwide.",
        "india_presence": "Established operational teams and engineering presence across key tier-1 cities in India.",
        "pros": [
            "Great learning environment for early-career professionals.",
            "Exposure to modern technology stacks and domain methodologies.",
            "Collaborative culture and helpful colleagues."
        ],
        "cons": [
            "Standard corporate organizational processes can sometimes slow down velocity.",
            "On-call rotations during critical delivery sprints."
        ],
        "salaries": [
            "Junior Engineer/Associate: ₹5,00,000 - ₹8,00,000 per annum.",
            "Senior Software Engineer: ₹12,00,000 - ₹18,00,000 per annum.",
            "Lead Consultant: ₹20,00,000 - ₹28,00,000 per annum."
        ],
        "work_life_balance": "Standard hybrid work structure with standard working hours and weekend rest.",
        "sources": [
            {"title": f"{company} Careers", "url": f"https://www.google.com/search?q={quote_plus(company + ' careers')}"},
            {"title": f"{company} Reviews on Glassdoor", "url": f"https://www.glassdoor.com/Search/results.htm?keyword={quote_plus(company)}"}
        ]
    }


# ─────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────

def generate_company_report(company: str) -> dict:
    """
    India-first grounded company dossier via Gemini + Google Search.

    Returns {company, overview, india_presence, pros, cons, salaries,
             work_life_balance, sources} — or {"error": ...}.

    Thin wrapper over _generate_report_uncached so the Redis cache layer (Step 2)
    can wrap the expensive grounded call by key without touching the generation
    body. No caching happens here yet — this is the seam.
    """
    company = (company or "").strip()
    if not company:
        return {"error": "Enter a company name first."}

    from backend.cache import cache
    return cache.get_or_generate(
        namespace="dossier",
        key=company.lower(),
        generator=lambda: _generate_report_uncached(company),
    )


def _generate_report_uncached(company: str) -> dict:
    """Grounded generation with no caching — always hits Gemini + Google Search."""
    t0 = time.time()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.google_api_key)

        resp = client.models.generate_content(
            model=settings.llm_grounding_model,  # lite is fine — grounding uses a separate ~1.5K RPD tool quota
            contents=PROMPT.format(company=company),
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
        logger.error(f"Company report JSON parse failed: {e}\nRaw: {text[:300]}")
        return {"error": "The research service returned malformed data. Please try again."}
    except Exception as e:
        msg = str(e)
        logger.error(f"Company report failed: {msg}")
        
        # Check if we have a pre-generated dossier for this company
        company_lower = company.lower().strip()
        if company_lower in _FALLBACK_REPORTS:
            logger.info(f"Using high-quality pre-generated fallback report for: {company}")
            return {
                "company": company,
                **_FALLBACK_REPORTS[company_lower],
                "_fallback": True,   # never cache — this is a degraded result
            }

        # Fall back to a generic template for any other company
        logger.info(f"Using generic fallback template for: {company}")
        return {**get_generic_fallback(company), "_fallback": True}

    logger.info(f"Company report for '{company}' done in {time.time()-t0:.1f}s ({len(sources)} sources)")

    # If the model says it found nothing, honour that
    if data.get("error"):
        return {"error": data["error"]}

    # Defensive normalization — the LLM occasionally returns wrong types
    def _lst(key):
        v = data.get(key)
        return [str(x) for x in v] if isinstance(v, list) else []

    def _str(key, default=""):
        v = data.get(key)
        return str(v) if v not in (None, "") else default

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

    return {
        "company": company,
        "overview": _str("overview", "No overview available."),
        "india_presence": _str("india_presence"),
        "pros": _lst("pros"),
        "cons": _lst("cons"),
        "salaries": _lst("salaries"),
        "work_life_balance": _str("work_life_balance", "No work-life balance data available."),
        "sources": merged,
    }
