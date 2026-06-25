#!/usr/bin/env python3
"""Pure-stdlib MCP (stdio) server exposing the Research Graph's deterministic seams as tools.

Implements the minimal MCP stdio protocol (JSON-RPC 2.0, newline-delimited) BY HAND — no
third-party dependencies, so it runs with the system python3 like the rest of the plugin.
Claude Code / Codex launch it via .mcp.json with ${CLAUDE_PLUGIN_ROOT}; the deterministic seams
wrap shared/scripts/g02/g02_flow.py.

Methods: initialize, notifications/* (ignored), ping, tools/list, tools/call.
Tools: research_front_door, research_node_input, research_planner_prepare,
research_planner_finalize, research_plan_review_task, research_provider_status,
research_domain_prepare, research_query_plan_generate_fast, research_metadata_search,
research_doi_verify,
research_doi_verify_batch, research_domain_finalize,
research_domain_review_task, research_canonical_prepare, research_citation_expand,
research_canonical_finalize, research_canonical_review_task,
research_recent_prepare, research_recent_finalize, research_recent_review_task,
research_market_cases_prepare, research_web_case_search,
research_market_cases_finalize, research_market_cases_review_task,
research_candidate_index_prepare, research_candidate_index_finalize,
research_candidate_index_review_task,
research_source_selection_prepare, research_source_selection_validate,
research_source_selection_finalize, research_retrieval_prepare,
research_oa_resolve, research_document_retrieve, research_document_validate,
research_retrieval_finalize, research_retrieval_review_task,
research_web_case_extract,
research_paper_review_prepare, research_document_text_index,
research_document_text_window, research_paper_review_finalize,
research_paper_review_task, research_synthesis_prepare,
research_synthesis_finalize, research_synthesis_review_task,
research_bundle_finalize,
research_review_prepare, research_review_finalize,
research_finalize, research_scout_fanout, research_scout_a07_prepare,
research_scout_a07_tasks_prepare, research_scout_a07_partial_finalize, research_scout_a07_aggregate,
  research_scout_synthesis_prepare, research_scout_deep_dive_windows,
  research_scout_a09_task_prepare, research_scout_synthesis_finalize,
research_run_stub, research_run_codex.
"""
from __future__ import annotations

import json
import os
import sys
import pathlib

# Self-bootstrap sys.path so `core` and `g02` import however we're launched.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from g02 import g02_flow as rf  # noqa: E402
from g02 import domain  # noqa: E402
from g02 import canonical  # noqa: E402
from g02 import citations  # noqa: E402
from g02 import recent  # noqa: E402
from g02 import market_cases  # noqa: E402
from g02 import candidate_index  # noqa: E402
from g02 import source_selection  # noqa: E402
from g02 import retrieval  # noqa: E402
from g02 import oa_retrieval  # noqa: E402
from g02 import web_cases  # noqa: E402
from g02 import paper_review  # noqa: E402
from g02 import synthesis  # noqa: E402
from g02 import planner  # noqa: E402
from g02 import scout_fanout  # noqa: E402
from g02 import scout_a07_bridge  # noqa: E402
from g02 import scout_a07_runner  # noqa: E402
from g02 import scout_a09_runner  # noqa: E402
from g02 import scout_synthesis  # noqa: E402
from g02 import provider_config  # noqa: E402
from g02 import providers  # noqa: E402
from g02 import query_planning  # noqa: E402
from g02 import crossref  # noqa: E402
from g02 import review as reviewer  # noqa: E402
from core import artifacts, event_log, graphs, handoff  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "edu-materials-research", "version": "0.17.0"}


# ---- tool implementations (return JSON-serializable values) --------------

def _front_door(args: dict):
    return rf.front_door(args["context"])


def _node_input(args: dict):
    rgi = rf._load_any(args["ref"])
    inputs = rf.node_input_map(rgi, graphs.load(rf.GRAPH_ID))
    node = args.get("node")
    if not node:
        return inputs
    if node not in inputs:
        raise ValueError(f"no agent node {node!r}; have: {', '.join(inputs)}")
    return {node: inputs[node]}


def _finalize(args: dict):
    bundle = args["bundle"]
    if isinstance(bundle, str):                       # a path
        return rf.finalize(bundle)
    return handoff.emit_handoff(bundle, rf.OUTPUT_CONTRACT, name="research_bundle")  # inline


def _review_prepare(args: dict):
    return reviewer.prepare_review(args["task"])


def _review_finalize(args: dict):
    return reviewer.finalize_review_decision(args["task"], args["decision"])


