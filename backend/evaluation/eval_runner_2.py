import argparse
import asyncio
from datetime import datetime
import html
import json
import logging
from pathlib import Path
import random
import re
import sys
from typing import Any, Dict, List, Optional
import unicodedata

from tqdm import tqdm

# Add backend root to sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# Internal imports
try:
    from src.internal.mentions.agent import run_entity_linking
    from src.internal.queryGeneration.prompt_construction import prompt_construction
    from src.internal.queryGeneration.tool_calling_loop import run_query_generation
    from src.internal.queryGeneration.tools import get_tools_spec
    from src.internal.schema_cache import SCHEMA_CACHE, _load_preloaded_examples
    import src.internal.sparql as sparql_mod
    from src.schemas.mentions import DetailedMention, Mention
    from src.schemas.query_generation import (
        LinkedMention,
        LinkedMentions,
        RequestQueryGeneration,
    )
except ImportError as e:
    print(f"Import error: {e}")
    print("Please make sure you are running this from the backend directory.")
    sys.exit(1)

# --- Configuration & Constants ---
DATASET_CONFIGS = {
    "dblp": {
        "endpoint": "https://sparql.dblp.org/sparql",
        "schema_path": BACKEND_ROOT / "src/internal/data/dblp.rdf",
        "gold_path": BACKEND_ROOT / "evaluation/data/dblp_gold.json",
        "base_iri": "https://dblp.org/rdf/schema#",
        "rdf_format": "xml",
        "schema_key": "DBLP",
        "description": "The DBLP computer science bibliography dataset. Contains information about publications, authors, venues (journals and conferences), and their relationships.",
    },
    "beer": {
        "endpoint": "http://localhost:3030/beer/query",
        "schema_path": BACKEND_ROOT.parent / "fuseki/schema/beer/beer.ttl",
        "gold_path": BACKEND_ROOT / "evaluation/data/beer_gold.json",
        "base_iri": "https://rdf.ag/o/beer#",
        "rdf_format": "turtle",
        "schema_key": "BEER",
        "description": "A dataset about beers, breweries, beer styles, brands, and kegs. Contains detailed information about different alcoholic beverages and their manufacturers.",
    },
    "pokemon": {
        "endpoint": "http://localhost:3030/pokemon/query",
        "schema_path": BACKEND_ROOT.parent / "fuseki/schema/pokemon/pokemon.ttl",
        "gold_path": BACKEND_ROOT / "evaluation/data/pokemon_gold.json",
        "base_iri": None,
        "rdf_format": "turtle",
        "schema_key": "POKEMON",
        "description": "A dataset about Pokémon. Contains information about different Pokémon species, their types, abilities, stats, and evolutions.",
    },
}
DEFAULT_MODEL = "RWTH-GPT-gpt-oss-120b"
LOG = logging.getLogger("eval_runner")


# --- Utilities ---


def setup_logging(run_id: str, verbose: bool = False):
    log_dir = BACKEND_ROOT / "evaluation/runs" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "eval.log"

    # Root logger gets everything
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # File handler always gets INFO level logs
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    # Stream handler (terminal) level depends on verbose flag
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    if verbose:
        stream_handler.setLevel(logging.INFO)
    else:
        stream_handler.setLevel(logging.WARNING)
    root_logger.addHandler(stream_handler)

    return log_dir


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def parse_only_ids(value: str) -> set[str]:
    return {part.strip() for part in value.split(",") if part.strip()}


def load_results_payload(path: Path) -> Dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError(f"Invalid results payload in {path}")
    return payload


def calculate_metrics(ext_set: set, gold_set: set) -> Dict[str, float]:
    if not ext_set and not gold_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    tp = len(ext_set & gold_set)
    fp = len(ext_set - gold_set)
    fn = len(gold_set - ext_set)
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return {"precision": p, "recall": r, "f1": f1}


