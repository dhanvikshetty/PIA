"""
Resume Analyzer — ATS-Style Analysis

Fast path: ONE Gemini call returning plain JSON (no structured_output overhead).
Rule-based formatting checks run first (zero API cost).

PII: Both PDFs processed in-memory only — never persisted.
"""

import os
import re
import json
try:
    import fitz
except ImportError:
    fitz = None
from typing import Optional
from loguru import logger

from backend.config import settings


# ─────────────────────────────────────────────
# PDF extraction
# ─────────────────────────────────────────────

def _extract_text(pdf_bytes: bytes, label: str) -> str:
    if fitz is None:
        logger.error(f"PyMuPDF is not available. Cannot extract text from {label}.")
        return ""
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
# Rule-based formatting checks (instant, no API)
# ─────────────────────────────────────────────

_SECTIONS = [
    "summary", "objective", "profile", "experience", "work experience",
    "employment", "education", "academic", "skills", "technical skills",
    "projects", "certifications", "achievements", "awards",
]


def _formatting_checks(text: str) -> dict:
    low = text.lower()
    lines = text.splitlines()
    positives, issues = [], []

    if re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text):
        positives.append("Email address present")
    else:
        issues.append("No email address — ATS requires contact info")

    if re.search(r"(\+?\d[\d\s\-().]{7,}\d)", text):
        positives.append("Phone number present")
    else:
        issues.append("No phone number detected")

    if "linkedin.com" in low:
        positives.append("LinkedIn URL included")
    if "github.com" in low:
        positives.append("GitHub URL included")

    bullets = sum(1 for l in lines if re.match(r"^[\s]*[•\-\*▪▸◦]", l))
    if bullets >= 5:
        positives.append("Bullet points used (ATS-friendly)")
    elif bullets == 0:
        issues.append("No bullet points — use bullets for experience")

    if re.search(r"\b(19|20)\d{2}\b", text):
        positives.append("Employment dates present")
    else:
        issues.append("No dates detected — add start/end dates to each role")

    detected = [s.title() for s in _SECTIONS if s in low]
    for s in ["Experience", "Education", "Skills"]:
        if s.lower() not in low:
            issues.append(f"Missing '{s}' section — core ATS requirement")

    words = len(text.split())
    if words < 300:
        issues.append(f"Resume too short ({words} words)")
    elif words > 2000:
        issues.append(f"Resume very long ({words} words) — aim for 1-2 pages")
    else:
        positives.append(f"Good length ({words} words)")

    if sum(1 for l in lines if len(l) > 100) > 20:
        issues.append("Possible multi-column layout — ATS parsers struggle with columns")

    return {
        "positives": positives,
        "issues": issues,
        "detected_sections": detected,
        "score": max(0.0, 100.0 - len(issues) * 15),
    }


# ─────────────────────────────────────────────
# Prompt — returns plain JSON, no schema overhead
# ─────────────────────────────────────────────

PROMPT = """\
You are an ATS (Applicant Tracking System) expert. Analyze the resume against the job description and return a JSON object. No markdown, no explanation — raw JSON only.

=== JOB DESCRIPTION ===
{jd_text}

=== RESUME ===
{resume_text}

=== PRE-COMPUTED FORMATTING (use these directly) ===
Sections found: {sections_present}
Formatting positives: {fmt_positives}
Formatting issues: {fmt_issues}
Formatting score: {fmt_score}/100

Return ONLY this JSON structure (no markdown fences):
{{
  "company": "string",
  "role": "string",
  "seniority_level": "Entry|Mid|Senior|Lead|Manager",
  "industry_domain": "string",
  "required_experience_years": null or int,
  "required_degree": null or "string",
  "required_skills": ["list of hard skills explicitly required"],
  "preferred_skills": ["list of nice-to-have skills"],
  "jd_keywords": ["all ATS keywords including acronyms AND full forms"],
  "ats_score": float (weighted: skills*0.35 + keywords*0.25 + experience*0.15 + education*0.10 + sections*0.10 + formatting*0.05),
  "section_scores": {{
    "skills_match": float,
    "keyword_density": float,
    "section_completeness": float,
    "experience_alignment": float,
    "education_match": float,
    "formatting": float (use pre-computed formatting score above)
  }},
  "matched_required_skills": ["skills in both JD and resume"],
  "missing_required_skills": ["required skills NOT in resume, ranked by importance"],
  "matched_preferred_skills": ["preferred skills in resume"],
  "missing_preferred_skills": ["preferred skills not in resume"],
  "matched_keywords": ["JD keywords found in resume"],
  "missing_keywords": ["important JD keywords missing from resume"],
  "experience_years_detected": null or int,
  "education_detected": null or "string",
  "priority_recommendations": ["5-7 specific actionable fixes, ordered by impact"],
  "strengths": ["3-4 genuine strengths for this specific JD"],
  "overall_verdict": "2-3 honest sentences about ATS pass likelihood and biggest gap"
}}"""