def _planner_payload(value):
    if isinstance(value, dict) and "schema_version" not in value \
            and isinstance(value.get("ref"), str):
        return artifacts.hydrate(value["ref"])
    if isinstance(value, str) and value.startswith(artifacts.SCHEME):
        return artifacts.hydrate(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            return json.loads(stripped)
        if not stripped:
            raise ValueError("planner input string must not be empty")
        # Do not hand an arbitrary LLM-sized string to pathlib. Apart from producing
        # platform-specific errors (for example ENAMETOOLONG), that made an inline JSON
        # serialization indistinguishable from a path.
        if len(stripped) > 4096 or "\x00" in stripped:
            raise ValueError("planner input is neither inline JSON nor a safe path")
        path = pathlib.Path(stripped)
        if not path.is_file():
            raise ValueError(f"planner input path does not exist or is not a file: {stripped}")
        return json.loads(path.read_text(encoding="utf-8"))
    return value


def _planner_prepare(args: dict):
    return planner.prepare_planner(
        _planner_payload(args["input"]),
        previous_plan_ref=args.get("previous_plan_ref"),
        revision_items=args.get("revision_items"),
        execution_profile=args.get("execution_profile"),
    )


def _planner_finalize(args: dict):
    prepared = planner.prepare_planner(
        _planner_payload(args["input"]),
        previous_plan_ref=args.get("previous_plan_ref"),
        revision_items=args.get("revision_items"),
        execution_profile=args.get("execution_profile"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return planner.finalize_research_plan(
        prepared["planner_input"],
        args["plan"],
        previous_plan=prepared["previous_plan"],
        revision_items=prepared["revision_items"],
    )


def _plan_review_task(args: dict):
    prepared = planner.prepare_planner(
        _planner_payload(args["input"]),
        execution_profile=args.get("execution_profile"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return planner.build_research_plan_review_task(
        prepared["planner_input"],
        args["artifact"],
        review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _provider_status(args: dict):
    return provider_config.provider_status(args.get("config"))


def _query_plan_generate_fast(args: dict):
    profile = args.get("profile")
    if profile is None:
        manifest = graphs.load("g02")
        name = args.get("execution_profile") or manifest.get(
            "default_execution_profile", "fast"
        )
        profiles = manifest.get("execution_profiles", {})
        profile = profiles.get(name, {}) if isinstance(profiles, dict) else {}
    return query_planning.generate_fast_query_plan(args["discovery_input"], profile)


def _domain_prepare(args: dict):
    return domain.prepare_domain(
        args["research_plan_ref"],
        args["topic_id"],
        config_path=args.get("config"),
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )


def _metadata_search(args: dict):
    inputs = [args.get(name) for name in ("domain_input", "canonical_input", "recent_input")
              if args.get(name) is not None]
    if len(inputs) != 1:
        raise ValueError("exactly one of domain_input, canonical_input or recent_input is required")
    discovery_input = inputs[0]
    return providers.search_metadata(
        args["query_plan"],
        discovery_input,
        route_id=args["route_id"],
        provider=args["provider"],
        cursor=args.get("cursor"),
        config_path=args.get("config"),
    )


def _doi_verify(args: dict):
    return crossref.verify_source_record(args["source_record"])


def _doi_verify_batch(args: dict):
    return crossref.verify_source_records(args["source_records"])


def _domain_finalize(args: dict):
    prepared = domain.prepare_domain(
        args["research_plan_ref"],
        args["topic_id"],
        config_path=args.get("config"),
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return domain.finalize_domain_candidates(
        prepared["domain_input"],
        args["output"],
        previous_candidates=prepared["previous_candidates"],
        revision_items=prepared["revision_items"],
    )


def _domain_review_task(args: dict):
    prepared = domain.prepare_domain(
        args["research_plan_ref"],
        args["topic_id"],
        config_path=args.get("config"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return domain.build_domain_review_task(
        prepared["domain_input"],
        args["artifact"],
        review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _canonical_prepare(args: dict):
    return canonical.prepare_canonical(
        args["research_plan_ref"],
        args["domain_candidates_ref"],
        args["topic_id"],
        config_path=args.get("config"),
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )


def _citation_expand(args: dict):
    return citations.expand_citations(
        args["discovery_input"],
        seed_source_id=args["seed_source_id"],
        provider=args["provider"],
        relation=args["relation"],
        cursor=args.get("cursor"),
        limit=args.get("limit"),
        config_path=args.get("config"),
    )


def _recent_prepare(args: dict):
    return recent.prepare_recent(
        args["research_plan_ref"], args["domain_candidates_ref"], args["topic_id"],
        config_path=args.get("config"),
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )


def _recent_finalize(args: dict):
    prepared = recent.prepare_recent(
        args["research_plan_ref"], args["domain_candidates_ref"], args["topic_id"],
        config_path=args.get("config"),
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return recent.finalize_recent_candidates(
        prepared["recent_input"], args["output"],
        previous_candidates=prepared["previous_candidates"],
        revision_items=prepared["revision_items"],
    )


def _recent_review_task(args: dict):
    prepared = recent.prepare_recent(
        args["research_plan_ref"], args["domain_candidates_ref"], args["topic_id"],
        config_path=args.get("config"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return recent.build_recent_review_task(
        prepared["recent_input"], args["artifact"], review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _market_cases_prepare(args: dict):
    return market_cases.prepare_market_cases(
        args["research_plan_ref"], args["domain_candidates_ref"], args["topic_id"],
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )


def _web_case_search(args: dict):
    return web_cases.search_web_cases(
        args["query_plan"], args["market_case_input"],
        route_id=args["route_id"], provider=args["provider"],
        cursor=args.get("cursor"),
    )


def _market_cases_finalize(args: dict):
    prepared = market_cases.prepare_market_cases(
        args["research_plan_ref"], args["domain_candidates_ref"], args["topic_id"],
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return market_cases.finalize_market_case_candidates(
        prepared["market_case_input"], args["output"],
        previous_candidates=prepared["previous_candidates"],
        revision_items=prepared["revision_items"],
    )


def _market_cases_review_task(args: dict):
    prepared = market_cases.prepare_market_cases(
        args["research_plan_ref"], args["domain_candidates_ref"], args["topic_id"],
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return market_cases.build_market_case_review_task(
        prepared["market_case_input"], args["artifact"], review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _candidate_index_prepare(args: dict):
    return candidate_index.prepare_candidate_index(
        args["research_plan_ref"], args["reviewed_upstreams"],
        selection_profile=args.get("selection_profile"),
        previous_index_ref=args.get("previous_index_ref"),
        search_extension_refs=args.get("search_extension_refs"),
    )


def _candidate_index_finalize(args: dict):
    prepared = candidate_index.prepare_candidate_index(
        args["research_plan_ref"], args["reviewed_upstreams"],
        selection_profile=args.get("selection_profile"),
        previous_index_ref=args.get("previous_index_ref"),
        search_extension_refs=args.get("search_extension_refs"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return candidate_index.finalize_candidate_index(
        prepared["candidate_index_input"], artifact_version=args.get("artifact_version", "1.0.0")
    )


def _candidate_index_review_task(args: dict):
    prepared = candidate_index.prepare_candidate_index(
        args["research_plan_ref"], args["reviewed_upstreams"],
        selection_profile=args.get("selection_profile"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return candidate_index.build_candidate_index_review_task(
        prepared["candidate_index_input"], args["artifact"], review_id=args["review_id"],
        attempt=args.get("attempt", 1), previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _source_selection_prepare(args: dict):
    return source_selection.prepare_source_selection(args["candidate_source_index_ref"])


def _source_selection_validate(args: dict):
    return source_selection.validate_source_selection(
        args["candidate_source_index_ref"], selection=args.get("selection"),
        response_text=args.get("response_text"),
    )


def _source_selection_finalize(args: dict):
    return source_selection.finalize_source_selection(
        args["candidate_source_index_ref"], args["selection"],
        args["confirmation_token"],
    )


def _retrieval_prepare(args: dict):
    return retrieval.prepare_retrieval(
        args["approved_source_set_ref"],
        previous_corpus_ref=args.get("previous_corpus_ref"),
    )


def _oa_resolve(args: dict):
    return oa_retrieval.resolve_open_access(
        args["retrieval_input"], args["source_id"]
    )


def _document_retrieve(args: dict):
    return oa_retrieval.retrieve_document(
        args["retrieval_input"], args["resolution_ref"]
    )


def _document_validate(args: dict):
    return oa_retrieval.validate_document(
        args["retrieval_input"], args["retrieved_file_ref"],
    )


def _retrieval_finalize(args: dict):
    prepared = retrieval.prepare_retrieval(
        args["approved_source_set_ref"],
        previous_corpus_ref=args.get("previous_corpus_ref"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return retrieval.finalize_retrieval(
        prepared["retrieval_input"], args["result_refs"],
        artifact_version=args.get("artifact_version", "1.0.0"),
    )


def _retrieval_review_task(args: dict):
    prepared = retrieval.prepare_retrieval(args["approved_source_set_ref"])
    if not prepared["ready"]:
        return prepared["envelope"]
    return retrieval.build_retrieval_review_task(
        prepared["retrieval_input"], args["artifact"], review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _web_case_extract(args: dict):
    return web_cases.extract_web_case(
        args["selection_ref"], args["candidate_sources_ref"], args["source_id"],
    )


def _paper_review_prepare(args: dict):
    return paper_review.prepare_paper_review(
        args["retrieved_corpus_ref"],
        args["source_id"],
        research_plan_ref=args.get("research_plan_ref"),
        candidate_source_index_ref=args.get("candidate_source_index_ref"),
        text_index_ref=args.get("text_index_ref"),
        previous_review_ref=args.get("previous_review_ref"),
        revision_items=args.get("revision_items"),
    )


def _document_text_index(args: dict):
    return paper_review.build_document_text_index(
        args["retrieved_corpus_ref"],
        args["source_id"],
        research_plan_ref=args.get("research_plan_ref"),
        candidate_source_index_ref=args.get("candidate_source_index_ref"),
    )


def _document_text_window(args: dict):
    return paper_review.document_text_window(
        args["text_index_ref"],
        section_ids=args.get("section_ids"),
        query_terms=args.get("query_terms"),
        max_chars=args.get("max_chars", 1600),
    )


def _paper_review_finalize(args: dict):
    prepared = paper_review.prepare_paper_review(
        args["retrieved_corpus_ref"],
        args["source_id"],
        research_plan_ref=args.get("research_plan_ref"),
        candidate_source_index_ref=args.get("candidate_source_index_ref"),
        text_index_ref=args.get("text_index_ref"),
        previous_review_ref=args.get("previous_review_ref"),
        revision_items=args.get("revision_items"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return paper_review.finalize_paper_review(
        prepared["paper_review_input"],
        args["output"],
        artifact_version=args.get("artifact_version", "1.0.0"),
    )


def _paper_review_task(args: dict):
    prepared = paper_review.prepare_paper_review(
        args["retrieved_corpus_ref"],
        args["source_id"],
        research_plan_ref=args.get("research_plan_ref"),
        candidate_source_index_ref=args.get("candidate_source_index_ref"),
        text_index_ref=args.get("text_index_ref"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return paper_review.build_paper_review_task(
        prepared["paper_review_input"],
        args["artifact"],
        review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _synthesis_prepare(args: dict):
    return synthesis.prepare_synthesis(
        args["research_plan_ref"],
        args["candidate_source_index_ref"],
        args["approved_source_set_ref"],
        args["retrieved_corpus_ref"],
        args["paper_review_refs"],
        profile=args.get("profile"),
        reviewed_paper_reviews=args.get("reviewed_paper_reviews"),
        previous_state_ref=args.get("previous_state_ref"),
        revision_items=args.get("revision_items"),
    )


def _synthesis_finalize(args: dict):
    prepared = synthesis.prepare_synthesis(
        args["research_plan_ref"],
        args["candidate_source_index_ref"],
        args["approved_source_set_ref"],
        args["retrieved_corpus_ref"],
        args["paper_review_refs"],
        profile=args.get("profile"),
        reviewed_paper_reviews=args.get("reviewed_paper_reviews"),
        previous_state_ref=args.get("previous_state_ref"),
        revision_items=args.get("revision_items"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return synthesis.finalize_synthesis(
        prepared["synthesis_input"],
        args["output"],
        artifact_version=args.get("artifact_version", "1.0.0"),
    )


def _synthesis_review_task(args: dict):
    prepared = synthesis.prepare_synthesis(
        args["research_plan_ref"],
        args["candidate_source_index_ref"],
        args["approved_source_set_ref"],
        args["retrieved_corpus_ref"],
        args["paper_review_refs"],
        profile=args.get("profile"),
        reviewed_paper_reviews=args.get("reviewed_paper_reviews"),
        previous_state_ref=args.get("previous_state_ref"),
        revision_items=args.get("revision_items"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return synthesis.build_synthesis_review_task(
        prepared["synthesis_input"],
        args["artifact"],
        review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _bundle_finalize(args: dict):
    return synthesis.finalize_research_bundle(
        args["research_state_ref"],
        args["decision"],
        artifact_version=args.get("artifact_version", "1.0.0"),
    )


def _canonical_finalize(args: dict):
    prepared = canonical.prepare_canonical(
        args["research_plan_ref"],
        args["domain_candidates_ref"],
        args["topic_id"],
        config_path=args.get("config"),
        previous_candidates_ref=args.get("previous_candidates_ref"),
        revision_items=args.get("revision_items"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return canonical.finalize_canonical_candidates(
        prepared["canonical_input"],
        args["output"],
        previous_candidates=prepared["previous_candidates"],
        revision_items=prepared["revision_items"],
    )


def _canonical_review_task(args: dict):
    prepared = canonical.prepare_canonical(
        args["research_plan_ref"],
        args["domain_candidates_ref"],
        args["topic_id"],
        config_path=args.get("config"),
    )
    if not prepared["ready"]:
        return prepared["envelope"]
    return canonical.build_canonical_review_task(
        prepared["canonical_input"],
        args["artifact"],
        review_id=args["review_id"],
        attempt=args.get("attempt", 1),
        previous_decision_ref=args.get("previous_decision_ref"),
        producer_revision_response=args.get("producer_revision_response"),
    )


def _run_stub(args: dict):
    return rf.run(rf.front_door(args["context"])["ref"])


def _scout_fanout(args: dict):
    return scout_fanout.run_scout_fanout(
        args["research_plan_ref"],
        workspace=args.get("workspace"),
        total_target=args.get("total_target"),
        max_workers=args.get("max_workers"),
    )


def _scout_a07_prepare(args: dict):
    return scout_a07_bridge.build_scout_a07_reviews(
        args["scout_run_dir"],
        output_dir=args.get("output_dir"),
        intake_ref=args.get("intake_ref"),
        max_windows_per_source=args.get("max_windows_per_source", 5),
        max_scan_pages=args.get("max_scan_pages", 16),
    )


def _scout_a07_tasks_prepare(args: dict):
    return scout_a07_runner.write_scout_a07_model_tasks(
        args["a07_dir"],
        output_dir=args.get("output_dir"),
        intake=args.get("intake"),
        topic_ids=args.get("topic_ids"),
        source_ids=args.get("source_ids"),
        include_context_only=args.get("include_context_only", True),
        limit=args.get("limit"),
    )


def _scout_a07_partial_finalize(args: dict):
    return scout_a07_bridge.finalize_scout_a07_partial(
        args["work_input_path"],
        args["output"],
        output_path=args.get("output_path"),
        artifact_version=args.get("artifact_version", "1.0.0"),
    )


def _scout_a07_aggregate(args: dict):
    return scout_a07_bridge.aggregate_scout_a07_reviews(args["a07_dir"])


def _scout_synthesis_prepare(args: dict):
    return scout_synthesis.prepare_scout_fast_synthesis(
        args["reviews_json"],
        intake=args.get("intake"),
        max_deep_dive_sources=args.get("max_deep_dive_sources", 5),
    )


def _scout_deep_dive_windows(args: dict):
    prepared = scout_synthesis.prepare_scout_fast_synthesis(
        args["reviews_json"],
        intake=args.get("intake"),
        max_deep_dive_sources=args.get("max_deep_dive_sources", 5),
    )
    synthesis_input = prepared["synthesis_input"]
    return scout_synthesis.gather_deep_dive_windows(
        synthesis_input["reviews"],
        synthesis_input["deep_dive_requests"],
        max_windows=args.get("max_windows", 12),
        max_chars=args.get("max_chars", 1800),
    )


def _scout_a09_task_prepare(args: dict):
    built = scout_a09_runner.build_a09_task(
        args["reviews_json"],
        intake=args.get("intake"),
        max_deep_dive_sources=args.get("max_deep_dive_sources", 5),
        deep_dive_windows=args.get("deep_dive_windows", 8),
        deep_dive_chars=args.get("deep_dive_chars", 1200),
    )
    return {
        "task": built["task"],
        "deep_dive": built["deep_dive"],
    }


def _scout_synthesis_finalize(args: dict):
    prepared = scout_synthesis.prepare_scout_fast_synthesis(
        args["reviews_json"],
        intake=args.get("intake"),
        max_deep_dive_sources=args.get("max_deep_dive_sources", 5),
    )
    return scout_synthesis.finalize_scout_fast_solution(
        prepared["synthesis_input"],
        args.get("output"),
        deep_dive=args.get("deep_dive"),
        artifact_version=args.get("artifact_version", "1.0.0"),
        output_path=args.get("output_path"),
    )


def _run_codex(args: dict):
    """Run or resume the graph through Codex workers.

    MCP tools are not an interactive stdin surface, so the default gate behavior is pause/resume.
    Human approval is never simulated in the reviewed runner. Use research_run_stub for a no-op
    wiring smoke that intentionally auto-approves its synthetic gates.
    """
    from runners.codex import codex_node_runner

    gates = args.get("gates", "pause")
    if gates != "pause":
        raise ValueError("reviewed Codex runs require gates='pause'")

    resume_token = args.get("resume_token")
    decisions = args.get("decisions")
    if resume_token:
        return rf.run(
            None,
            node_runner=codex_node_runner,
            pause_on_gate=True,
            resume_token=resume_token,
            decisions=decisions,
            reviewed=True,
            through=args.get("through", "g02-a09-synthesizer"),
            topic_ids=args.get("topic_ids"),
        )

    context = args.get("context")
    if not context:
        raise ValueError("context is required when resume_token is absent")
    ref = rf.front_door(context)["ref"]
    return rf.run(
        ref,
        node_runner=codex_node_runner,
        pause_on_gate=True,
        reviewed=True,
        through=args.get("through", "g02-a09-synthesizer"),
        topic_ids=args.get("topic_ids"),
    )


def _run_hosted(args: dict):
    """Start a HOST-DRIVEN reviewed g02 run (no nested codex). Each producer/reviewer yields
    awaiting_node/awaiting_review; the host plays it (calling the node's finalize op) and resumes."""
    context = args.get("context")
    if not context:
        raise ValueError("context is required")
    ref = rf.front_door(context)["ref"]
    return rf.run(ref, reviewed=True, pause_on_node=True, pause_on_gate=True,
                  through=args.get("through", "g02-a09-synthesizer"),
                  topic_ids=args.get("topic_ids"))


def _resume(args: dict):
    """Resume a host-driven run. Producers resume with node_results={node: finalize_envelope};
    reviewers with review_results={node: review_finalize_envelope}; gates with decisions; a node the
    host cannot produce with node_failures. Optional usage_reports={node: {input_tokens,
    output_tokens, model}} carries the model tokens only the host knows (token tracing for Claude)."""
    return rf.run(None, reviewed=True, pause_on_node=True, pause_on_gate=True,
                  resume_token=args["resume_token"],
                  node_results=args.get("node_results"), node_failures=args.get("node_failures"),
                  review_results=args.get("review_results"), decisions=args.get("decisions"),
                  usage_reports=args.get("usage_reports"),
                  through=args.get("through", "g02-a09-synthesizer"),
                  topic_ids=args.get("topic_ids"))


def _trace(args: dict):
    from core import event_log
    return event_log.open_log(f"{rf.GRAPH_ID}-reviewed", run_id=args["run_id"]).summary()


TOOLS = [
    {
        "name": "research_front_door",
        "description": "Validate a research_graph_input bundle against research_graph_input@1 "
                       "and register it in the artifact store. Returns {ref, task_id}. "
                       "Fail-fast on invalid input. Call this first.",
        "inputSchema": {
            "type": "object",
            "properties": {"context": {"type": "string",
                           "description": "path or artifact:// ref to a research_graph_input bundle"}},
            "required": ["context"],
        },
    },
    {
        "name": "research_node_input",
        "description": "Preview boundary-only no-op harness inputs, or one via 'node'. G02-A01 is "
                       "fully scoped here; dependency-based nodes use their dedicated prepare "
                       "operation, beginning with research_domain_prepare for G02-A02.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string", "description": "ref from research_front_door"},
                           "node": {"type": "string", "description": "optional single node name"}},
            "required": ["ref"],
        },
    },
    {
        "name": "research_planner_prepare",
        "description": "Validate and scope research_graph_input@1 for G02-A01 Planner. For a "
                       "revision, also validate and hydrate only the named previous ResearchPlan. "
                       "Returns the isolated research_planner_input@1 plus an exact "
                       "plan_output_template, or a completed failure envelope without invoking "
                       "an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": ["object", "string"],
                    "description": "Research Graph input object, path or artifact:// ref"
                },
                "previous_plan_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
                "execution_profile": {"type": "string", "enum": ["fast", "scout"]},
            },
            "required": ["input"],
        },
    },
    {
        "name": "research_planner_finalize",
        "description": "Validate a G02-A01 ResearchPlan against its scoped approved input, "
                       "persist a valid research_plan@1 and return envelope@1. Supports minimal "
                       "revision checks when previous_plan_ref and revision_items are supplied.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": ["object", "string"],
                    "description": "Research Graph or scoped planner input object, path or ref"
                },
                "plan": {"type": "object"},
                "previous_plan_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
                "execution_profile": {"type": "string", "enum": ["fast", "scout"]},
            },
            "required": ["input", "plan"],
        },
    },
    {
        "name": "research_plan_review_task",
        "description": "Freeze the research_plan review profile and build one review_task@1 "
                       "for a persisted G02-A01 artifact descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": ["object", "string"],
                    "description": "Research Graph or scoped planner input object, path or ref"
                },
                "artifact": {
                    "type": "object",
                    "description": "Persisted research_plan descriptor from finalize; use ref, not artifact_ref.",
                    "required": ["type", "ref", "schema_version", "artifact_version"],
                    "properties": {
                        "type": {"type": "string", "enum": ["research_plan"]},
                        "ref": {"type": "string", "description": "artifact:// research_plan ref"},
                        "schema_version": {"type": "string", "enum": ["research_plan@1"]},
                        "artifact_version": {"type": "string"}
                    }
                },
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
                "execution_profile": {"type": "string", "enum": ["fast", "scout"]},
            },
            "required": ["input", "artifact", "review_id"],
        },
    },
    {
        "name": "research_provider_status",
        "description": "Validate the G02 provider configuration at startup and return a "
                       "secret-free capability report for OpenAlex, Semantic Scholar and "
                       "arXiv. No provider request is made.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "config": {"type": "string", "description": "optional provider config path"},
            },
        },
    },
    {
        "name": "research_domain_prepare",
        "description": "Hydrate one approved ResearchPlan topic for G02-A02, validate provider "
                       "startup configuration and return domain_research_input@1 with only "
                       "secret-free provider capabilities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "config": {"type": "string"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "topic_id"],
        },
    },
    {
        "name": "research_query_plan_generate_fast",
        "description": "Generate and validate a bounded provider-neutral scholarly query plan "
                       "for the common fast A02/A03/A04 path. Returns a structured gap without "
                       "making provider calls when deterministic generation is unsafe.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "discovery_input": {"type": "object"},
                "profile": {"type": "object"},
                "execution_profile": {"type": "string"},
            },
            "required": ["discovery_input"],
        },
    },
    {
        "name": "research_metadata_search",
        "description": "Execute exactly one authorized QueryPlan route for G02-A02, G02-A03 or "
                       "G02-A04 against one configured scholarly provider. Supply exactly one "
                       "of domain_input, canonical_input or recent_input. The deterministic "
                       "adapter applies limits, retry, caching, normalization and provenance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_plan": {"type": "object"},
                "domain_input": {"type": "object"},
                "canonical_input": {"type": "object"},
                "recent_input": {"type": "object"},
                "route_id": {"type": "string"},
                "provider": {
                    "type": "string",
                    "enum": ["openalex", "semantic_scholar", "arxiv"],
                },
                "cursor": {"type": "string"},
                "config": {"type": "string"},
            },
            "required": ["query_plan", "route_id", "provider"],
        },
    },
    {
        "name": "research_doi_verify",
        "description": "Verify one unchanged source_record@1 DOI and bibliographic identity "
                       "through the configured deterministic Crossref adapter. Returns one "
                       "persisted doi_verification_result@1 with field comparisons and raw "
                       "provenance; it never overwrites provider metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {"source_record": {"type": "object"}},
            "required": ["source_record"],
        },
    },
    {
        "name": "research_doi_verify_batch",
        "description": "Verify a bounded array of unchanged source_record@1 values through "
                       "Crossref while reusing the deterministic cache.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_records": {"type": "array", "items": {"type": "object"},
                                   "maxItems": 60}
            },
            "required": ["source_records"],
        },
    },
    {
        "name": "research_domain_finalize",
        "description": "Validate G02-A02 output against its approved topic and every persisted "
                       "provider result, then store domain_candidate_sources@1 and return "
                       "envelope@1. Supports bounded revision of one previous artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "output": {"type": "object"},
                "config": {"type": "string"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "topic_id", "output"],
        },
    },
    {
        "name": "research_domain_review_task",
        "description": "Freeze the domain_candidates review profile and build one "
                       "review_task@1 for a persisted G02-A02 artifact descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
                "config": {"type": "string"},
            },
            "required": ["research_plan_ref", "topic_id", "artifact", "review_id"],
        },
    },
    {
        "name": "research_canonical_prepare",
        "description": "Hydrate one approved ResearchPlan topic and its reviewed G02-A02 "
                       "DomainCandidateSources, then return canonical_research_input@1 with "
                       "verified provider-resolvable seeds, canonical roles, target coverage, "
                       "bounded citation limits and secret-free capabilities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "domain_candidates_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "config": {"type": "string"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "domain_candidates_ref", "topic_id"],
        },
    },
    {
        "name": "research_citation_expand",
        "description": "Execute one authorized one-hop citation relation for a verified A03 or "
                       "A04 seed. OpenAlex supports cited_by; Semantic Scholar supports "
                       "references, cited_by and recommendations. The result is persisted as "
                       "literature_tool_result@1 with normalized source_record@1 values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "discovery_input": {"type": "object"},
                "seed_source_id": {"type": "string"},
                "provider": {
                    "type": "string",
                    "enum": ["openalex", "semantic_scholar", "arxiv"],
                },
                "relation": {
                    "type": "string",
                    "enum": ["references", "cited_by", "recommendations"],
                },
                "cursor": {"type": "string"},
                "limit": {"type": "integer"},
                "config": {"type": "string"},
            },
            "required": ["discovery_input", "seed_source_id", "provider", "relation", "limit"],
        },
    },
    {
        "name": "research_canonical_finalize",
        "description": "Validate G02-A03 output against its scoped canonical input, reviewed "
                       "domain records and every persisted metadata or citation result, then "
                       "store canonical candidate_sources@1 and return envelope@1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "domain_candidates_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "output": {"type": "object"},
                "config": {"type": "string"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "domain_candidates_ref", "topic_id", "output"],
        },
    },
    {
        "name": "research_canonical_review_task",
        "description": "Freeze the canonical_sources review profile and build one "
                       "review_task@1 for a persisted G02-A03 canonical artifact descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "domain_candidates_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
                "config": {"type": "string"},
            },
            "required": ["research_plan_ref", "domain_candidates_ref", "topic_id", "artifact", "review_id"],
        },
    },
    {
        "name": "research_recent_prepare",
        "description": "Hydrate one approved current-source topic and reviewed A02 pool, derive "
                       "the exact calendar window from intake recency_window_years, and return "
                       "secret-free recent_research_input@1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "domain_candidates_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "config": {"type": "string"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "domain_candidates_ref", "topic_id"],
        },
    },
    {
        "name": "research_recent_finalize",
        "description": "Validate G02-A04 output against its intake-derived recency window, "
                       "reviewed A02 records and persisted search operations, then store the "
                       "recent candidate_sources@1 stream and return envelope@1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "domain_candidates_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "output": {"type": "object"},
                "config": {"type": "string"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "domain_candidates_ref", "topic_id", "output"],
        },
    },
    {
        "name": "research_recent_review_task",
        "description": "Freeze RD-01 through RD-06 and build one recent_developments "
                       "review_task@1 for a persisted G02-A04 artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "domain_candidates_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
                "config": {"type": "string"},
            },
            "required": ["research_plan_ref", "domain_candidates_ref", "topic_id", "artifact", "review_id"],
        },
    },
    {
        "name": "research_market_cases_prepare",
        "description": "Project one approved topic and reviewed A02 identity into the minimal "
                       "market_case_research_input@1, including traceable case needs, bounded "
                       "web routes, administrator tier policy and secret-free provider status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "domain_candidates_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "domain_candidates_ref", "topic_id"],
        },
    },
    {
        "name": "research_web_case_search",
        "description": "Execute one authorized A11 query route through the configured Tavily, "
                       "administrator-pinned SearXNG or auto_budgeted mode. Applies endpoint and "
                       "redirect controls, JSON-only responses, budgets, cache, timeout, rate "
                       "limits, source tiers, normalized records and full provenance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_plan": {"type": "object"},
                "market_case_input": {"type": "object"},
                "route_id": {"type": "string"},
                "provider": {
                    "type": "string", "enum": ["tavily", "searxng", "auto_budgeted"],
                },
                "cursor": {"type": "string"},
            },
            "required": ["query_plan", "market_case_input", "route_id", "provider"],
        },
    },
    {
        "name": "research_market_cases_finalize",
        "description": "Validate unchanged provider-backed market-case records, scoped web "
                       "operation refs, separate semantic annotations, materiality, tiering and "
                       "coverage, then persist the market_cases candidate_sources@1 stream.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "domain_candidates_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "output": {"type": "object"},
                "previous_candidates_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["research_plan_ref", "domain_candidates_ref", "topic_id", "output"],
        },
    },
    {
        "name": "research_market_cases_review_task",
        "description": "Freeze MC-01 through MC-06 and build one market_cases review_task@1 "
                       "for a persisted G02-A11 candidate artifact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "domain_candidates_ref": {"type": "string"},
                "topic_id": {"type": "string"},
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
            },
            "required": ["research_plan_ref", "domain_candidates_ref", "topic_id", "artifact", "review_id"],
        },
    },
    {
        "name": "research_web_case_extract",
        "description": "Extract one exact HTTPS market-case URL through Tavily only after a "
                       "persisted, final human_source_selection@1 approves that source for "
                       "download. Returns a bounded untrusted-content artifact descriptor and "
                       "prompt-injection flags, never page text inline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selection_ref": {"type": "string"},
                "candidate_sources_ref": {"type": "string"},
                "source_id": {"type": "string"},
            },
            "required": ["selection_ref", "candidate_sources_ref", "source_id"],
        },
    },
    {
        "name": "research_candidate_index_prepare",
        "description": "Hydrate the exact ResearchPlan plus APPROVED A02, A03, A04 and A11 "
                       "artifacts, verify each review binding and project candidate_index_input@1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "reviewed_upstreams": {"type": "array", "items": {"type": "object"}},
                "selection_profile": {"type": "object"},
                "previous_index_ref": {"type": "string"},
                "search_extension_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["research_plan_ref", "reviewed_upstreams"],
        },
    },
    {
        "name": "research_candidate_index_finalize",
        "description": "Deterministically deduplicate and rank reviewed candidates, create "
                       "basis-labelled content descriptions and persist CandidateSourceIndex "
                       "plus candidate_source_review.md for the human gate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "reviewed_upstreams": {"type": "array", "items": {"type": "object"}},
                "selection_profile": {"type": "object"},
                "previous_index_ref": {"type": "string"},
                "search_extension_refs": {"type": "array", "items": {"type": "string"}},
                "artifact_version": {"type": "string"},
            },
            "required": ["research_plan_ref", "reviewed_upstreams"],
        },
    },
    {
        "name": "research_candidate_index_review_task",
        "description": "Freeze CI-01 through CI-08 and build one candidate_index review_task@1 "
                       "for a persisted G02-A05 index descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "reviewed_upstreams": {"type": "array", "items": {"type": "object"}},
                "selection_profile": {"type": "object"},
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
            },
            "required": ["research_plan_ref", "reviewed_upstreams", "artifact", "review_id"],
        },
    },
    {
        "name": "research_source_selection_prepare",
        "description": "Load the reviewed CandidateSourceIndex and its Markdown document, then "
                       "return content cards, gaps, exact IDs and the user-facing action template.",
        "inputSchema": {
            "type": "object",
            "properties": {"candidate_source_index_ref": {"type": "string"}},
            "required": ["candidate_source_index_ref"],
        },
    },
    {
        "name": "research_source_selection_validate",
        "description": "Parse the copyable response template or validate a host-mapped natural "
                       "language decision, enforce IDs, actions and coverage, and return the exact "
                       "summary plus a confirmation token. This operation never authorizes retrieval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_source_index_ref": {"type": "string"},
                "selection": {"type": "object"},
                "response_text": {"type": "string"},
            },
            "required": ["candidate_source_index_ref"],
        },
    },
    {
        "name": "research_source_selection_finalize",
        "description": "After the user sees and separately confirms the parsed summary, validate "
                       "the confirmation token and persist human_source_selection@1 plus the exact "
                       "human_approved_source_set@1 consumed by A06.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_source_index_ref": {"type": "string"},
                "selection": {"type": "object"},
                "confirmation_token": {"type": "string"},
            },
            "required": ["candidate_source_index_ref", "selection", "confirmation_token"],
        },
    },
    {
        "name": "research_retrieval_prepare",
        "description": "Hydrate one finally confirmed HumanApprovedSourceSet and project the "
                       "minimal retrieval_input@1 with DOWNLOAD records, skipped actions, legal OA "
                       "policy and secret-free provider capabilities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "approved_source_set_ref": {"type": "string"},
                "previous_corpus_ref": {"type": "string"},
            },
            "required": ["approved_source_set_ref"],
        },
    },
    {
        "name": "research_oa_resolve",
        "description": "Resolve one approved source through record links, Unpaywall, optional CORE, "
                       "DOAB and OAPEN. Market cases are routed to gated A11 extraction. Returns an "
                       "auditable open_access_resolution@1 without downloading a document.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "retrieval_input": {"type": "object"},
                "source_id": {"type": "string"},
            },
            "required": ["retrieval_input", "source_id"],
        },
    },
    {
        "name": "research_document_retrieve",
        "description": "Download one scholarly document from the selected legal OA resolution "
                       "under HTTPS, redirect, timeout, retry and byte limits into a temporary "
                       "corpus ref. It does not accept the file into RetrievedCorpus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "retrieval_input": {"type": "object"},
                "resolution_ref": {"type": "string"},
            },
            "required": ["retrieval_input", "resolution_ref"],
        },
    },
    {
        "name": "research_document_validate",
        "description": "Validate the temporary file's checksum, content type, PDF signature and "
                       "resolver-backed source identity, then promote an accepted file under a "
                       "stable corpus ref or record a duplicate/rejection.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "retrieval_input": {"type": "object"},
                "retrieved_file_ref": {"type": "string"},
            },
            "required": ["retrieval_input", "retrieved_file_ref"],
        },
    },
    {
        "name": "research_retrieval_finalize",
        "description": "Re-prepare exact authorization, partition validated scholarly files and "
                       "gated A11 market-case extraction results, render each accepted market case "
                       "as readable Markdown plus a separate JSON audit artifact, and persist both "
                       "with validated PDFs in retrieved_corpus@1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "approved_source_set_ref": {"type": "string"},
                "result_refs": {"type": "array", "items": {"type": "string"}},
                "previous_corpus_ref": {"type": "string"},
                "artifact_version": {"type": "string"},
            },
            "required": ["approved_source_set_ref", "result_refs"],
        },
    },
    {
        "name": "research_retrieval_review_task",
        "description": "Validate files and authorization, freeze RT-01 through RT-08 and build "
                       "one retrieved_corpus review_task@1 for G02-A10.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "approved_source_set_ref": {"type": "string"},
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
            },
            "required": ["approved_source_set_ref", "artifact", "review_id"],
        },
    },
    {
        "name": "research_paper_review_prepare",
        "description": "Prepare one source-scoped G02-A07 input from RetrievedCorpus, build or "
                       "reuse a deterministic text index and provide bounded suggested windows.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "retrieved_corpus_ref": {"type": "string"},
                "source_id": {"type": "string"},
                "research_plan_ref": {"type": "string"},
                "candidate_source_index_ref": {"type": "string"},
                "text_index_ref": {"type": "string"},
                "previous_review_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["retrieved_corpus_ref", "source_id"],
        },
    },
    {
        "name": "research_document_text_index",
        "description": "Create a deterministic section map for one accepted PDF or market-case "
                       "bundle and store only bounded snippets, identity and location metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "retrieved_corpus_ref": {"type": "string"},
                "source_id": {"type": "string"},
                "research_plan_ref": {"type": "string"},
                "candidate_source_index_ref": {"type": "string"},
            },
            "required": ["retrieved_corpus_ref", "source_id"],
        },
    },
    {
        "name": "research_document_text_window",
        "description": "Return one bounded text window from a deterministic text index by "
                       "section IDs or query terms. It never returns full PDF or full page text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text_index_ref": {"type": "string"},
                "section_ids": {"type": "array", "items": {"type": "string"}},
                "query_terms": {"type": "array", "items": {"type": "string"}},
                "max_chars": {"type": "integer"},
            },
            "required": ["text_index_ref"],
        },
    },
    {
        "name": "research_paper_review_finalize",
        "description": "Validate source identity, locations, prompt-injection flags and compact "
                       "size, then persist one paper_review@1 for a single accepted source.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "retrieved_corpus_ref": {"type": "string"},
                "source_id": {"type": "string"},
                "research_plan_ref": {"type": "string"},
                "candidate_source_index_ref": {"type": "string"},
                "text_index_ref": {"type": "string"},
                "previous_review_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
                "output": {"type": "object"},
                "artifact_version": {"type": "string"},
            },
            "required": ["retrieved_corpus_ref", "source_id", "output"],
        },
    },
    {
        "name": "research_paper_review_task",
        "description": "Build the G02-A07 paper_evidence review_task@1 for A10 conditional review.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "retrieved_corpus_ref": {"type": "string"},
                "source_id": {"type": "string"},
                "research_plan_ref": {"type": "string"},
                "candidate_source_index_ref": {"type": "string"},
                "text_index_ref": {"type": "string"},
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
            },
            "required": ["retrieved_corpus_ref", "source_id", "artifact", "review_id"],
        },
    },
    {
        "name": "research_synthesis_prepare",
        "description": "Prepare the fast A09 synthesis input from reviewed A07 PaperReviews and "
                       "A01/A05/source-gate/A06 refs without requiring A08 ClaimAssessment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "candidate_source_index_ref": {"type": "string"},
                "approved_source_set_ref": {"type": "string"},
                "retrieved_corpus_ref": {"type": "string"},
                "paper_review_refs": {"type": "array", "items": {"type": "string"}},
                "reviewed_paper_reviews": {"type": "array", "items": {"type": "object"}},
                "previous_state_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
                "profile": {"type": "object"},
            },
            "required": [
                "research_plan_ref", "candidate_source_index_ref",
                "approved_source_set_ref", "retrieved_corpus_ref", "paper_review_refs"
            ],
        },
    },
    {
        "name": "research_synthesis_finalize",
        "description": "Persist research_state@1, compact evidence map, human validation packet "
                       "and SolutionInputCandidate while making the skipped A08 limitation explicit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "candidate_source_index_ref": {"type": "string"},
                "approved_source_set_ref": {"type": "string"},
                "retrieved_corpus_ref": {"type": "string"},
                "paper_review_refs": {"type": "array", "items": {"type": "string"}},
                "reviewed_paper_reviews": {"type": "array", "items": {"type": "object"}},
                "previous_state_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
                "profile": {"type": "object"},
                "output": {"type": "object"},
                "artifact_version": {"type": "string"},
            },
            "required": [
                "research_plan_ref", "candidate_source_index_ref",
                "approved_source_set_ref", "retrieved_corpus_ref",
                "paper_review_refs", "output"
            ],
        },
    },
    {
        "name": "research_synthesis_review_task",
        "description": "Build the mandatory G02-A09 research_synthesis review_task@1 for A10.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {"type": "string"},
                "candidate_source_index_ref": {"type": "string"},
                "approved_source_set_ref": {"type": "string"},
                "retrieved_corpus_ref": {"type": "string"},
                "paper_review_refs": {"type": "array", "items": {"type": "string"}},
                "reviewed_paper_reviews": {"type": "array", "items": {"type": "object"}},
                "previous_state_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
                "profile": {"type": "object"},
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
            },
            "required": [
                "research_plan_ref", "candidate_source_index_ref",
                "approved_source_set_ref", "retrieved_corpus_ref",
                "paper_review_refs", "artifact", "review_id"
            ],
        },
    },
    {
        "name": "research_bundle_finalize",
        "description": "After the Human Research Gate approves reviewed A09, validate and store "
                       "the compact user_approved_research_bundle@1 for Graph03.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_state_ref": {"type": "string"},
                "decision": {"type": "object"},
                "artifact_version": {"type": "string"},
            },
            "required": ["research_state_ref", "decision"],
        },
    },
    {
        "name": "research_review_prepare",
        "description": "Validate one complete review_task@1 returned unchanged from a stage "
                       "review-task builder, enforce one artifact and hydrate only that "
                       "artifact for the isolated universal reviewer. Invalid review basis or "
                       "unavailable artifact returns a completed BLOCKED decision envelope when "
                       "audit identity is available.",
        "inputSchema": {
            "type": "object",
            "properties": {"task": {"type": "object"}},
            "required": ["task"],
        },
    },
    {
        "name": "research_review_finalize",
        "description": "Validate one review_decision@1 against its ReviewTask, persist it and "
                       "return envelope@1 with one review_decision descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "object"},
                "decision": {"type": "object"},
            },
            "required": ["task", "decision"],
        },
    },
    {
        "name": "research_finalize",
        "description": "Validate a UserApprovedResearchBundle (inline object or path) against "
                       "user_approved_research_bundle@1 and emit it as the typed handoff. "
                       "Returns the handoff descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {"bundle": {
                "type": ["object", "string"],
                "description": "the bundle object, or a path to a JSON file"
            }},
            "required": ["bundle"],
        },
    },
    {
        "name": "research_scout_fanout",
        "description": "Run the dedicated deterministic Scout profile from one persisted "
                       "research_plan@1. Starts one process per topic, requires OPENALEX_API_KEY "
                       "from env, and persists plan, requests, PDFs, manifests, per-topic Scout "
                       "corpora and index.json. Does not run A07, A09, run or run-codex.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {
                    "type": "string",
                    "description": "Path or artifact:// ref to a finalized research_plan@1"
                },
                "workspace": {
                    "type": "string",
                    "description": "Optional exact Scout workspace; defaults under .emagents"
                },
                "total_target": {
                    "type": "integer",
                    "description": "Optional override; profile default is 50"
                },
                "max_workers": {"type": "integer"}
            },
            "required": ["research_plan_ref"]
        }
    },
    {
        "name": "research_scout_a07_prepare",
        "description": "Prepare bounded, parallel-safe A07 light-review work items from one "
                       "Scout run directory. Reads Scout plan, requests, index, topic corpora "
                       "and sampled PDF windows, then writes reviews.json plus immutable "
                       "work/<topic_id>/<source_id>.input.json files. Does not call an LLM.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scout_run_dir": {
                    "type": "string",
                    "description": "Path to outputs/g02/<task_id>/scout or a legacy Scout run dir"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Optional A07 output directory; defaults next to the Scout run"
                },
                "intake_ref": {
                    "type": "string",
                    "description": "Optional research_graph_input@1 path/ref used as presentation context"
                },
                "max_windows_per_source": {
                    "type": "integer",
                    "description": "Bounded PDF windows per source; default 5"
                },
                "max_scan_pages": {
                    "type": "integer",
                    "description": "Maximum sampled PDF pages before selecting windows; default 16"
                }
            },
            "required": ["scout_run_dir"]
        }
    },
    {
        "name": "research_scout_a07_tasks_prepare",
        "description": "Build compact scout_a07_model_task@1 JSON files from pending A07 work "
                       "items. Each task includes selected PDF windows and only the linked "
                       "intake context needed for one topic/source model review.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a07_dir": {
                    "type": "string",
                    "description": "Directory containing reviews.json and work/"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Optional task output directory; defaults to <a07_dir>/tasks"
                },
                "intake": {
                    "type": ["string", "object"],
                    "description": "Optional research_graph_input@1 path/ref/object; defaults to each work item's intake_ref"
                },
                "topic_ids": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "source_ids": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "include_context_only": {
                    "type": "boolean",
                    "description": "Whether to also prepare context_only sources; default true"
                },
                "limit": {"type": "integer"}
            },
            "required": ["a07_dir"]
        }
    },
    {
        "name": "research_scout_a07_partial_finalize",
        "description": "Validate and persist one A07 light-review worker result. The worker "
                       "must pass the immutable work input path and its JSON output; this tool "
                       "writes only partial/<topic_id>/<source_id>.review.json atomically.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "work_input_path": {
                    "type": "string",
                    "description": "Path to one work/<topic_id>/<source_id>.input.json file"
                },
                "output": {
                    "type": "object",
                    "description": "A07 worker JSON output with candidates, pointers, gaps and limitations"
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional exact destination for the partial review JSON"
                },
                "artifact_version": {
                    "type": "string",
                    "description": "Partial review artifact version; default 1.0.0"
                }
            },
            "required": ["work_input_path", "output"]
        }
    },
    {
        "name": "research_scout_a07_aggregate",
        "description": "Aggregate A07 partial review files into one scout_a07_reviews@1 "
                       "reviews.json without worker write contention.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a07_dir": {
                    "type": "string",
                    "description": "Directory containing reviews.json, work/ and partial/"
                }
            },
            "required": ["a07_dir"]
        }
    },
    {
        "name": "research_scout_synthesis_prepare",
        "description": "Prepare the Scout-fast A09 synthesis input from aggregated A07 reviews "
                       "and optional intake. Selects at most five bounded deep-dive source slots.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reviews_json": {
                    "type": "string",
                    "description": "Path or artifact ref to scout_a07_reviews@1"
                },
                "intake": {
                    "type": "string",
                    "description": "Optional research_graph_input@1 path/ref for presentation context"
                },
                "max_deep_dive_sources": {
                    "type": "integer",
                    "description": "Maximum bounded A09 deep-dive sources; hard cap 5"
                }
            },
            "required": ["reviews_json"]
        }
    },
    {
        "name": "research_scout_deep_dive_windows",
        "description": "Gather up to twelve bounded additional PDF windows for each of at most "
                       "five auditable A09 Scout deep-dive requests. Missing PDFs fail open with "
                       "an explicit limitation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reviews_json": {
                    "type": "string",
                    "description": "Path or artifact ref to scout_a07_reviews@1"
                },
                "intake": {
                    "type": "string",
                    "description": "Optional research_graph_input@1 path/ref"
                },
                "max_deep_dive_sources": {
                    "type": "integer",
                    "description": "Maximum selected source count; hard cap 5"
                },
                "max_windows": {
                    "type": "integer",
                    "description": "Maximum expanded windows per source; hard cap 12"
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters per expanded window; default 1800"
                }
            },
            "required": ["reviews_json"]
        }
    },
    {
        "name": "research_scout_a09_task_prepare",
        "description": "Build the obligatory scout_a09_model_task@1 for an Opus/medium "
                       "verification pass. The tool prepares the deterministic baseline and "
                       "bounded deep dive with at most five sources, eight windows per source "
                       "and 1200 characters per window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reviews_json": {
                    "type": "string",
                    "description": "Path or artifact ref to aggregated scout_a07_reviews@1"
                },
                "intake": {
                    "type": ["string", "object"],
                    "description": "Optional research_graph_input@1 path/ref/object for compact intake cards"
                },
                "max_deep_dive_sources": {
                    "type": "integer",
                    "description": "Maximum selected source count; hard cap 5"
                },
                "deep_dive_windows": {
                    "type": "integer",
                    "description": "Maximum windows per selected source; hard cap 8"
                },
                "deep_dive_chars": {
                    "type": "integer",
                    "description": "Maximum characters per window; hard cap 1200"
                }
            },
            "required": ["reviews_json"]
        }
    },
    {
        "name": "research_scout_synthesis_finalize",
        "description": "Finalize the Scout-fast A09 output as solution_input_candidate@1 for "
                       "Graph03. The final contract must contain concrete slide-update guidance; "
                       "Graph03 must not call back into G02.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reviews_json": {
                    "type": "string",
                    "description": "Path or artifact ref to scout_a07_reviews@1"
                },
                "intake": {
                    "type": "string",
                    "description": "Optional research_graph_input@1 path/ref for presentation context"
                },
                "output": {
                    "type": "object",
                    "description": "Raw g02-a09-scout-synthesis JSON with plan, priorities, optional improvements, unresolved items and confidence. Omit only after a failed or unavailable model attempt to request deterministic fallback."
                },
                "deep_dive": {
                    "type": "object",
                    "description": "Optional scout_a07_deep_dive@1 package returned by research_scout_deep_dive_windows"
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional destination path for solution_input_candidate@1"
                },
                "artifact_version": {
                    "type": "string",
                    "description": "Final artifact version; default 1.0.0"
                },
                "max_deep_dive_sources": {
                    "type": "integer",
                    "description": "Maximum bounded A09 deep-dive sources; hard cap 5"
                }
            },
            "required": ["reviews_json"]
        }
    },
    {
        "name": "research_run_stub",
        "description": "Run the whole Research Graph with STUB nodes (no LLM) — wiring test. "
                       "Returns the output handoff descriptor.",
        "inputSchema": {
            "type": "object",
            "properties": {"context": {"type": "string"}},
            "required": ["context"],
        },
    },
    {
        "name": "research_run_codex",
        "description": "Semantic entrypoint for 'zrob research', 'zrób research' or "
                       "'run research graph' in Codex. "
                       "Validate the input and run the fast reviewed frontier with isolated Codex "
                       "workers through reviewed A09, then pause at human gates. User gates always "
                       "use pause/resume because MCP tools cannot read interactive stdin.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": "Path or artifact:// ref to a research_graph_input bundle. "
                                   "Required unless resume_token is provided.",
                },
                "gates": {
                    "type": "string",
                    "enum": ["pause"],
                    "description": "Human gate handoff/resume mode (default and only reviewed mode).",
                },
                "resume_token": {
                    "type": "string",
                    "description": "Token from an awaiting_user response to resume a paused run.",
                },
                "decisions": {
                    "type": "object",
                    "description": "Gate decisions keyed by gate name when resuming.",
                },
                "through": {
                    "type": "string",
                    "enum": [
                        "g02-a01-planner", "g02-a02-domain", "g02-a03-canonical-sources",
                        "g02-a04-recent-developments", "g02-a11-market-cases",
                        "g02-a05-candidate-source-index", "user-source-selection-gate",
                        "g02-a06-paper-retrieval", "g02-a07-paper-review",
                        "g02-a09-synthesizer", "user-research-gate"
                    ],
                    "description": "Last implemented stage to execute; defaults to reviewed A09 and pauses at the Human Research Gate."
                },
                "topic_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional bounded topic subset; A05 requires the complete plan."
                },
            },
        },
    },
    {
        "name": "research_run_hosted",
        "description": "Start a HOST-DRIVEN reviewed g02 run (no nested codex exec). Each producer "
                       "yields {status:'awaiting_node', resume_token, node, input, upstream, "
                       "finalize_op, protocol}; play it (call its finalize op) and call "
                       "research_resume with node_results. Each reviewed producer then yields "
                       "{status:'awaiting_review', node, review_task, artifact_ref}; review it (call "
                       "research_review_finalize) and resume with review_results. Human gates yield "
                       "awaiting_user. Use this to drive g02 from a Claude/Codex session.",
        "inputSchema": {"type": "object", "required": ["context"],
                        "properties": {"context": {"type": "string",
                                                   "description": "path or artifact:// ref to a research_graph_input bundle"},
                                       "through": {"type": "string"},
                                       "topic_ids": {"type": "array", "items": {"type": "string"}}}},
    },
    {
        "name": "research_resume",
        "description": "Resume a host-driven g02 run with exactly one of: node_results={node: "
                       "finalize_envelope} (after playing a producer + its finalize op); "
                       "review_results={node: review_finalize_envelope} (after playing the reviewer "
                       "via research_review_finalize); node_failures={node: {summary, issues}}; or "
                       "decisions={gate: ...} for a human gate. Optional usage_reports={node: "
                       "{input_tokens, output_tokens, model}} records the model tokens only the host "
                       "knows (token tracing). Returns the next awaiting_* or the run report.",
        "inputSchema": {"type": "object", "required": ["resume_token"],
                        "properties": {"resume_token": {"type": "string"},
                                       "node_results": {"type": "object"},
                                       "review_results": {"type": "object"},
                                       "node_failures": {"type": "object"},
                                       "decisions": {"type": "object"},
                                       "usage_reports": {"type": "object",
                                                         "description": "{node: {input_tokens, output_tokens, model}} — omit if unavailable"},
                                       "through": {"type": "string"},
                                       "topic_ids": {"type": "array", "items": {"type": "string"}}}},
    },
    {
        "name": "research_trace",
        "description": "Return the trace summary for a run: per-agent/per-tool durations and per-node "
                       "token usage (input/output) rolled up, plus run totals. Pass the run's "
                       "resume_token as run_id.",
        "inputSchema": {"type": "object", "required": ["run_id"],
                        "properties": {"run_id": {"type": "string", "description": "the run's resume_token"}}},
    },
]

