"""
Rank this week's articles with Claude.

Two stages, to keep cost low while being picky:
  1. TRIAGE  - a cheap model scores every article 0-10 against the rubric.
  2. REVIEW  - a stronger model re-scores anything that passed triage and writes
               a short "why it's interesting" note (not a title rephrase).

Output: cache/ranked_articles.json (all scored articles, sorted)
        cache/curated.json         (the filtered list used for the PDF)
"""
import json
import os
import re
import html
import time

import anthropic

RAW_FEED_CACHE = "cache/raw_feeds.json"
RANKED_CACHE = "cache/ranked_articles.json"
CURATED_CACHE = "cache/curated.json"

# Models are configurable from the workflow (repo variables) without code changes.
TRIAGE_MODEL = os.environ.get("TRIAGE_MODEL", "claude-haiku-4-5")
REVIEW_MODEL = os.environ.get("REVIEW_MODEL", "claude-sonnet-4-5")

# Selection: keep everything scoring >= THRESHOLD, capped at MAX_PAPERS.
THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", 6))
MAX_PAPERS = int(os.environ.get("MAX_PAPERS", 25))
# Triage score an article needs before it gets the (pricier) full review.
TRIAGE_PASS = float(os.environ.get("TRIAGE_PASS", 4))

client = anthropic.Anthropic()

RUBRIC = """
You are screening the battery / electrochemistry literature for a researcher in
chemical imaging of batteries. Be a demanding, sceptical referee: most papers
should score low.

WHAT THE READER WANTS (high scores)
- Chemical / spectroscopic imaging of batteries: X-ray (STXM, ptychography,
  XANES/EXAFS mapping, nano-/micro-CT, Bragg CDI), neutron imaging, Raman/IR
  mapping, NMR/MRI, cryo-EM/EELS/4D-STEM, ToF-SIMS, optical/interferometric
  operando microscopy, etc.
- Operando / in situ techniques that watch a working cell, especially new
  methods or clever extensions of existing ones.
- Spatial / multiscale heterogeneity: particle-to-particle, depth, SOC
  inhomogeneity, degradation fronts, tomography.
- Genuine mechanistic understanding: WHY a material/interface works or fails
  (SEI/CEI formation, lattice oxygen, phase transitions, Li plating, cracking,
  transport limitations), backed by direct evidence.
- Real breakthroughs in high-impact venues (Nature, Science, Nature Energy,
  Nature Materials, Joule, Nature Chemistry, etc.) that change how the field
  thinks, even if not imaging-based.

WHAT THE READER DOES NOT WANT (score 0-3)
- "Sandwich papers": we changed X / doped with Y / added additive Z / coated
  with W and got ~10-30% better capacity, rate or cycling, with routine
  characterisation (XRD, SEM, standard XPS, CV/EIS) and a hand-wavy or
  DFT-only rationale.
- Incremental electrolyte/additive/binder recipes without new mechanistic insight.
- Non-battery topics (photovoltaics, catalysis, OER/HER, fuel cells, TENGs,
  supercapacitors) -> 0, unless the technique itself is novel and clearly
  transferable to batteries (max 4).
- Reviews/perspectives: max 5 unless they are definitive on operando/imaging methods.

SCALE (0-10, integers)
 10  Field-changing: new imaging/operando capability or a mechanistic result
     that will be widely cited.
 8-9 Strong: advanced spatially resolved / operando characterisation yielding
     clear new insight into a battery mechanism.
 6-7 Interesting: solid mechanistic insight OR a notable new technique, but
     narrower or less convincing.
 4-5 Battery paper with some real insight, mostly conventional methods.
 1-3 Sandwich paper / incremental performance improvement.
 0   Not about batteries.
Judge only from the title and abstract; if the abstract is missing, be
conservative and do not exceed 5 unless the title alone clearly signals a
major imaging/operando advance.
"""

TRIAGE_TOOL = {
    "name": "record_score",
    "description": "Record the relevance score for one article.",
    "input_schema": {
        "type": "object",
        "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 10}},
        "required": ["score"],
    },
}

REVIEW_TOOL = {
    "name": "record_review",
    "description": "Record the final assessment of one article.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 10},
            "technique": {
                "type": "string",
                "description": "Key characterisation technique(s), a few words, e.g. 'operando 4D-STEM', or 'none notable'.",
            },
            "why_interesting": {
                "type": "string",
                "description": (
                    "1-2 sentences (max ~45 words) for an expert: what is actually new - "
                    "the specific mechanism revealed, the measurement trick, or the "
                    "quantitative finding. Do NOT restate the title. Do not use hype words."
                ),
            },
        },
        "required": ["score", "technique", "why_interesting"],
    },
}


def clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def call_tool(model, tool, system, user, max_tokens=300):
    for attempt in range(4):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": user}],
            )
            for block in resp.content:
                if block.type == "tool_use":
                    return block.input
            return None
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            wait = 5 * (attempt + 1)
            print(f"  API error ({e.__class__.__name__}); retrying in {wait}s")
            time.sleep(wait)
    return None


def article_text(a):
    return (
        f"Journal: {a.get('journal', '')}\n"
        f"Title: {clean(a['title'])}\n"
        f"Abstract: {clean(a.get('content', ''))[:4000] or '(no abstract in feed)'}"
    )


def rank_articles():
    with open(RAW_FEED_CACHE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"Triage of {len(articles)} articles with {TRIAGE_MODEL}...")
    for i, a in enumerate(articles):
        out = call_tool(TRIAGE_MODEL, TRIAGE_TOOL, RUBRIC, article_text(a), max_tokens=50)
        a["triage_score"] = float(out["score"]) if out else 0.0
        a["score"] = a["triage_score"]
        a["summary"], a["technique"] = "", ""
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(articles)}")

    shortlist = [a for a in articles if a["triage_score"] >= TRIAGE_PASS]
    print(f"Review of {len(shortlist)} shortlisted articles with {REVIEW_MODEL}...")
    for a in shortlist:
        out = call_tool(REVIEW_MODEL, REVIEW_TOOL, RUBRIC, article_text(a), max_tokens=400)
        if out:
            a["score"] = float(out["score"])
            a["technique"] = out.get("technique", "")
            a["summary"] = out.get("why_interesting", "")

    ranked = sorted(articles, key=lambda x: x["score"], reverse=True)
    curated = [a for a in ranked if a["score"] >= THRESHOLD][:MAX_PAPERS]

    with open(RANKED_CACHE, "w", encoding="utf-8") as f:
        json.dump(ranked, f, indent=2, ensure_ascii=False)
    with open(CURATED_CACHE, "w", encoding="utf-8") as f:
        json.dump(curated, f, indent=2, ensure_ascii=False)

    print(f"Ranked {len(ranked)} articles. Kept {len(curated)} (score >= {THRESHOLD}, max {MAX_PAPERS}).")
    return curated


if __name__ == "__main__":
    rank_articles()
