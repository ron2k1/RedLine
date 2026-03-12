"""LLM analyzer module -- structured analysis of filing diffs via Ollama.

Uses Ollama's OpenAI-compatible endpoint with the instructor library
for validated, structured output (Pydantic models).

Does NOT compute scores -- that's scorer.py's job.
"""

import json
import logging
from typing import Optional

import instructor
from openai import OpenAI
from pydantic import BaseModel, Field

from redline import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class NotableChange(BaseModel):
    """A single notable change detected in the filing diff."""
    description: str = Field(description="Brief description of the change")
    category: str = Field(
        description="Category: risk, financial, operational, legal, governance"
    )
    severity: int = Field(ge=1, le=10, description="Severity 1-10")
    quote: str = Field(description="Relevant quote from the diff text")


class AnalysisResponse(BaseModel):
    """Structured LLM analysis output."""
    summary: str = Field(
        description="1-2 sentence summary of the most important changes"
    )
    notable_changes: list[NotableChange] = Field(default_factory=list)
    severity_score: int = Field(ge=1, le=10, description="Overall severity 1-10")
    reasoning: str = Field(description="Brief reasoning for the severity score")


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """You are a financial analyst reviewing changes between two SEC filing periods.

Filing: {ticker} {form_type} for period {period}
Section: {section}

Below is a diff summary showing what changed:
{diff_preview}

Signals detected: {signals}

Analyze these changes and assess their significance for investors.
Focus on material changes that could affect the company's financial health, risk profile, or operations.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_diff(
    ticker: str,
    form_type: str,
    period: str,
    section: str,
    diff_preview: str,
    signals_json: str,
) -> dict | None:
    """Run LLM analysis on a diff via Ollama.

    Returns dict with keys: summary, notable_changes, severity_score, reasoning.
    Returns None if the LLM call fails after retries.

    Does NOT compute final_score -- that's scorer.py's job.
    """
    try:
        # Create an OpenAI client pointing at Ollama's OpenAI-compatible endpoint
        openai_client = OpenAI(
            base_url=f"{config.OLLAMA_HOST}/v1",
            api_key="ollama",  # required by openai lib but unused by Ollama
        )

        # Patch with instructor for structured output
        patched_client = instructor.from_openai(
            openai_client,
            mode=instructor.Mode.JSON,
        )

        prompt = ANALYSIS_PROMPT.format(
            ticker=ticker,
            form_type=form_type,
            period=period,
            section=section,
            diff_preview=diff_preview[:3000],  # truncate to avoid token limits
            signals=signals_json,
        )

        response = patched_client.chat.completions.create(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_model=AnalysisResponse,
            max_retries=3,
        )

        return {
            "summary": response.summary,
            "notable_changes": [c.model_dump() for c in response.notable_changes],
            "severity_score": response.severity_score,
            "reasoning": response.reasoning,
        }

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        return None