PROMPTS = [
    {
        "name": "research",
        "description": "Semantic 'zrob research' / 'zrób research' entrypoint for running the "
                       "Research Graph over an approved research_graph_input bundle.",
        "arguments": [
            {
                "name": "context",
                "description": "Path or artifact:// ref to a research_graph_input bundle.",
                "required": True,
            },
        ],
    },
    {
        "name": "research-scout",
        "description": "Run the bounded Claude-hosted A01 (Opus/medium) -> parallel Scout -> "
                       "persistent PDF/JSON workflow, stopping before A07.",
        "arguments": [
            {
                "name": "context",
                "description": "Path or artifact:// ref to a research_graph_input bundle.",
                "required": True,
            },
        ],
    },
    {
        "name": "research-scout-e2e",
        "description": "Run the Scout path through A07 light reviews and A09 scout_fast, producing "
                       "solution_input_candidate@1 for Graph03. Live Scout and host-model A07 are "
                       "still performed by the host environment.",
        "arguments": [
            {
                "name": "context",
                "description": "Path or artifact:// ref to a research_graph_input bundle.",
                "required": True,
            },
        ],
    },
]


def _research_prompt(context: str) -> dict:
    return {
        "description": "Semantic 'zrob research' entrypoint for a research_graph_input bundle.",
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        "The user asked to zrob research / zrób research. Use the "
                        "edu-materials-agents orchestrate-research workflow for this "
                        f"research_graph_input bundle: {context}\n\n"
                        "For the full Codex workflow, call research_run_codex with gates='pause' "
                        "so human gates return an awaiting_user resume token. For a deterministic "
                        "wiring check only, use research_run_stub."
                    ),
                },
            },
        ],
    }


