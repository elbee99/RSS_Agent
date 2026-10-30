"""
Rank this week's articles with Claude.

Three stages, to keep cost and run time low while being picky:
  0. PREFILTER - free keyword check; drops articles with no battery terms at all.
  1. TRIAGE    - a cheap model scores the rest 0-10, many articles per API call.
  2. REVIEW    - a stronger model re-scores the shortlist and writes a short
                 "why it's interesting" note (not a title rephrase).

Output: cache/ranked_articles.json (all articles, sorted)
        cache/curated.json         (the filtered list used for the PDF)
"""
import json
import os
import re
import html
import time
from concurrent.futures import ThreadPoolExecutor

import anthropic

RAW_FEED_CACHE = "cache/raw_feeds.json"
RANKED_CACHE = "cache/ranked_articles.json"
CURATED_CACHE = "cache/curated.json"

# Models: set TRIAGE_MODEL / REVIEW_MODEL repo variables to override.
# Otherwise the first available model in each list is used, so a retired
# model never breaks the run.
TRIAGE_CANDIDATES = ["claude-haiku-4-5"]
REVIEW_CANDIDATES = ["claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6", "claude-sonnet-4-5"]

THRESHOLD = float(os.environ.get("SCORE_THRESHOLD") or 6)   # keep score >= this
MAX_PAPERS = int(os.environ.get("MAX_PAPERS") or 25)         # ...capped at this many
TRIAGE_PASS = float(os.environ.get("TRIAGE_PASS") or 5)      # triage score needed for full review
TRIAGE_BATCH = 25                                            # articles per triage call
WORKERS = 4                                                  # parallel API calls

client = anthropic.Anthropic()

# Articles must mention at least one of these (title + abstract) to be sent to Claude.
BATTERY_TERMS = re.compile(
    r"batter|lithium|\bli[- ]?ion|\bli[- ]?metal|\bli[- ]?s\b|sodium[- ]ion|\bna[- ]?ion|"
    r"potassium[- ]ion|zinc[- ]ion|\bzn[- ]?ion|magnesium[- ]ion|calcium[- ]ion|"
    r"cathode|anode|electrolyte|electrode|interphase|\bsei\b|\bcei\b|dendrit|plating|"
    r"intercalat|solid[- ]state|energy storage|state of charge|redox flow",
    re.IGNORECASE,
)

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
    "name": "record_scores",
    "description": "Record a relevance score for every article in the list.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer", "description": "Article number as given."},
                        "score": {"type": "integer", "minimum": 0, "maximum": 10},
                    },
                    "required": ["n", "score"],
                },
            }
        },
        "required": ["scores"],
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


def pick_model(env_var, candidates):
    if os.environ.get(env_var):
        return os.environ[env_var]
    for m in candidates:
        try:
            client.models.retrieve(m)
            return m
        except anthropic.NotFoundError:
            continue
    raise RuntimeError(f"None of {candidates} is available; set the {env_var} repo variable.")


def call_tool(model, tool, user, max_tokens):
    for attempt in range(5):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=RUBRIC,
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": user}],
            )
            for block in resp.content:
                if block.type == "tool_use":
                    return block.input
            return None
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError) as e:
            wait = 10 * (attempt + 1)
            print(f"  {e.__class__.__name__}; retrying in {wait}s")
            time.sleep(wait)
    return None


def article_text(a, abstract_chars=4000):
    abstract = clean(a.get("content", ""))[:abstract_chars] or "(no abstract in feed)"
    return f"Journal: {a.get('journal', '')}\nTitle: {clean(a['title'])}\nAbstract: {abstract}"


def triage_batch(model, batch):
    body = "Score each article below.\n\n" + "\n\n".join(
        f"### Article {i}\n{article_text(a, 1500)}" for i, a in enumerate(batch)
    )
    out = call_tool(model, TRIAGE_TOOL, body, max_tokens=60 + 25 * len(batch))
    scores = {s["n"]: s["score"] for s in (out or {}).get("scores", []) if "n" in s}
    for i, a in enumerate(batch):
        a["triage_score"] = float(scores.get(i, 0))


def review(model, a):
    out = call_tool(model, REVIEW_TOOL, article_text(a), max_tokens=400)
    if out:
        a["score"] = float(out["score"])
        a["technique"] = out.get("technique", "")
        a["summary"] = out.get("why_interesting", "")


def rank_articles():
    with open(RAW_FEED_CACHE, "r", encoding="utf-8") as f:
        articles = json.load(f)

    for a in articles:
        a.update(triage_score=0.0, score=0.0, summary="", technique="")

    candidates = [a for a in articles if BATTERY_TERMS.search(a["title"] + " " + clean(a.get("content", "")))]
    print(f"{len(articles)} articles; {len(candidates)} mention batteries and go to triage.")

    triage_model = pick_model("TRIAGE_MODEL", TRIAGE_CANDIDATES)
    review_model = pick_model("REVIEW_MODEL", REVIEW_CANDIDATES)
    print(f"Triage model: {triage_model}  |  Review model: {review_model}")

    batches = [candidates[i:i + TRIAGE_BATCH] for i in range(0, len(candidates), TRIAGE_BATCH)]
    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(lambda b: triage_batch(triage_model, b), batches))
    for a in candidates:
        a["score"] = a["triage_score"]

    shortlist = [a for a in candidates if a["triage_score"] >= TRIAGE_PASS]
    print(f"{len(shortlist)} passed triage (>= {TRIAGE_PASS}); reviewing...")
    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(lambda a: review(review_model, a), shortlist))

    ranked = sorted(articles, key=lambda x: x["score"], reverse=True)
    curated = [a for a in ranked if a["score"] >= THRESHOLD][:MAX_PAPERS]

    with open(RANKED_CACHE, "w", encoding="utf-8") as f:
        json.dump(ranked, f, indent=2, ensure_ascii=False)
    with open(CURATED_CACHE, "w", encoding="utf-8") as f:
        json.dump(curated, f, indent=2, ensure_ascii=False)

    print(f"Kept {len(curated)} papers (score >= {THRESHOLD}, max {MAX_PAPERS}).")
    return curated


if __name__ == "__main__":
    rank_articles()