# ─────────────────────────────────────────────
# Shared LLM helpers
# ─────────────────────────────────────────────

def _build_prompt(resume_text: str, jd_text: str, fmt: dict) -> str:
    """Fill the single-call ATS prompt with JD/resume text + local formatting."""
    return PROMPT.format(
        jd_text=jd_text[:3500],
        resume_text=resume_text[:3500],
        sections_present=", ".join(fmt["detected_sections"]) or "None detected",
        fmt_positives="; ".join(fmt["positives"]) or "None",
        fmt_issues="; ".join(fmt["issues"]) or "None",
        fmt_score=int(fmt["score"]),
    )


def _parse_llm_json(raw) -> dict:
    """Coerce an LLM response .content (str or list-of-parts) into a dict."""
    if isinstance(raw, list):
        raw = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in raw
        )
    content = (raw or "").strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0].strip()
    return json.loads(content)


def _quota_message(exc: Exception) -> str:
    """User-facing message for an LLM failure — quota-aware."""
    msg = str(exc)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        return "The AI service is rate-limited right now (free-tier quota). Please wait about a minute and try again."
    return "ATS analysis failed. Please try again in a moment."


# ─────────────────────────────────────────────
# Main public function — single Groq→Gemini call
# ─────────────────────────────────────────────

def analyze_resume(resume_pdf_bytes: bytes, jd_pdf_bytes: bytes) -> dict:
    """
    ATS resume analysis — single LLM call with plain JSON output.

    1. Extract text from both PDFs (fitz, in-memory, instant)
    2. Rule-based formatting checks (instant regex)
    3. ONE chat_invoke call (Groq primary → Gemini fallback) → plain JSON
    4. Normalize + return
    """
    import time
    t0 = time.time()

    resume_text = _extract_text(resume_pdf_bytes, "Resume")
    jd_text = _extract_text(jd_pdf_bytes, "JD")

    if not resume_text.strip():
        return {"error": "Could not extract text from resume PDF. Make sure it is not a scanned image."}
    if not jd_text.strip():
        return {"error": "Could not extract text from JD PDF. Make sure it is not a scanned image."}

    fmt = _formatting_checks(resume_text)
    logger.info(f"Formatting done in {time.time()-t0:.1f}s: score={fmt['score']}, issues={len(fmt['issues'])}")

    try:
        from backend.rag.llm_client import chat_invoke
        response = chat_invoke(_build_prompt(resume_text, jd_text, fmt), temperature=0.0)
        report = _parse_llm_json(response.content)
    except Exception as e:
        logger.error(f"ATS analysis failed: {e}")
        return {"error": _quota_message(e)}

    logger.info(f"Total analysis time: {time.time()-t0:.1f}s")
    return _normalize_report(report, fmt)


# ─────────────────────────────────────────────
# Normalization — shared by streaming + non-streaming
# ─────────────────────────────────────────────