def _research_scout_prompt(context: str) -> dict:
    return {
        "description": "Claude-hosted A01 → A10 review (max 1) → Scout workflow.",
        "messages": [{
            "role": "user",
            "content": {
                "type": "text",
                "text": (
                    "Run only the Edu Materials scout milestone for this research_graph_input: "
                    f"{context}\n\n"
                    "STEP 1 — Prepare: call research_planner_prepare with "
                    "execution_profile='scout'. This returns research_planner_input@1 and "
                    "plan_output_template.\n\n"
                    "STEP 2 — Plan (acting as g02-a01-planner, Opus/medium): create 4-6 "
                    "intake-anchored, bibliographically searchable topics following the "
                    "plan_output_template. Each topic must have a stable TOPIC_ID, 3-6 "
                    "core_terms and coverage units linked to approved drivers. Call "
                    "research_planner_finalize with input=<original research_graph_input>, "
                    "plan=<complete plan object> and execution_profile='scout'. The produced "
                    "research_plan descriptor uses path=<artifact:// ref>; retain that path "
                    "and artifact_version.\n\n"
                    "STEP 3 — Build review task: call research_plan_review_task with "
                    "input=<original research_graph_input>, "
                    "artifact={type:'research_plan', ref:<descriptor.path>, "
                    "schema_version:'research_plan@1', artifact_version:<artifact_version>}, "
                    "review_id='plan-review-001', execution_profile='scout'.\n\n"
                    "STEP 4 — Isolate review input: call research_review_prepare with the exact "
                    "review_task returned by STEP 3. Continue only when ready=true. Review the "
                    "hydrated artifact from this response, not a remembered draft.\n\n"
                    "STEP 5 — One review only (acting as g02-a10-output-reviewer): use the exact "
                    "acceptance_criteria, evidence_requirements and prohibited_behaviors from "
                    "the review_task. In particular assess driver/claim relevance, query-quality "
                    "and specificity of core_terms, balanced driver coverage, semantic separation "
                    "of topics, and whether each topic can discover both canonical and recent "
                    "sources when both are required. Produce a review_decision@1 with decision "
                    "APPROVED or REVISE. Use REVISE "
                    "only when a mandatory criterion is genuinely violated; do not invent "
                    "findings. Copy audit identity from the task and fill every required field: "
                    "schema_version='review_decision@1', review_id, task_id, "
                    "logical_review_node, reviewer_agent='g02-a10-output-reviewer', "
                    "producer_agent, artifact_ref, artifact_version, review_profile, "
                    "decision, confidence ('low', 'medium' or 'high'), attempt=1, summary, "
                    "findings, closed_finding_ids=[], and advisories=[]. Every finding requires "
                    "finding_id, criterion_id from the task, severity ('minor' or 'major' for "
                    "REVISE), location, observed, required_correction and evidence_refs. For "
                    "APPROVED use findings=[], root_cause=null and revision_scope=null. For "
                    "REVISE set root_cause="
                    "'producer_error', revision_scope.target_agent=producer_agent, "
                    "revision_scope.finding_ids=[all finding IDs]. "
                    "Then call research_review_finalize with task=<review_task> and "
                    "decision=<your decision object>.\n\n"
                    "STEP 6 — Conditional revision (only if STEP 5 decision was REVISE, "
                    "acting again as g02-a01-planner): revise the plan to address all "
                    "findings from the review decision, preserve unaffected plan content, and "
                    "advance artifact_version (for example 1.0.0 → 1.0.1). Call "
                    "research_planner_finalize with input=<original research_graph_input>, "
                    "plan=<complete revised plan>, execution_profile='scout', "
                    "previous_plan_ref=<STEP 2 descriptor.path> and "
                    "revision_items=<findings list from the review decision>. Use the produced "
                    "descriptor.path as the final plan ref. Do not invoke A10 again: the maximum "
                    "is exactly one review. If decision was APPROVED, skip this step.\n\n"
                    "STEP 7 — Scout: call research_scout_fanout with the final "
                    "research_plan artifact ref (from STEP 2 if APPROVED, from STEP 6 if "
                    "revised), total_target=50. Report run_directory and index summary. "
                    "Stop before A07 and A09. Do not call research_run_stub or "
                    "research_run_codex."
                ),
            },
        }],
    }


