"""OpenRouter LLM-as-Judge wrappers.

A judge takes a pairwise comparison (question, candidate_A, candidate_B) and
returns a verdict in {"A", "B", "tie"}. Sequential judges additionally see
prior judges' verdicts to test anchoring.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")


@dataclass
class JudgeVerdict:
    judge_model: str
    raw_response: str
    verdict: str            # "A" / "B" / "tie" / "parse_fail"
    prompt_tokens: int
    completion_tokens: int


def _call_openrouter(model: str, prompt: str, timeout: int = 30,
                     max_tokens: int = 64, temperature: float = 0.0) -> dict:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_verdict(text: str) -> str:
    """Extract A / B / tie from judge response."""
    m = re.search(r"\b(A|B|TIE)\b", text.upper())
    if m:
        return m.group(1).lower() if m.group(1) == "TIE" else m.group(1)
    return "parse_fail"


def _build_prompt(question: str, cand_a: str, cand_b: str,
                  prior_verdicts: Optional[List[str]] = None) -> str:
    prior_text = ""
    if prior_verdicts:
        prior_text = (
            "\nPrior judges' verdicts: "
            + ", ".join(prior_verdicts)
            + "\n"
        )
    return f"""You are evaluating two candidate answers to a question.
Pick the better answer (A or B) or "tie" if they are equivalent.

Question: {question}

Candidate A: {cand_a}

Candidate B: {cand_b}
{prior_text}
Respond with ONLY one of: A, B, tie

Your answer:"""


def _parse_truth(text: str) -> str:
    """Extract true / false from a reference-free factuality verdict."""
    m = re.search(r"\b(TRUE|FALSE)\b", text.upper())
    if m:
        return m.group(1).lower()
    return "parse_fail"


def _build_statement_prompt(statement: str) -> str:
    return f"""You are checking a single statement for factual accuracy.
You are given ONLY the statement, with no reference answer.

Statement: {statement}

Is this statement factually correct? Consider any dates, numbers, and claims.
Respond with ONLY one word: true (if fully correct) or false (if it contains
any factual error).

Your answer:"""


def judge_statement(model: str, statement: str,
                    prior_verdicts: Optional[List[str]] = None) -> JudgeVerdict:
    """Reference-free single-statement factuality check. Verdict in
    {"true", "false", "parse_fail"}. Judge sees only the statement (no foil)."""
    prompt = _build_statement_prompt(statement)
    if prior_verdicts:
        prompt = (prompt.rstrip("\nYour answer:")
                  + "\nPrior judges' verdicts: " + ", ".join(prior_verdicts)
                  + "\n\nYour answer:")
    try:
        resp = _call_openrouter(model, prompt)
        msg = resp["choices"][0]["message"]["content"]
        usage = resp.get("usage", {})
        return JudgeVerdict(
            judge_model=model,
            raw_response=msg,
            verdict=_parse_truth(msg),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
    except Exception as e:
        return JudgeVerdict(
            judge_model=model,
            raw_response=f"ERROR: {e}",
            verdict="parse_fail",
            prompt_tokens=0,
            completion_tokens=0,
        )


def judge_pair(model: str, question: str, cand_a: str, cand_b: str,
               prior_verdicts: Optional[List[str]] = None) -> JudgeVerdict:
    """Query a single judge model for verdict on a pairwise comparison.

    If `prior_verdicts` is provided, this is a sequential cascade call; the
    judge sees prior judges' verdicts. Otherwise it is an independent call.
    """
    prompt = _build_prompt(question, cand_a, cand_b, prior_verdicts)
    try:
        resp = _call_openrouter(model, prompt)
        msg = resp["choices"][0]["message"]["content"]
        usage = resp.get("usage", {})
        return JudgeVerdict(
            judge_model=model,
            raw_response=msg,
            verdict=_parse_verdict(msg),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
    except Exception as e:
        return JudgeVerdict(
            judge_model=model,
            raw_response=f"ERROR: {e}",
            verdict="parse_fail",
            prompt_tokens=0,
            completion_tokens=0,
        )