def _normalize_report(report: dict, fmt: dict) -> dict:

    # Normalize: ensure all expected keys exist with safe defaults.
    # These coercers are defensive — the LLM occasionally returns a value in the
    # wrong type (e.g. "85%" or "high"), which must not 500 the whole request.
    def _lst(key):
        v = report.get(key)
        return v if isinstance(v, list) else []

    def _flt(key):
        try:
            return float(report.get(key))
        except (TypeError, ValueError):
            return 0.0

    def _num(v):  # safe float for nested section_scores values
        try:
            return round(float(v), 1)
        except (TypeError, ValueError):
            return 0.0

    def _int(key):
        v = report.get(key)
        try:
            return int(v)  # note: 0 is a valid value and must be preserved
        except (TypeError, ValueError):
            return None

    def _str(key, default=""):
        v = report.get(key)
        return str(v) if v not in (None, "") else default

    ss = report.get("section_scores")
    if not isinstance(ss, dict):
        ss = {}

    return {
        "company":                   _str("company", "Unknown"),
        "role":                      _str("role", "Unknown Role"),
        "seniority_level":           _str("seniority_level", "Mid"),
        "industry_domain":           _str("industry_domain", "Software"),
        "required_experience_years": _int("required_experience_years"),
        "required_degree":           report.get("required_degree"),
        "ats_score":                 round(_flt("ats_score"), 1),
        "section_scores": {
            "skills_match":         _num(ss.get("skills_match")),
            "keyword_density":      _num(ss.get("keyword_density")),
            "section_completeness": _num(ss.get("section_completeness")),
            "experience_alignment": _num(ss.get("experience_alignment")),
            "education_match":      _num(ss.get("education_match")),
            "formatting":           _num(ss.get("formatting") or fmt["score"]),
        },
        "matched_required_skills":   _lst("matched_required_skills"),
        "missing_required_skills":   _lst("missing_required_skills"),
        "matched_preferred_skills":  _lst("matched_preferred_skills"),
        "missing_preferred_skills":  _lst("missing_preferred_skills"),
        "matched_keywords":          _lst("matched_keywords"),
        "missing_keywords":          _lst("missing_keywords"),
        "experience_years_detected": _int("experience_years_detected"),
        "education_detected":        report.get("education_detected"),
        "formatting_issues":         fmt["issues"],    # always use rule-based
        "formatting_positives":      fmt["positives"],
        "priority_recommendations":  _lst("priority_recommendations"),
        "strengths":                 _lst("strengths"),
        "overall_verdict":           _str("overall_verdict", "Analysis complete."),
        "total_required_skills":     len(_lst("required_skills")),
        "total_keywords":            len(_lst("jd_keywords")),
    }


# ─────────────────────────────────────────────
# Streaming variant — SSE progress + final result
# ─────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent-Events frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def analyze_resume_events(resume_pdf_bytes: bytes, jd_pdf_bytes: bytes):
    """
    Generator yielding SSE frames for a streaming ATS analysis.

    Emits `stage` frames as work progresses, then one final `result` frame with
    the full ResumeAnalyzeResponse dict — or an `error` frame on failure.

    This is still a SINGLE model round-trip: the stages are progress signals
    around local extraction/formatting and the one chat_invoke call, not extra
    LLM calls.
    """
    import time
    t0 = time.time()

    yield _sse("stage", {"stage": "extracting", "message": "Extracting text from your PDFs..."})
    resume_text = _extract_text(resume_pdf_bytes, "Resume")
    jd_text = _extract_text(jd_pdf_bytes, "JD")

    if not resume_text.strip():
        yield _sse("error", {"error": "Could not extract text from resume PDF. Make sure it is not a scanned image."})
        return
    if not jd_text.strip():
        yield _sse("error", {"error": "Could not extract text from JD PDF. Make sure it is not a scanned image."})
        return

    yield _sse("stage", {"stage": "formatting", "message": "Running ATS formatting checks..."})
    fmt = _formatting_checks(resume_text)

    yield _sse("stage", {"stage": "querying", "message": "Matching your resume against the job description..."})
    try:
        from backend.rag.llm_client import chat_invoke
        response = chat_invoke(_build_prompt(resume_text, jd_text, fmt), temperature=0.0)
        report = _parse_llm_json(response.content)
    except Exception as e:
        logger.error(f"ATS analysis (stream) failed: {e}")
        yield _sse("error", {"error": _quota_message(e)})
        return

    yield _sse("stage", {"stage": "scoring", "message": "Scoring and building your report..."})
    result = _normalize_report(report, fmt)
    logger.info(f"Total analysis time (stream): {time.time()-t0:.1f}s")
    yield _sse("result", result)