def _research_scout_e2e_prompt(context: str) -> dict:
    return {
        "description": "Scout -> A07 light -> A09 scout_fast workflow.",
        "messages": [{
            "role": "user",
            "content": {
                "type": "text",
                "text": (
                    "Run the Edu Materials Scout E2E workflow for this research_graph_input: "
                    f"{context}\n\n"
                    "First complete the same A01/A10/Scout steps as the research-scout prompt: "
                    "prepare and finalize a scout research_plan@1, run exactly one A10 plan review, "
                    "revise only if that one review returns REVISE, then call research_scout_fanout "
                    "with total_target=50.\n\n"
                    "After Scout completes, continue:\n\n"
                    "STEP 8 - A07 prepare: call research_scout_a07_prepare with "
                    "scout_run_dir=<run_directory> and intake_ref=<this context>. This writes "
                    "reviews.json and work/<topic_id>/<source_id>.input.json files.\n\n"
                    "STEP 9 - A07 model tasks: call research_scout_a07_tasks_prepare with "
                    "a07_dir=<A07 output dir> and intake=<this context>. It writes "
                    "scout_a07_model_task@1 files under tasks/. Each task is one topic/source unit.\n\n"
                    "STEP 10 - A07 light worker loop: for each task file, act as "
                    "g02-a07-scout-light-review. Use Sonnet/high when the host supports model "
                    "selection. Read only the task JSON, selected_windows and compact intake_context. "
                    "Do not read the full PDF. Produce the raw A07 JSON output and immediately call "
                    "research_scout_a07_partial_finalize with work_input_path=<a07_dir>/<work_input_ref> "
                    "and output=<raw A07 JSON>. Multiple tasks may run in parallel, but each worker "
                    "writes only its own partial review through the finalizer.\n\n"
                    "STEP 11 - Aggregate: call research_scout_a07_aggregate with a07_dir=<A07 output dir>. "
                    "Continue only with the aggregated reviews.json.\n\n"
                    "STEP 12 - Obligatory A09 scout_fast model pass: call "
                    "research_scout_a09_task_prepare with reviews_json=<a07_dir>/reviews.json, "
                    "intake=<this context>, max_deep_dive_sources=5, deep_dive_windows=8 and "
                    "deep_dive_chars=1200. The result contains one scout_a09_model_task@1 plus its "
                    "bounded deep_dive package. Act once as g02-a09-scout-synthesis using Opus with "
                    "medium effort. Read only the task, verify and refine deterministic_baseline, and "
                    "return the skill's raw JSON object. Then call research_scout_synthesis_finalize "
                    "with the same reviews_json and intake, deep_dive=<task-prepare deep_dive>, and "
                    "output=<raw A09 JSON>. A09 must not add evidence or read PDFs. If the model attempt "
                    "fails or is unavailable, call the finalizer without output but with the same "
                    "deep_dive; never fabricate model output. The result will record "
                    "a09_model_pass=false and synthesis_engine=deterministic_fallback.\n\n"
                    "Final output is solution_input_candidate@1 for Graph03. Graph03 must not be asked "
                    "to call G02 or do further research. Do not call research_run_stub or research_run_codex."
                ),
            },
        }],
    }


