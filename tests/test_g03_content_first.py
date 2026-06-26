"""Content-first G03 tests: original slide content, market-case facts and structured prompt blocks.

These lock in the refactor that makes the generator prompt non-generic: A11/A08 additive content is
read from the gated user_approved_research_bundle@1 solution_handoff, market-case facts travel as
slide elements (not just IDs), and the prompt renders a power title, a teaching message and example
blocks with their facts and sources.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared" / "scripts"))

import pytest  # noqa: E402

from core import contracts  # noqa: E402
from g03 import blueprint as bp, slide_design as sd, prompt_build as pb  # noqa: E402


def _fact():
    return {
        "case_id": "case-0dte-volume-cboe-2025", "title": "0DTE options exceeded 60% of SPX volume",
        "institution_or_event": "CBOE", "event_date": "2025-05",
        "what_happened": "0DTE options took more than 60% of SPX options volume in May 2025.",
        "why_interesting": "Shows why gamma/theta dominate risk near expiry.",
        "source_url": "https://example.org/cboe", "source_title": "CBOE 2025 report",
    }


def test_extract_additive_reads_solution_handoff_of_gated_bundle():
    # The active g02 exit is user_approved_research_bundle@1: additive content lives under solution_handoff.
    research = {
        "schema_version": "user_approved_research_bundle@1",
        "solution_handoff": {
            "recommended_claims": [{
                "recommendation_id": "REC1", "topic_id": "T1", "claim": "Feature 0DTE risk concentration",
                "support_basis": "web", "web_case_refs": ["case-0dte-volume-cboe-2025"],
                "web_case_facts": [_fact()], "confidence": "high",
            }],
        },
    }
    cands = bp._extract_additive_candidates(research)
    assert len(cands) == 1
    assert cands[0]["kind"] == "recommended_claim"
    assert cands[0]["web_case_facts"][0]["case_id"] == "case-0dte-volume-cboe-2025"


def _slot(**kw):
    base = {
        "slot_id": "SLOT_N_001", "position": 1, "kind": "new", "status": "ADD",
        "working_title": "0DTE options", "power_title": "0DTE makes gamma the dominant near-expiry risk",
        "teaching_message": "Near expiry, 0DTE options concentrate gamma and theta risk.",
        "web_case_facts": [_fact()], "content_pointers": {"keep": [], "add": ["0DTE concentrates gamma"], "remove": []},
        "source_refs": ["case-0dte-volume-cboe-2025"], "is_new_information": True,
    }
    base.update(kw)
    return base


def _plan(slots):
    return {"schema_version": "slide_plan@1", "task_id": "T", "output_language": "Polish", "slots": slots}


def test_slide_design_builds_example_content_block_and_power_title():
    design = sd.build_slide_design(_plan([_slot()]))
    assert contracts.validate(design, "slide_design_set@1")["ok"]
    slide = design["slides"][0]
    assert slide["title"] == "0DTE makes gamma the dominant near-expiry risk"  # power title
    blocks = slide["content_blocks"]
    example = [b for b in blocks if b["kind"] == "example"]
    assert example and "60%" in example[0]["content"]


def test_prompt_renders_say_elements_and_example_facts():
    design = sd.build_slide_design(_plan([_slot()]))
    md = pb.build_presentation_prompt(design, "notebooklm")["prompt_markdown"]
    assert "What the slide should say" in md
    assert "Slide elements" in md
    assert "Real-world example" in md
    assert "60% of SPX volume" in md or "60% of SPX options volume" in md
    assert "How to read this spec" in md


def test_keep_slide_uses_original_content_not_placeholder():
    slot = _slot(slot_id="SLOT_E_5", kind="existing", status="KEEP", is_new_information=False,
                 power_title="Opcje to instrumenty pochodne",
                 teaching_message="Opcja to instrument pochodny, którego wartość zależy od instrumentu bazowego.",
                 web_case_facts=[], content_pointers={"keep": ["Opcja to instrument pochodny..."], "add": [], "remove": []})
    design = sd.build_slide_design(_plan([slot]))
    md = pb.build_presentation_prompt(design, "notebooklm")["prompt_markdown"]
    assert "instrument pochodny" in md
    assert "Nazwij główną ideę" not in md