def _normalize_mention_text(text: str) -> str:
    if "\\u" in text:
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            pass
    text = unicodedata.normalize("NFKC", text).casefold().strip()
    text = text.strip('"“”')
    text = re.sub(r"\.$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_mention_match(ext: List[Dict[str, Any]], gold: List[Dict[str, Any]]) -> bool:
    if not ext and not gold:
        return True
    # Relaxed: Only compare the text spans (case-insensitive, trimmed)
    e_set = set(_normalize_mention_text(m["text"]) for m in ext if m.get("text"))
    g_set = set(_normalize_mention_text(m["text"]) for m in gold if m.get("text"))
    return e_set == g_set


def _is_entity_match(ext: List[Dict[str, Any]], gold: List[Dict[str, Any]]) -> bool:
    if not ext and not gold:
        return True
    e_set = set(e["iri"].strip("<>") for e in ext)
    g_set = set(e["iri"].strip("<>") for e in gold)
    return e_set == g_set


def compare_bindings(
    expected: List[Dict[str, Any]], actual: List[Dict[str, Any]]
) -> bool:
    """Rigorous binding comparison logic integrated from analyze_query_generation.py"""
    if len(expected) != len(actual):
        return False

    if not expected and not actual:
        return True

    def get_raw_set(row):
        return {
            str(val["value"]).strip()
            if isinstance(val, dict) and "value" in val
            else str(val).strip()
            for val in row.values()
        }

    actual_sets = [get_raw_set(r) for r in actual]

    for exp_row in expected:
        exp_set = get_raw_set(exp_row)
        if not any(exp_set.issubset(act_set) for act_set in actual_sets):
            return False

    return True


def generate_html_report(
    run_dir: Path, summary: Dict[str, Any], results: List[Dict[str, Any]]
):
    report_path = run_dir / "report.html"

    total = summary.get("total", 0)
    system_errors = summary.get("system_errors", 0)
    task_failures = summary.get("task_failures", 0)
    review_cases = summary.get("review_cases", 0)
    accuracy = summary.get("execution_accuracy", 0)

    ext_f1 = summary.get("avg_extraction_f1", 0)
    ext_p = summary.get("avg_extraction_precision", 0)
    ext_r = summary.get("avg_extraction_recall", 0)

    link_f1 = summary.get("avg_linking_f1", 0)
    link_p = summary.get("avg_linking_precision", 0)
    link_r = summary.get("avg_linking_recall", 0)

    # Candidate Ranking Metrics
    recall_at_k = summary.get("entity_recall_at_k_micro", 0)
    top1_rate = summary.get("gold_top1_rate_micro", 0)
    k_val = summary.get("k", 10)

    gold_entities_total = summary.get("gold_entities_total", 0)
    gold_entities_top1 = summary.get("gold_entities_top1", 0)
    gold_entities_retrieved_not_top1 = summary.get(
        "gold_entities_retrieved_not_top1", 0
    )
    gold_entities_not_retrieved = summary.get("gold_entities_not_retrieved", 0)
    cards_html = ""
    for r in results:
        # Match status for badges
        ext_mentions = r.get("steps", {}).get("extraction", [])
        gold_mentions = r.get("gold_mentions", [])
        mentions_match = _is_mention_match(ext_mentions, gold_mentions)

        ext_entities = r.get("steps", {}).get("linking", [])
        gold_entities = r.get("gold_entities", [])
        entities_match = _is_entity_match(ext_entities, gold_entities)

        is_correct = r.get("metrics", {}).get("execution_accuracy", 0) == 1.0
        is_error = r["status"] == "error"
        is_review = r["status"] == "review"

        if is_error:
            status_label = "ERROR"
            row_type = "failure"
        elif is_review:
            status_label = "REVIEW"
            row_type = "failure"
        elif is_correct and mentions_match and entities_match:
            status_label = "PASS"
            row_type = "success"
        else:
            status_label = "FAIL"
            row_type = "failure"

        status_class = status_label.lower()

        # Build Mentions HTML
        ext_m = r.get("metrics", {}).get("extraction", {})
        ext_f1_val = ext_m.get("f1", 0)
        mentions_html = f"""
        <div class="step-box {"match" if mentions_match else "mismatch"}">
            <div class="step-header">Extraction {"✅" if mentions_match else "❌"} <span style="float:right">F1: {ext_f1_val:.2f}</span></div>
            <div class="compare-grid">
                <div class="side"><strong>Extracted</strong><ul>{"".join(f"<li>'{html.escape(m['text'])}' <small>({html.escape(m.get('type', '').split('#')[-1])})</small></li>" for m in ext_mentions) or "<li>None</li>"}</ul></div>
                <div class="side gold"><strong>Gold</strong><ul>{"".join(f"<li>'{html.escape(m['text'])}' <small>({html.escape(m.get('type', '').split('#')[-1])})</small></li>" for m in gold_mentions) or "<li>None</li>"}</ul></div>
            </div>
        </div>"""

        # Build Entities HTML
        link_m = r.get("metrics", {}).get("linking", {})
        link_f1_val = link_m.get("f1", 0)
        entities_html = f"""
        <div class="step-box {"match" if entities_match else "mismatch"}">
            <div class="step-header">Linking {"✅" if entities_match else "❌"} <span style="float:right">F1: {link_f1_val:.2f}</span></div>
            <div class="compare-grid">
                <div class="side"><strong>Linked</strong><ul>{"".join(f"<li>{html.escape(e['text'])} &rarr; <small>{html.escape(e['iri'].split('/')[-1])}</small></li>" for e in ext_entities) or "<li>None</li>"}</ul></div>
                <div class="side gold"><strong>Gold</strong><ul>{"".join(f"<li>{html.escape(e['text'])} &rarr; <small>{html.escape(e['iri'].split('/')[-1])}</small></li>" for e in gold_entities) or "<li>None</li>"}</ul></div>
            </div>
        </div>"""

        # Build SPARQL HTML
        gen_query = r.get("steps", {}).get("generation", "N/A")
        gold_query = r.get("gold_query", "N/A")
        query_match_icon = "✅" if is_correct else ("❓" if is_review else "❌")
        query_match_class = (
            "match" if is_correct else ("review" if is_review else "mismatch")
        )

        sparql_html = f"""
        <div class="step-box {query_match_class}">
            <div class="step-header">Query Generation {query_match_icon}</div>
            <div class="compare-grid sparql-grid">
                <div class="side"><strong>Generated SPARQL</strong><pre><code>{html.escape(gen_query)}</code></pre></div>
                <div class="side gold"><strong>Gold Standard</strong><pre><code>{html.escape(gold_query)}</code></pre></div>
            </div>
        </div>"""

        # Build Results HTML
        actual_res = r.get("actual_results")
        expected_res = r.get("expected_results")
        results_comparison_html = ""

        if actual_res and expected_res:
            res_type = actual_res.get("type", "SELECT")
            if res_type == "ASK":
                results_comparison_html = f"""
                <div class="results-box">
                    <div class="step-header">Execution Results (ASK)</div>
                    <div class="compare-grid">
                        <div class="side"><strong>Actual:</strong> <code>{actual_res.get("boolean")}</code></div>
                        <div class="side gold"><strong>Expected:</strong> <code>{expected_res.get("boolean")}</code></div>
                    </div>
                </div>"""
            else:
                actual_binds = actual_res.get("bindings", [])
                expected_binds = expected_res.get("bindings", [])

                def format_bindings(binds, total):
                    if not binds:
                        return "<em>No results returned</em>"
                    html_str = "<div class='table-container'><table><thead><tr>"
                    keys = []
                    if binds:
                        keys = list(binds[0].keys())
                    if not keys:
                        return "<em>Empty result set</em>"
                    for k in keys:
                        html_str += f"<th>{html.escape(k)}</th>"
                    html_str += "</tr></thead><tbody>"
                    for row in binds:
                        html_str += "<tr>"
                        for k in keys:
                            cell = row.get(k, "")
                            if isinstance(cell, dict) and "value" in cell:
                                val = str(cell["value"])
                            else:
                                val = str(cell)
                            val_short = (val[:100] + "...") if len(val) > 100 else val
                            html_str += f"<td title='{html.escape(val)}'>{html.escape(val_short)}</td>"
                        html_str += "</tr>"
                    html_str += "</tbody></table></div>"
                    if total > len(binds):
                        html_str += f"<div class='more-results'>+ {total - len(binds)} more rows (showing top {len(binds)})</div>"
                    return html_str

                results_comparison_html = f"""
                <div class="results-box">
                    <div class="step-header">Execution Results (SELECT)</div>
                    <div class="compare-grid">
                        <div class="side"><strong>Actual ({actual_res.get("total", 0)} total)</strong>{format_bindings(actual_binds, actual_res.get("total", 0))}</div>
                        <div class="side gold"><strong>Expected ({expected_res.get("total", 0)} total)</strong>{format_bindings(expected_binds, expected_res.get("total", 0))}</div>
                    </div>
                </div>"""

        cards_html += f"""
        <div class="result-card {status_class}" data-type="{row_type}" id="card-{r["id"]}">
            <div class="card-header" onclick="toggleCard('{r["id"]}')" style="cursor: pointer;">
                <div class="id-badge">{r["id"]}</div>
                <div class="question-text">{html.escape(r["question"])}</div>
                <div class="status-indicator {status_class}">{status_label}</div>
                <div class="chevron">▼</div>
            </div>
            <div class="card-body collapsible-content" id="body-{r["id"]}" style="display: none;">
                <div class="pipeline-row">
                    {mentions_html}
                    {entities_html}
                </div>
                {sparql_html}
                {results_comparison_html}
                {f'<div class="error-banner">{html.escape(r.get("error", ""))}</div>' if is_error else ""}
                <div class="reason-tag">Failure Reason: <strong>{html.escape(r.get("failure_reason", "N/A"))}</strong></div>
            </div>
        </div>"""

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>NL2SPARQL Eval - {summary["timestamp"]}</title>
        <style>
            :root {{ --pass: #2ecc71; --fail: #e67e22; --review: #f1c40f; --error: #e74c3c; --bg: #f5f7f9; --text: #2c3e50; }}
            body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 40px; line-height: 1.5; }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            h1 {{ margin-top: 0; color: #1a2a3a; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}

            .summary-bar {{ display: flex; gap: 20px; margin-bottom: 40px; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 12px; flex: 1; box-shadow: 0 4px 6px rgba(0,0,0,0.05); text-align: center; border-bottom: 4px solid #3498db; }}
            .stat-card.accuracy {{ border-color: var(--pass); }}
            .stat-card.fail {{ border-color: var(--fail); }}
            .stat-card.review {{ border-color: var(--review); }}
            .stat-card.error {{ border-color: var(--error); }}
            .stat-card .val {{ font-size: 32px; font-weight: 800; display: block; }}
            .stat-card .lab {{ font-size: 12px; color: #7f8c8d; text-transform: uppercase; font-weight: 600; }}

            .controls {{ margin-bottom: 20px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
            .filter-btn, .action-btn {{ padding: 8px 18px; border-radius: 25px; border: 1px solid #ddd; background: white; cursor: pointer; font-weight: 600; transition: all 0.2s; font-size: 13px; }}
            .filter-btn.active {{ background: var(--text); color: white; border-color: var(--text); }}

            .result-card {{ background: white; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 15px; overflow: hidden; border-left: 8px solid #ddd; transition: transform 0.1s; }}
            .result-card:hover {{ transform: translateY(-2px); }}
            .result-card.pass {{ border-left-color: var(--pass); }}
            .result-card.fail {{ border-left-color: var(--fail); }}
            .result-card.review {{ border-left-color: var(--review); }}
            .result-card.error {{ border-left-color: var(--error); }}

            .card-header {{ padding: 15px 25px; background: #fff; display: flex; align-items: center; gap: 20px; user-select: none; }}
            .id-badge {{ background: #f0f4f8; padding: 4px 12px; border-radius: 6px; font-weight: bold; color: #546e7a; min-width: 60px; text-align: center; }}
            .question-text {{ font-size: 15px; font-weight: 600; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
            .status-indicator {{ padding: 4px 12px; border-radius: 20px; color: white; font-weight: bold; font-size: 11px; min-width: 60px; text-align: center; }}
            .status-indicator.pass {{ background: var(--pass); }}
            .status-indicator.fail {{ background: var(--fail); }}
            .status-indicator.review {{ background: var(--review); color: #333; }}
            .status-indicator.error {{ background: var(--error); }}
            .chevron {{ font-size: 12px; color: #bdc3c7; transition: transform 0.3s; }}
            .result-card.expanded .chevron {{ transform: rotate(180deg); }}
            .result-card.expanded .question-text {{ white-space: normal; }}

            .card-body {{ padding: 25px; border-top: 1px solid #f0f0f0; background: #fcfdfe; }}
            .pipeline-row {{ display: flex; gap: 20px; margin-bottom: 20px; }}
            .step-box {{ flex: 1; border: 1px solid #eef2f6; border-radius: 8px; overflow: hidden; background: white; }}
            .step-header {{ background: #f8fafc; padding: 8px 15px; font-size: 13px; font-weight: 700; border-bottom: 1px solid #eef2f6; }}
            .step-box.match {{ border-color: #d4edda; }}
            .step-box.mismatch {{ border-color: #f5c6cb; }}
            .step-box.review {{ border-color: #ffeeba; }}

            .compare-grid {{ display: flex; font-size: 13px; }}
            .side {{ flex: 1; padding: 15px; }}
            .side.gold {{ background: #fcfdfd; border-left: 1px dashed #eee; }}
            .sparql-grid {{ flex-direction: column; }}

            pre {{ background: #1e293b; color: #f8fafc; padding: 15px; border-radius: 6px; font-size: 12px; overflow-x: auto; margin-top: 10px; }}
            .results-box {{ margin-top: 20px; border: 1px solid #eef2f6; border-radius: 8px; overflow: hidden; background: white; }}
            .table-container {{ max-height: 250px; overflow-y: auto; }}
            .results-box table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
            .results-box th {{ background: #f8fafc; padding: 6px 10px; border-bottom: 1px solid #eef2f6; text-align: left; position: sticky; top: 0; box-shadow: 0 1px 0 #eef2f6; z-index: 10; }}
            .results-box td {{ padding: 6px 10px; border-bottom: 1px solid #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
            .more-results {{ padding: 8px; text-align: center; font-size: 10px; color: #94a3b8; }}
            small {{ color: #94a3b8; font-family: monospace; }}

            /* Modal Styles */
            .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); }}
            .modal-content {{ background-color: #fefefe; margin: 10% auto; padding: 30px; border-radius: 12px; width: 60%; max-width: 600px; box-shadow: 0 5px 25px rgba(0,0,0,0.2); position: relative; }}
            .modal-content h2 {{ margin-top: 0; color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 15px; }}
            .close {{ color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; line-height: 1; }}
            .close:hover, .close:focus {{ color: black; text-decoration: none; cursor: pointer; }}
            .modal-stats {{ display: flex; gap: 20px; margin-top: 25px; }}
            .stat-card:hover {{ transform: translateY(-3px); transition: transform 0.2s; box-shadow: 0 6px 12px rgba(0,0,0,0.1); }}
            </style>
            </head>
    <body>
        <div class="container">
            <h1>Pipeline Evaluation Report</h1>
            <div class="summary-bar">
                <div class="stat-card">
                    <span class="val">{total}</span>
                    <span class="lab">Total Queries</span>
                </div>
                <div class="stat-card accuracy" onclick="showModal('ext-modal')" style="cursor: pointer;" title="Click for Extraction details">
                    <span class="val">{ext_f1:.1f}%</span>
                    <span class="lab">Extraction</span>
                </div>
                <div class="stat-card accuracy" onclick="showModal('link-modal')" style="cursor: pointer;" title="Click for Linking details">
                    <span class="val">{link_f1:.1f}%</span>
                    <span class="lab">Linking</span>
                </div>
                <div class="stat-card accuracy">
                    <span class="val">{accuracy:.1f}%</span>
                    <span class="lab">Execution Acc</span>
                </div>
                <div class="stat-card fail">
                    <span class="val">{review_cases + task_failures}</span>
                    <span class="lab">Fail/Review</span>
                </div>
                <div class="stat-card error">
                    <span class="val">{system_errors}</span>
                    <span class="lab">System Errors</span>
                </div>
            </div>

            <!-- Modals for detailed metrics -->
            <div id="ext-modal" class="modal">
                <div class="modal-content">
                    <span class="close" onclick="closeModal('ext-modal')">&times;</span>
                    <h2>Mention Extraction Metrics</h2>
                    <p style="color: #7f8c8d; font-size: 13px; margin-top: 0;">Evaluation of text spans extracted by the LLM.</p>
                    <div class="modal-stats">
                        <div class="stat-card"><span class="val">{ext_p:.1f}%</span><span class="lab">Precision</span></div>
                        <div class="stat-card"><span class="val">{ext_r:.1f}%</span><span class="lab">Recall</span></div>
                        <div class="stat-card accuracy"><span class="val">{ext_f1:.1f}%</span><span class="lab">F1 Score</span></div>
                    </div>
                </div>
            </div>

            <div id="link-modal" class="modal">
                <div class="modal-content">
                    <span class="close" onclick="closeModal('link-modal')">&times;</span>
                    <h2>Entity Linking Metrics</h2>
                    <p style="color: #7f8c8d; font-size: 13px; margin-top: 0;">Evaluation of final linked IRIs and candidate retrieval.</p>

                    <div style="margin: 20px 0; padding: 15px; background: #f8fafc; border-radius: 8px; font-size: 14px;">
                        <ul style="margin: 0; padding-left: 20px; color: #334155;">
                            <li><strong>Total Gold Entities:</strong> {gold_entities_total}</li>
                            <li><strong>Ranked Top-1:</strong> {gold_entities_top1}</li>
                            <li><strong>Retrieved (Not Top-1):</strong> {gold_entities_retrieved_not_top1}</li>
                            <li><strong>Not Retrieved:</strong> {gold_entities_not_retrieved}</li>
                        </ul>
                    </div>

                    <div class="modal-stats" style="margin-bottom: 15px;">
                        <div class="stat-card"><span class="val">{link_p:.1f}%</span><span class="lab">Linking Precision</span></div>
                        <div class="stat-card"><span class="val">{link_r:.1f}%</span><span class="lab">Linking Recall</span></div>
                        <div class="stat-card accuracy"><span class="val">{link_f1:.1f}%</span><span class="lab">Linking F1</span></div>
                    </div>

                    <div class="modal-stats">
                        <div class="stat-card"><span class="val">{top1_rate:.1f}%</span><span class="lab">Top-1 Match Rate</span></div>
                        <div class="stat-card accuracy"><span class="val">{recall_at_k:.1f}%</span><span class="lab">Recall@{k_val}</span></div>
                    </div>
                </div>
            </div>

            <div class="controls">
                <button id="btn-all" class="filter-btn active" onclick="filterResults('all')">Show All</button>
                <button id="btn-fail" class="filter-btn" onclick="filterResults('failure')">Review / Failures</button>
                <div style="flex: 1;"></div>
                <button class="action-btn" onclick="expandAll(true)">Expand All</button>
                <button class="action-btn" onclick="expandAll(false)">Collapse All</button>
            </div>

            <div id="results-list">{cards_html}</div>
        </div>

        <script>
            function showModal(id) {{
                document.getElementById(id).style.display = "block";
            }}

            function closeModal(id) {{
                document.getElementById(id).style.display = "none";
            }}

            window.onclick = function(event) {{
                if (event.target.classList.contains('modal')) {{
                    event.target.style.display = "none";
                }}
            }}

            function toggleCard(id) {{
                const card = document.getElementById('card-' + id);
                const body = document.getElementById('body-' + id);
                const isExpanded = card.classList.contains('expanded');
                body.style.display = isExpanded ? 'none' : 'block';
                card.classList.toggle('expanded');
            }}

            function expandAll(expand) {{
                document.querySelectorAll('.result-card').forEach(card => {{
                    const id = card.id.replace('card-', '');
                    const body = document.getElementById('body-' + id);
                    body.style.display = expand ? 'block' : 'none';
                    card.classList.toggle('expanded', expand);
                }});
            }}

            function filterResults(type) {{
                document.querySelectorAll('.result-card').forEach(card => {{
                    card.style.display = (type === 'all' || card.getAttribute('data-type') === 'failure') ? 'block' : 'none';
                }});
                document.getElementById('btn-all').classList.toggle('active', type === 'all');
                document.getElementById('btn-fail').classList.toggle('active', type === 'failure');
            }}
        </script>
    </body>
    </html>
    """
    report_path.write_text(html_content, encoding="utf-8")
    return report_path


# --- Data Handling ---


class DatasetLoader:
    def __init__(self, questions_path: Path, answers_path: Path):
        self.questions_path = questions_path
        self.answers_path = answers_path
        self._questions = []
        self._answers = {}

    def load(self):
        data = load_json(self.questions_path)
        if isinstance(data, list):
            self._questions = data
            # Also check if answers are embedded in the questions (consolidated format)
            for q in self._questions:
                if "answer" in q and q.get("id"):
                    self._answers[q["id"]] = q["answer"]
        elif isinstance(data, dict) and "questions" in data:
            self._questions = data["questions"]
            for q in self._questions:
                if "answer" in q and q.get("id"):
                    self._answers[q["id"]] = q["answer"]
        else:
            raise ValueError(f"Invalid questions format in {self.questions_path}")

        # Still try to load separate answers file if provided and valid
        if self.answers_path and self.answers_path.is_file():
            ans_data = load_json(self.answers_path)
            if ans_data:
                if isinstance(ans_data, list):
                    for a in ans_data:
                        if a.get("id") and a.get("answer"):
                            self._answers[a["id"]] = a["answer"]
                elif isinstance(ans_data, dict) and "answers" in ans_data:
                    for a in ans_data["answers"]:
                        if a.get("id") and a.get("answer"):
                            self._answers[a["id"]] = a["answer"]

    def get_sample(self, limit: int, seed: int) -> List[Dict[str, Any]]:
        if limit <= 0 or limit >= len(self._questions):
            return self._questions
        rng = random.Random(seed)
        return rng.sample(self._questions, limit)

    def get_answer(self, qid: str) -> Optional[Dict[str, Any]]:
        return self._answers.get(qid)


# --- Pipeline Components ---


async def run_agentic_pipeline(
    ctx,
    schema_id: str,
    question: str,
    model: str,
    previous_mentions: Optional[List[DetailedMention]] = None,
) -> List[DetailedMention]:
    meta = SCHEMA_CACHE.get_meta(schema_id)
    result = await run_entity_linking(
        ctx=ctx,
        question=question,
        model=model,
        max_iterations=50,
        max_message_history=50,
        rerank_fallback=True,
        allow_user_clarification=False,
        kg_description=(meta.description if meta else None),
        previous_mentions=previous_mentions,
        follow_up_message="Please find candidates and link the provided mentions to the knowledge graph."
        if previous_mentions
        else None,
    )
    return result.mentions


async def run_generation(
    ctx, question: str, linked_mentions: List[LinkedMention], model: str, schema_id: str
) -> str:
    request = RequestQueryGeneration(
        question=question,
        mentions=LinkedMentions(mentions=linked_mentions),
        schema_id=schema_id,
        model=model,
    )
    user_prompt, system_prompt = prompt_construction(request)
    res = await run_query_generation(
        model=model,
        schema_id=schema_id,
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        tools=get_tools_spec(),
    )
    return res.query


# --- Evaluation Logic ---


class Evaluator:
    def __init__(self, ctx, model: str, schema_id: str, endpoint: str):
        self.ctx = ctx
        self.model = model
        self.schema_id = schema_id
        self.endpoint = endpoint

    def gold_to_linked_mentions(self, item: Dict[str, Any]) -> List[LinkedMention]:
        """Convert DBLP-QuAD entities to LinkedMention for mocking."""
        raw_entities = item.get("entities") or item.get("processed_entities") or []
        linked = []

        for i, e in enumerate(raw_entities):
            if isinstance(e, str):
                linked.append(
                    LinkedMention(
                        text=f"Gold Entity {i}",
                        type=" ",
                        iri=e.strip("<>"),
                        label_pred=None,
                    )
                )
            elif isinstance(e, dict):
                linked.append(
                    LinkedMention(
                        text=e.get("text") or f"Gold Entity {i}",
                        type=e.get("type") or " ",
                        iri=(e.get("iri") or "").strip("<>"),
                        label_pred=e.get("label"),
                    )
                )
        return linked

    async def evaluate_item(
        self,
        item: Dict[str, Any],
        gold_answer: Optional[Dict[str, Any]],
        task: str,
        use_gold_linking: bool = False,
        use_gold_extraction: bool = False,
    ) -> Dict[str, Any]:
        qid = item.get("id", "unknown")
        question = (
            item["question"].get("string", "")
            if isinstance(item.get("question"), dict)
            else item.get("question", "")
        )

        # Prepare gold data for report comparison
        gold_linked = self.gold_to_linked_mentions(item)
        gold_mentions_raw = item.get("mentions") or item.get("expected_mentions")

        if gold_mentions_raw and isinstance(gold_mentions_raw, list):
            gold_mentions_list = []
            for m in gold_mentions_raw:
                if isinstance(m, str):
                    gold_mentions_list.append({"text": m, "type": " "})
                elif isinstance(m, dict):
                    gold_mentions_list.append(
                        {"text": m.get("text") or "N/A", "type": m.get("type") or " "}
                    )
        else:
            gold_mentions_list = [
                {"text": lm.text, "type": lm.type} for lm in gold_linked
            ]

        gold_entities_list = [{"text": lm.text, "iri": lm.iri} for lm in gold_linked]

        result = {
            "id": qid,
            "question": question,
            "gold_query": item.get("query", {}).get("sparql")
            if isinstance(item.get("query"), dict)
            else "N/A",
            "gold_mentions": gold_mentions_list,
            "gold_entities": gold_entities_list,
            "status": "success",
            "metrics": {},
            "steps": {},
        }

        try:
            # 1. Extraction
            mentions = []
            detailed_mentions = []
            if task in ["extraction", "linking", "generation", "e2e", "isolated"]:
                if use_gold_extraction and task != "isolated":
                    mentions = [
                        Mention(
                            text=lm.text, type=lm.type, label_pred=lm.label_pred or ""
                        )
                        for lm in gold_linked
                    ]
                    detailed_mentions = [
                        DetailedMention(
                            **m.model_dump(exclude={"candidates"}), candidates=[]
                        )
                        for m in mentions
                    ]
                else:
                    detailed_mentions = await run_agentic_pipeline(
                        self.ctx, self.schema_id, question, self.model
                    )
                    mentions = [
                        Mention(
                            text=dm.text,
                            type=dm.type,
                            label_pred=dm.label_pred or "",
                            attrs=dm.attrs,
                        )
                        for dm in detailed_mentions
                    ]
                result["steps"]["extraction"] = [m.model_dump() for m in mentions]

                # Calculate metrics
                e_set_mentions = set(
                    _normalize_mention_text(m.text) for m in mentions if m.text
                )
                g_set_mentions = set(
                    _normalize_mention_text(m["text"])
                    for m in gold_mentions_list
                    if m.get("text")
                )
                result["metrics"]["extraction"] = calculate_metrics(
                    e_set_mentions, g_set_mentions
                )

            # 2. Linking
            linked_mentions = []
            if task in ["linking", "generation", "e2e", "isolated"]:
                if use_gold_linking and task != "isolated":
                    linked_mentions = gold_linked
                else:
                    if use_gold_extraction or task == "isolated":
                        mentions_for_linking = [
                            Mention(
                                text=lm.text,
                                type=lm.type,
                                label_pred=lm.label_pred or "",
                            )
                            for lm in gold_linked
                        ]
                        detailed_mentions_for_linking = [
                            DetailedMention(
                                **m.model_dump(exclude={"candidates"}), candidates=[]
                            )
                            for m in mentions_for_linking
                        ]
                        detailed_mentions = await run_agentic_pipeline(
                            self.ctx,
                            self.schema_id,
                            question,
                            self.model,
                            previous_mentions=detailed_mentions_for_linking,
                        )
                    for dm in detailed_mentions:
                        if dm.candidates:
                            top = dm.candidates[0]
                            linked_mentions.append(
                                LinkedMention(
                                    text=dm.text,
                                    type=dm.type,
                                    iri=top.uri,
                                    label_pred=dm.label_pred,
                                )
                            )
                result["steps"]["linking"] = [lm.model_dump() for lm in linked_mentions]

                # Calculate metrics
                e_set_entities = set(
                    lm.iri.strip("<>") for lm in linked_mentions if lm.iri
                )
                g_set_entities = set(
                    e["iri"].strip("<>") for e in gold_entities_list if e.get("iri")
                )
                result["metrics"]["linking"] = calculate_metrics(
                    e_set_entities, g_set_entities
                )

                # Candidate Ranking Metrics
                if not use_gold_linking and task in [
                    "linking",
                    "generation",
                    "e2e",
                    "isolated",
                ]:
                    k = 10
                    gold_ranks = []
                    for gold_ent in gold_entities_list:
                        gold_iri = gold_ent.get("iri", "").strip("<>")
                        if not gold_iri:
                            continue

                        best_rank = -1
                        for dm in detailed_mentions:
                            for i, cand in enumerate(dm.candidates):
                                if cand.uri.strip("<>") == gold_iri:
                                    if best_rank == -1 or (i + 1) < best_rank:
                                        best_rank = i + 1
                        gold_ranks.append(best_rank)

                    result["metrics"]["linking_ranking"] = {"ranks": gold_ranks, "k": k}

            # 3. Generation
            generated_query = ""
            if task in ["generation", "e2e", "isolated"]:
                mentions_for_generation = (
                    gold_linked if task == "isolated" else linked_mentions
                )
                generated_query = await run_generation(
                    self.ctx,
                    question,
                    mentions_for_generation,
                    self.model,
                    self.schema_id,
                )
                result["steps"]["generation"] = generated_query

            # 4. Execution & Validation
            if task in ["generation", "e2e", "isolated"] and gold_answer:
                exec_res = await sparql_mod.run(
                    self.endpoint, generated_query, self.ctx
                )
                is_correct = False

                # Capture results
                is_ask = "boolean" in gold_answer and isinstance(
                    gold_answer["boolean"], bool
                )

                if is_ask:
                    is_correct = exec_res.boolean == gold_answer["boolean"]
                    actual_results_for_report = {
                        "type": "ASK",
                        "boolean": exec_res.boolean,
                    }
                    expected_results_for_report = {
                        "type": "ASK",
                        "boolean": gold_answer["boolean"],
                    }
                else:
                    expected_bindings = gold_answer.get("results", {}).get(
                        "bindings", []
                    )
                    if not expected_bindings and "bindings" not in gold_answer.get(
                        "results", {}
                    ):
                        if isinstance(gold_answer.get("results"), list):
                            expected_bindings = gold_answer["results"]

                    actual_bindings = []
                    if exec_res.results and exec_res.results.bindings:
                        for b in exec_res.results.bindings:
                            actual_bindings.append(
                                {
                                    k: (v.value if hasattr(v, "value") else v)
                                    for k, v in b.items()
                                }
                            )

                    is_correct = compare_bindings(expected_bindings, actual_bindings)
                    actual_results_for_report = {
                        "type": "SELECT",
                        "bindings": actual_bindings[:100],
                        "total": len(actual_bindings),
                    }
                    expected_results_for_report = {
                        "type": "SELECT",
                        "bindings": expected_bindings[:100],
                        "total": len(expected_bindings),
                    }

                result["metrics"]["execution_accuracy"] = 1.0 if is_correct else 0.0
                result["actual_results"] = actual_results_for_report
                result["expected_results"] = expected_results_for_report

                if not is_correct:
                    gold_iris = {lm.iri for lm in gold_linked if lm.iri}
                    pred_iris = {lm.iri for lm in linked_mentions if lm.iri}

                    if not gold_iris.issubset(pred_iris):
                        # Hard failure: The correct entities were not passed to the generator
                        result["status"] = "fail"
                        result["failure_reason"] = "linking_error"
                        result["missing_iris"] = list(gold_iris - pred_iris)
                    else:
                        # Soft failure: Entities were correct, but query logic/format mismatched
                        result["status"] = "review"
                        result["failure_reason"] = "generation_mismatch"

        except Exception as e:
            LOG.exception(f"Error evaluating item {qid}")
            result["status"] = "error"
            result["error"] = str(e)

        return result


async def main_async():
    parser = argparse.ArgumentParser(description="Unified Evaluation Runner")
    parser.add_argument(
        "--dataset",
        choices=["dblp", "beer", "pokemon"],
        default="dblp",
        help="Which dataset to evaluate",
    )
    parser.add_argument(
        "--task",
        choices=["extraction", "linking", "generation", "e2e", "isolated"],
        default="e2e",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--use-gold-linking", action="store_true")
    parser.add_argument("--use-gold-extraction", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--only-ids",
        help="Comma-separated question IDs to evaluate, e.g. Q0001,Q0007",
    )
    parser.add_argument(
        "--continue",
        dest="continue_from",
        help="Path to a previous results.json whose non-rerun items should be reused.",
    )

    args = parser.parse_args()
    logging.getLogger().handlers.clear()

    # Ensure internal 'app' logger also respects our configuration
    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.propagate = True

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = setup_logging(run_id, args.verbose)
    LOG.info(f"Starting evaluation run: {run_id}")

    # Load Dataset
    config = DATASET_CONFIGS[args.dataset]
    q_path = config["gold_path"]

    if not q_path.exists():
        LOG.error(f"Dataset not found at {q_path}")
        return

    loader = DatasetLoader(q_path, Path(""))
    loader.load()

    previous_results_by_id = {}
    base_sample = None
    run_limit = args.limit
    if args.continue_from:
        continue_path = Path(args.continue_from)
        previous_payload = load_results_payload(continue_path)
        run_limit = previous_payload.get("summary", {}).get("limit", args.limit)
        base_sample = loader.get_sample(run_limit, args.seed)
        previous_results_by_id = {
            item.get("id"): item
            for item in previous_payload["results"]
            if isinstance(item, dict) and item.get("id")
        }
        LOG.info(
            f"Loaded {len(previous_results_by_id)} prior results from {continue_path}."
        )

    sample = (
        list(base_sample)
        if base_sample is not None
        else loader.get_sample(run_limit, args.seed)
    )
    if args.only_ids:
        only_ids = parse_only_ids(args.only_ids)
        sample = [item for item in sample if item.get("id") in only_ids]
        LOG.info(f"Filtered to {len(sample)} items from --only-ids.")
    LOG.info(f"Loaded {len(sample)} items from {args.dataset}.")

    schema_id = f"{config['schema_key']}_EVAL"
    schema_data = config["schema_path"].read_bytes()
    SCHEMA_CACHE.put(
        schema_data,
        schema_id=schema_id,
        name=f"{config['schema_key']} Eval",
        endpoint=config["endpoint"],
        base_iri=config["base_iri"],
        rdf_format=config["rdf_format"],
        description=config.get("description"),
        overwrite=True,
    )

    examples_by_key = _load_preloaded_examples()
    if config["schema_key"] in examples_by_key:
        SCHEMA_CACHE.update_meta(
            schema_id, examples=examples_by_key[config["schema_key"]]
        )

    ctx = SCHEMA_CACHE.get(schema_id)

    evaluator = Evaluator(ctx, args.model, schema_id, config["endpoint"])
    results = []
    for item in tqdm(sample, desc=f"Evaluating {args.task}"):
        qid = item.get("id")
        gold_answer = loader.get_answer(qid)
        res = await evaluator.evaluate_item(
            item,
            gold_answer,
            args.task,
            args.use_gold_linking,
            args.use_gold_extraction,
        )
        results.append(res)

    if args.continue_from:
        rerun_results_by_id = {item["id"]: item for item in results}
        if base_sample is None:
            base_sample = loader.get_sample(args.limit, args.seed)
        results = []
        for item in base_sample:
            qid = item.get("id")
            if qid in rerun_results_by_id:
                results.append(rerun_results_by_id[qid])
            elif qid in previous_results_by_id:
                results.append(previous_results_by_id[qid])

        missing_ids = [
            item.get("id")
            for item in base_sample
            if item.get("id") not in {result.get("id") for result in results}
        ]
        if missing_ids:
            raise ValueError(
                "Missing merged results for IDs: " + ", ".join(missing_ids)
            )
    total = len(results)
    system_errors = sum(1 for r in results if r["status"] == "error")
    review_cases = sum(1 for r in results if r["status"] == "review")

    summary = {
        "dataset": args.dataset,
        "task": args.task,
        "limit": run_limit,
        "model": args.model,
        "timestamp": run_id,
        "total": total,
        "system_errors": system_errors,
        "review_cases": review_cases,
    }

    # Aggregate step-level metrics (Include all results, so failures drag the average down)
    if results:
        for step in ["extraction", "linking"]:
            # If a metric is missing due to a crash before the step completed, treat it as 0.0
            step_metrics = [
                r["metrics"].get(step, {"precision": 0.0, "recall": 0.0, "f1": 0.0})
                for r in results
            ]
            if step_metrics:
                avg_metrics = {
                    f"avg_{step}_{m}": sum(dm[m] for dm in step_metrics) / total
                    for m in ["precision", "recall", "f1"]
                }
                summary.update(avg_metrics)

        # Candidate Ranking aggregation
        if (
            args.task in ["linking", "generation", "e2e", "isolated"]
            and not args.use_gold_linking
        ):
            all_ranks = []
            for r in results:
                if "linking_ranking" in r.get("metrics", {}):
                    all_ranks.extend(r["metrics"]["linking_ranking"]["ranks"])
                else:
                    # If linking_ranking is missing because the item crashed before finishing linking,
                    # treat every gold entity in this question as "not retrieved" (-1)
                    gold_entities = r.get("gold_entities", [])
                    all_ranks.extend([-1] * len(gold_entities))

            if all_ranks:
                # Default to 10 if we can't find 'k' from any successful metric
                k = next(
                    (
                        r["metrics"]["linking_ranking"]["k"]
                        for r in results
                        if "linking_ranking" in r.get("metrics", {})
                    ),
                    10,
                )
                gold_entities_total = len(all_ranks)
                retrieved_ranks = [r for r in all_ranks if r != -1]

                gold_entities_top1 = sum(1 for r in all_ranks if r == 1)
                gold_entities_hit = sum(1 for r in retrieved_ranks if r <= k)
                gold_entities_retrieved_not_top1 = (
                    len(retrieved_ranks) - gold_entities_top1
                )
                gold_entities_not_retrieved = sum(1 for r in all_ranks if r == -1)

                histogram = {}
                for r in retrieved_ranks:
                    histogram[str(r)] = histogram.get(str(r), 0) + 1

                summary.update(
                    {
                        "items": total,
                        "k": k,
                        "gold_entities_total": gold_entities_total,
                        "gold_entities_hit": gold_entities_hit,
                        "gold_entities_top1": gold_entities_top1,
                        "gold_entities_retrieved_not_top1": gold_entities_retrieved_not_top1,
                        "gold_entities_not_retrieved": gold_entities_not_retrieved,
                        "entity_recall_at_k_micro": gold_entities_hit
                        / gold_entities_total
                        if gold_entities_total > 0
                        else 0,
                        "gold_top1_rate_micro": gold_entities_top1 / gold_entities_total
                        if gold_entities_total > 0
                        else 0,
                        "gold_retrieved_rate_micro": len(retrieved_ranks)
                        / gold_entities_total
                        if gold_entities_total > 0
                        else 0,
                        "gold_best_rank_histogram": histogram,
                    }
                )

    if args.task in ["generation", "e2e", "isolated"]:
        successes = sum(
            r.get("metrics", {}).get("execution_accuracy", 0.0) for r in results
        )
        summary["execution_accuracy"] = successes / total if total > 0 else 0.0
        summary["task_failures"] = total - successes - system_errors - review_cases

    (run_dir / "results.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8"
    )
    report_path = generate_html_report(run_dir, summary, results)

    print("\n" + "=" * 40)
    print(f"EVALUATION SUMMARY ({args.task})")
    print("-" * 40)
    print(f"{'Total Queries':20}: {summary['total']}")

    if "avg_extraction_f1" in summary:
        print(f"{'Extraction F1':20}: {summary['avg_extraction_f1']:.2f}")
    if "avg_linking_f1" in summary:
        print(f"{'Linking F1':20}: {summary['avg_linking_f1']:.2f}")
    if "entity_recall_at_k_micro" in summary:
        print(
            f"{'Entity Recall@' + str(summary.get('k', 10)):20}: {summary['entity_recall_at_k_micro']:.2f}"
        )
        print(f"{'Entity Top-1 Rate':20}: {summary['gold_top1_rate_micro']:.2f}")
    if "execution_accuracy" in summary:
        print(f"{'Execution Accuracy':20}: {summary['execution_accuracy']:.2f}")

    print(f"{'Review Required':20}: {summary['review_cases']}")
    print(f"{'Task Failures':20}: {summary.get('task_failures', 0)}")
    print(f"{'System Errors':20}: {summary['system_errors']}")
    print("=" * 40)
    print(f"HTML Report: {report_path}")


if __name__ == "__main__":
    asyncio.run(main_async())