DISPATCH = {
    "research_front_door": _front_door,
    "research_node_input": _node_input,
    "research_planner_prepare": _planner_prepare,
    "research_planner_finalize": _planner_finalize,
    "research_plan_review_task": _plan_review_task,
    "research_provider_status": _provider_status,
    "research_domain_prepare": _domain_prepare,
    "research_query_plan_generate_fast": _query_plan_generate_fast,
    "research_metadata_search": _metadata_search,
    "research_doi_verify": _doi_verify,
    "research_doi_verify_batch": _doi_verify_batch,
    "research_domain_finalize": _domain_finalize,
    "research_domain_review_task": _domain_review_task,
    "research_canonical_prepare": _canonical_prepare,
    "research_citation_expand": _citation_expand,
    "research_canonical_finalize": _canonical_finalize,
    "research_canonical_review_task": _canonical_review_task,
    "research_recent_prepare": _recent_prepare,
    "research_recent_finalize": _recent_finalize,
    "research_recent_review_task": _recent_review_task,
    "research_market_cases_prepare": _market_cases_prepare,
    "research_web_case_search": _web_case_search,
    "research_market_cases_finalize": _market_cases_finalize,
    "research_market_cases_review_task": _market_cases_review_task,
    "research_candidate_index_prepare": _candidate_index_prepare,
    "research_candidate_index_finalize": _candidate_index_finalize,
    "research_candidate_index_review_task": _candidate_index_review_task,
    "research_source_selection_prepare": _source_selection_prepare,
    "research_source_selection_validate": _source_selection_validate,
    "research_source_selection_finalize": _source_selection_finalize,
    "research_retrieval_prepare": _retrieval_prepare,
    "research_oa_resolve": _oa_resolve,
    "research_document_retrieve": _document_retrieve,
    "research_document_validate": _document_validate,
    "research_retrieval_finalize": _retrieval_finalize,
    "research_retrieval_review_task": _retrieval_review_task,
    "research_web_case_extract": _web_case_extract,
    "research_paper_review_prepare": _paper_review_prepare,
    "research_document_text_index": _document_text_index,
    "research_document_text_window": _document_text_window,
    "research_paper_review_finalize": _paper_review_finalize,
    "research_paper_review_task": _paper_review_task,
    "research_synthesis_prepare": _synthesis_prepare,
    "research_synthesis_finalize": _synthesis_finalize,
    "research_synthesis_review_task": _synthesis_review_task,
    "research_bundle_finalize": _bundle_finalize,
    "research_review_prepare": _review_prepare,
    "research_review_finalize": _review_finalize,
    "research_finalize": _finalize,
    "research_scout_fanout": _scout_fanout,
    "research_scout_a07_prepare": _scout_a07_prepare,
    "research_scout_a07_tasks_prepare": _scout_a07_tasks_prepare,
    "research_scout_a07_partial_finalize": _scout_a07_partial_finalize,
    "research_scout_a07_aggregate": _scout_a07_aggregate,
    "research_scout_synthesis_prepare": _scout_synthesis_prepare,
    "research_scout_deep_dive_windows": _scout_deep_dive_windows,
    "research_scout_a09_task_prepare": _scout_a09_task_prepare,
    "research_scout_synthesis_finalize": _scout_synthesis_finalize,
    "research_run_stub": _run_stub,
    "research_run_codex": _run_codex,
    "research_run_hosted": _run_hosted,
    "research_resume": _resume,
    "research_trace": _trace,
}


# ---- JSON-RPC plumbing ---------------------------------------------------

def _result(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle(msg: dict):
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications."""
    method = msg.get("method")
    if method is None:                       # a response echoed back to us — ignore
        return None
    if method.startswith("notifications/"):  # notifications get no reply
        return None
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return _result(mid, {
            "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
            "capabilities": {"prompts": {}, "tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _result(mid, {})
    if method == "prompts/list":
        return _result(mid, {"prompts": PROMPTS})
    if method == "prompts/get":
        name = params.get("name")
        if name not in {"research", "research-scout", "research-scout-e2e"}:
            return _error(mid, -32602, f"unknown prompt {name!r}")
        args = params.get("arguments") or {}
        context = args.get("context")
        if not context:
            return _error(mid, -32602, "missing required prompt argument 'context'")
        if name == "research-scout":
            prompt = _research_scout_prompt(context)
        elif name == "research-scout-e2e":
            prompt = _research_scout_e2e_prompt(context)
        else:
            prompt = _research_prompt(context)
        return _result(mid, prompt)
    if method == "tools/list":
        return _result(mid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        fn = DISPATCH.get(name)
        if fn is None:
            return _error(mid, -32602, f"unknown tool {name!r}")
        arguments = params.get("arguments") or {}
        run_id = os.environ.get("EMAGENTS_RUN_ID", "unscoped")
        node_id = os.environ.get("EMAGENTS_NODE_ID", "mcp-client")
        audit = event_log.open_log(f"{run_id}-mcp")
        audit.append(node_id, name, detail={"argument_keys": sorted(arguments)})
        try:
            out = fn(arguments)
            audit.append(node_id, name, status="ok", detail={"is_error": False})
            return _result(mid, {"content": [{"type": "text",
                                               "text": json.dumps(out, ensure_ascii=False)}]})
        except Exception as exc:  # tool error -> result with isError, not a protocol error
            audit.append(node_id, name, status="failed", detail={
                "is_error": True, "exception_type": type(exc).__name__,
            })
            return _result(mid, {"content": [{"type": "text", "text": f"error: {exc}"}],
                                 "isError": True})
    return _error(mid, -32601, f"method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
