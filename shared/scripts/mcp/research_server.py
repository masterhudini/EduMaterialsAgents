#!/usr/bin/env python3
"""Pure-stdlib MCP (stdio) server exposing the Research Graph's deterministic seams as tools.

Implements the minimal MCP stdio protocol (JSON-RPC 2.0, newline-delimited) BY HAND — no
third-party dependencies, so it runs with the system python3 like the rest of the plugin.
Claude Code / Codex launch it via .mcp.json with ${CLAUDE_PLUGIN_ROOT}. New G02 runs use the
current Scout -> A07 -> A09 toolchain exposed by tools/list. Retired A02-A06/A08/A11 and review
helpers are deprecated and blocked at the MCP runtime boundary, but kept in source for now.

Methods: initialize, notifications/* (ignored), ping, tools/list, tools/call.
Active tools: A01 planner prepare/finalize, Scout fanout, A07 prepare/tasks/partial
finalize/aggregate, A09 task/finalize/research-state materialization, Human Research Gate and
bundle finalize.
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
from g02 import a07_bridge  # noqa: E402
from g02 import a07_runner  # noqa: E402
from g02 import a09_runner  # noqa: E402
from g02 import a09_synthesis  # noqa: E402
from g02 import provider_config  # noqa: E402
from g02 import credentials  # noqa: E402
from g02 import providers  # noqa: E402
from g02 import query_planning  # noqa: E402
from g02 import crossref  # noqa: E402
from g02 import review as reviewer  # noqa: E402
from core import artifacts, event_log, graphs, handoff  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "edu-materials-research", "version": "0.17.0"}


# ---- tool implementations (return JSON-serializable values) --------------

def _mcp_envelope(status: str, summary: str, *, produced=None, issues=None, metrics=None) -> dict:
    return {
        "schema_version": "envelope@1",
        "status": status,
        "produced": produced or [],
        "summary": summary,
        "issues": issues or [],
        "metrics": metrics or {},
    }


def _graph_manifest() -> dict:
    return graphs.load(rf.GRAPH_ID)


def _graph_node(name: str, manifest: dict | None = None) -> dict:
    manifest = manifest or _graph_manifest()
    for node in manifest.get("nodes", []):
        if node.get("name") == name:
            return node
    raise KeyError(f"g02 graph node not found: {name}")


def _graph_op(node_name: str, op_name: str, manifest: dict | None = None) -> str:
    node = _graph_node(node_name, manifest)
    operations = node.get("operations") or {}
    if op_name not in operations:
        raise KeyError(f"g02 graph operation not found: {node_name}.{op_name}")
    return operations[op_name]


def _graph_operation_names(manifest: dict | None = None) -> set[str]:
    manifest = manifest or _graph_manifest()
    names = set()
    for node in manifest.get("nodes", []):
        operations = node.get("operations") or {}
        if isinstance(operations, dict):
            names.update(str(value) for value in operations.values() if value)
    return names


def _workflow_ops() -> dict:
    manifest = _graph_manifest()
    return {
        "sequence": list(manifest.get("sequence", [])),
        "default_profile": manifest.get("default_execution_profile", "scout_e2e"),
        "scout_target": (
            manifest.get("execution_profiles", {})
            .get("scout_e2e", {})
            .get("scout", {})
            .get("total_target", 50)
        ),
        "planner_prepare": _graph_op("g02-a01-planner", "prepare", manifest),
        "planner_finalize": _graph_op("g02-a01-planner", "finalize", manifest),
        "provider_setup": _graph_op("research-scout-fanout", "provider_setup", manifest),
        "scout_run": _graph_op("research-scout-fanout", "run", manifest),
        "a07_prepare": _graph_op("g02-a07-paper-review", "prepare", manifest),
        "a07_tasks": _graph_op("g02-a07-paper-review", "prepare_tasks", manifest),
        "a07_partial": _graph_op("g02-a07-paper-review", "partial_finalize", manifest),
        "a07_aggregate": _graph_op("g02-a07-paper-review", "aggregate", manifest),
        "a09_task": _graph_op("g02-a09-synthesizer", "prepare_task", manifest),
        "a09_solution": _graph_op("g02-a09-synthesizer", "finalize_solution", manifest),
        "a09_state": _graph_op("g02-a09-synthesizer", "finalize_research_state", manifest),
        "gate_prepare": _graph_op("user-research-gate", "prepare", manifest),
        "gate_finalize": _graph_op("user-research-gate", "finalize", manifest),
    }


def _read_artifact_or_path(ref: str):
    if ref.startswith(artifacts.SCHEME):
        return artifacts.hydrate(ref)
    return json.loads(pathlib.Path(ref).expanduser().resolve().read_text(encoding="utf-8"))


def _produced_payload(envelope: dict, schema_version: str, *, artifact_type: str | None = None) -> dict:
    for descriptor in envelope.get("produced", []):
        if not isinstance(descriptor, dict):
            continue
        if descriptor.get("schema_version") != schema_version:
            continue
        if artifact_type and descriptor.get("type") != artifact_type:
            continue
        path = descriptor.get("path")
        if not isinstance(path, str):
            continue
        return _read_artifact_or_path(path)
    raise ValueError(f"envelope has no produced {schema_version} descriptor")


def _produced_path(envelope: dict, schema_version: str, *, artifact_type: str | None = None) -> str:
    for descriptor in envelope.get("produced", []):
        if not isinstance(descriptor, dict):
            continue
        if descriptor.get("schema_version") != schema_version:
            continue
        if artifact_type and descriptor.get("type") != artifact_type:
            continue
        path = descriptor.get("path")
        if isinstance(path, str) and path:
            return path
    raise ValueError(f"envelope has no produced {schema_version} path")

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


PROVIDER_CATALOG = [
    {"provider": "semantic_scholar", "role": "Metadane scholarly (tytuły, abstrakty, cytowania).",
     "requires": "nothing", "needs": "nic", "signup": None},
    {"provider": "arxiv", "role": "Preprinty i wersje robocze.",
     "requires": "email", "needs": "email", "signup": None},
    {"provider": "crossref", "role": "Weryfikacja DOI i metadanych wydawniczych.",
     "requires": "email", "needs": "email", "signup": None},
    {"provider": "openalex", "role": "Główny graf scholarly (prace, autorzy, cytowania).",
     "requires": "email_and_token",
     "needs": "email + DARMOWY token OpenAlex — OBA wymagane (bez kompletu OpenAlex jest pomijany)",
     "signup": "https://openalex.org",
     "token": {
         "env": "OPENALEX_API_KEY",
         "required_for_openalex": True,
         "free": True,
         "needs_account": True,
         "signup": "https://openalex.org/login?redirect=/settings/api-key",
         "encouragement": "OpenAlex (najbogatsze źródło scholarly) potrzebuje email ORAZ DARMOWEGO "
                          "tokena. Bez kompletu OpenAlex jest "
                          "POMIJANY (reszta — Semantic Scholar, arXiv, Crossref, Unpaywall — działa "
                          "na samym mailu). Token jest darmowy: zaloguj się / załóż konto i wygeneruj "
                          "na https://openalex.org/login?redirect=/settings/api-key, potem podaj jako "
                          "openalex_key. WARTO — to otwiera najbogatszy graf scholarly."}},
    {"provider": "unpaywall", "role": "Rozwiązywanie legalnego Open Access do pobrań (a06).",
     "requires": "email", "needs": "email", "signup": None},
    {"provider": "doab", "role": "Open Access książki (a06).",
     "requires": "nothing", "needs": "nic", "signup": None},
    {"provider": "oapen", "role": "Open Access książki (a06).",
     "requires": "nothing", "needs": "nic", "signup": None},
]


def _provider_setup(args: dict):
    """Show the provider catalog with current readiness, and OPTIONALLY set session credentials.

    Pass {email} to unlock arXiv, Crossref and Unpaywall. OpenAlex needs BOTH the email AND its
    {openalex_key} (free token) — without both it is skipped. Pass nothing to just view the catalog.

    Readiness is derived from the credential requirement model + the live session env (not from
    provider_status, which fails validation while the email is still missing)."""
    creds = {k: args[k] for k in ("email", "openalex_key") if args.get(k)}
    saved = credentials.save(creds) if creds else {"stored": []}
    credentials.overlay()                                # reflect any on-disk creds in os.environ
    env = credentials.managed_environment(os.environ)
    has_email = bool(env.get("EMAGENTS_RESEARCH_CONTACT_EMAIL", "").strip())
    has_key = bool(env.get("OPENALEX_API_KEY", "").strip())
    rows = []
    for item in PROVIDER_CATALOG:
        req = item["requires"]
        if req == "nothing":
            ready = True
        elif req == "email":
            ready = has_email
        else:                                            # email_and_token (OpenAlex): both required
            ready = has_email and has_key
        if item["provider"] == "openalex":
            auth = ("configured" if (has_email and has_key) else
                    "incomplete_missing_token" if has_email else "incomplete_missing_email")
        elif req == "email":
            auth = "configured_email" if has_email else "required_email_missing"
        else:
            auth = "none"
        rows.append({**item, "ready": ready, "authentication": auth})
    openalex_ready = has_email and has_key
    return {
        "tier": "email" if has_email else "minimal",
        "contact_email_configured": has_email,
        "openalex_token_configured": has_key,
        "openalex_ready": openalex_ready,
        "saved": saved,
        "active_providers": [r["provider"] for r in rows if r["ready"]],
        "catalog": rows,
        "openalex_token_hint": next(
            (r["token"]["encouragement"] for r in rows
             if r["provider"] == "openalex" and not openalex_ready), None),
        "note": ("Podaj email, aby odblokować arXiv, Crossref i Unpaywall (legalne OA). OpenAlex "
                 "(najbogatszy graf scholarly) potrzebuje DODATKOWO darmowego tokena; bez kompletu "
                 "(email ORAZ token) OpenAlex jest pomijany. "
                 "Token za darmo: zaloguj się / załóż konto i wygeneruj na "
                 "https://openalex.org/login?redirect=/settings/api-key, podaj jako openalex_key. "
                 "Możesz nic nie podać — wtedy działa tylko Semantic Scholar (+ DOAB/OAPEN). Dane są "
                 "przechowywane efemerycznie, a plik znika po pierwszym udanym zapytaniu do bazy."),
    }


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
        knowledge_root=args.get("knowledge_root"),
        total_target=args.get("total_target"),
        max_workers=args.get("max_workers"),
    )


def _a07_prepare(args: dict):
    return a07_bridge.build_a07_reviews(
        args["scout_run_dir"],
        output_dir=args.get("output_dir"),
        intake_ref=args.get("intake_ref"),
        max_windows_per_source=args.get("max_windows_per_source", 5),
        max_scan_pages=args.get("max_scan_pages", 16),
    )


def _a07_tasks_prepare(args: dict):
    return a07_runner.write_a07_review_tasks(
        args["a07_dir"],
        output_dir=args.get("output_dir"),
        intake=args.get("intake"),
        topic_ids=args.get("topic_ids"),
        source_ids=args.get("source_ids"),
        include_context_only=args.get("include_context_only", True),
        limit=args.get("limit"),
    )


def _a07_partial_finalize(args: dict):
    work_path = pathlib.Path(args["work_input_path"]).expanduser().resolve()
    a07_root = work_path.parents[2] if len(work_path.parents) >= 3 else work_path.parent
    work_ref = a07_bridge._rel(work_path, a07_root)
    output_path = pathlib.Path(args["output_path"]).expanduser().resolve() if args.get("output_path") else (
        a07_root / a07_bridge._partial_ref_for_work_ref(work_ref)
    )
    partial = a07_bridge.finalize_a07_partial(
        args["work_input_path"],
        args["output"],
        output_path=output_path,
        artifact_version=args.get("artifact_version", "1.0.0"),
    )
    return _mcp_envelope(
        "ok",
        "Stored A07 partial review.",
        produced=[{
            "type": "a07_review",
            "path": str(output_path),
            "schema_version": a07_bridge.A07_PARTIAL_CONTRACT,
            "artifact_version": args.get("artifact_version", "1.0.0"),
        }],
        metrics={
            "presentation_update_count": len(partial.get("presentation_update_candidates", [])),
            "lookup_pointer_count": len(partial.get("lookup_pointers", [])),
            "coverage_gap_count": len(partial.get("coverage_gaps", [])),
        },
    )


def _a07_aggregate(args: dict):
    a07_dir = pathlib.Path(args["a07_dir"]).expanduser().resolve()
    aggregate = a07_bridge.aggregate_a07_reviews(a07_dir)
    reviews_path = a07_dir / "reviews.json"
    artifact_version = aggregate.get("artifact_version") or args.get("artifact_version", "1.0.0")
    return _mcp_envelope(
        "ok",
        "Stored aggregated A07 reviews.",
        produced=[{
            "type": "a07_reviews",
            "path": str(reviews_path),
            "schema_version": a07_bridge.A07_REVIEWS_CONTRACT,
            "artifact_version": artifact_version,
        }],
        metrics={
            "source_review_count": len(aggregate.get("source_reviews", [])),
            "presentation_update_count": len(aggregate.get("presentation_update_candidates", [])),
            "lookup_pointer_count": len(aggregate.get("lookup_pointers", [])),
            "coverage_gap_count": len(aggregate.get("coverage_gaps", [])),
        },
    )


def _a09_synthesis_prepare(args: dict):
    reviews_json = args["reviews_json"]
    if isinstance(reviews_json, dict) and reviews_json.get("schema_version") == "envelope@1":
        reviews_json = _produced_path(
            reviews_json,
            a07_bridge.A07_REVIEWS_CONTRACT,
            artifact_type="a07_reviews",
        )
    return a09_synthesis.prepare_a09_synthesis(
        reviews_json,
        intake=args.get("intake"),
        max_deep_dive_sources=args.get("max_deep_dive_sources", 5),
    )


def _scout_deep_dive_windows(args: dict):
    reviews_json = args["reviews_json"]
    if isinstance(reviews_json, dict) and reviews_json.get("schema_version") == "envelope@1":
        reviews_json = _produced_path(
            reviews_json,
            a07_bridge.A07_REVIEWS_CONTRACT,
            artifact_type="a07_reviews",
        )
    prepared = a09_synthesis.prepare_a09_synthesis(
        reviews_json,
        intake=args.get("intake"),
        max_deep_dive_sources=args.get("max_deep_dive_sources", 5),
    )
    synthesis_input = prepared["synthesis_input"]
    return a09_synthesis.gather_deep_dive_windows(
        synthesis_input["reviews"],
        synthesis_input["deep_dive_requests"],
        max_windows=args.get("max_windows", 12),
        max_chars=args.get("max_chars", 1800),
    )


def _a09_task_prepare(args: dict):
    reviews_json = args["reviews_json"]
    if isinstance(reviews_json, dict) and reviews_json.get("schema_version") == "envelope@1":
        reviews_json = _produced_path(
            reviews_json,
            a07_bridge.A07_REVIEWS_CONTRACT,
            artifact_type="a07_reviews",
        )
    built = a09_runner.build_a09_task(
        reviews_json,
        intake=args.get("intake"),
        max_deep_dive_sources=args.get("max_deep_dive_sources", 5),
        deep_dive_windows=args.get("deep_dive_windows", 8),
        deep_dive_chars=args.get("deep_dive_chars", 1200),
    )
    return {
        "task": built["task"],
        "deep_dive": built["deep_dive"],
    }


def _a09_synthesis_finalize(args: dict):
    reviews_json = args["reviews_json"]
    if isinstance(reviews_json, dict) and reviews_json.get("schema_version") == "envelope@1":
        reviews_json = _produced_path(
            reviews_json,
            a07_bridge.A07_REVIEWS_CONTRACT,
            artifact_type="a07_reviews",
        )
    prepared = a09_synthesis.prepare_a09_synthesis(
        reviews_json,
        intake=args.get("intake"),
        max_deep_dive_sources=args.get("max_deep_dive_sources", 5),
    )
    artifact_version = args.get("artifact_version", "1.0.0")
    solution = a09_synthesis.finalize_a09_solution(
        prepared["synthesis_input"],
        args.get("output"),
        deep_dive=args.get("deep_dive"),
        artifact_version=artifact_version,
        output_path=args.get("output_path"),
    )
    if args.get("output_path"):
        output_ref = str(pathlib.Path(args["output_path"]).expanduser().resolve())
    else:
        task = a09_synthesis._safe(str(solution["task_id"]))
        version = a09_synthesis._safe(str(artifact_version))
        output_ref = artifacts.store(
            f"g02/a09/{task}.{version}.solution-input-candidate.pre-gate.json",
            solution,
        )
    return _mcp_envelope(
        "ok",
        "Stored A09 solution input candidate.",
        produced=[{
            "type": "solution_input_candidate",
            "path": output_ref,
            "schema_version": a09_synthesis.SOLUTION_CONTRACT,
            "artifact_version": artifact_version,
        }],
        metrics={
            "a09_model_pass": bool(solution.get("a09_model_pass")),
            "suggested_update_count": len(solution.get("suggested_updates", [])),
            "optional_improvement_count": len(solution.get("optional_improvements", [])),
            "unresolved_count": len(solution.get("unresolved_items", [])),
        },
    )


def _a09_research_state_finalize(args: dict):
    solution = args.get("solution")
    if isinstance(solution, dict) and solution.get("schema_version") == "envelope@1":
        solution = _produced_payload(
            solution,
            a09_synthesis.SOLUTION_CONTRACT,
            artifact_type="solution_input_candidate",
        )
    if not isinstance(solution, dict):
        if args.get("reviews_json") is None:
            raise ValueError("solution or reviews_json is required")
        envelope = _a09_synthesis_finalize(args)
        solution = _produced_payload(
            envelope,
            a09_synthesis.SOLUTION_CONTRACT,
            artifact_type="solution_input_candidate",
        )
    return a09_synthesis.finalize_a09_research_state(
        solution,
        artifact_version=args.get("artifact_version", "1.0.0"),
    )


def _human_gate_prepare(args: dict):
    return synthesis.prepare_human_research_gate(args["research_state_ref"])


def _run_codex(args: dict):
    """Run or resume g02 through nested Codex workers, mirroring the g01/g03 codex entrypoints.

    Deterministic Scout fanout runs in-process; each A01/A07/A09 agent is an isolated codex worker.
    MCP is not an interactive stdin surface, so gates pause/resume and human approval is never
    simulated."""
    if args.get("gates", "pause") != "pause":
        raise ValueError("Codex runs require gates='pause'")
    runner = rf.make_g02_codex_runner()
    through = args.get("through", "user-research-gate")
    resume_token = args.get("resume_token")
    if resume_token:
        return rf.run(None, node_runner=runner, reviewed=True, pause_on_gate=True,
                      resume_token=resume_token, decisions=args.get("decisions"),
                      through=through, topic_ids=args.get("topic_ids"))
    context = args.get("context")
    if not context:
        raise ValueError("context is required when resume_token is absent")
    return rf.run(rf.front_door(context)["ref"], node_runner=runner, reviewed=True,
                  pause_on_gate=True, through=through, topic_ids=args.get("topic_ids"))


def _run_hosted(args: dict):
    context = args.get("context")
    if not context:
        raise ValueError("context is required")
    front_door = rf.front_door(context)
    return rf.run(
        front_door["ref"],
        reviewed=True,
        pause_on_node=True,
        pause_on_gate=True,
        through=args.get("through", "user-research-gate"),
        topic_ids=args.get("topic_ids"),
    )


def _resume(args: dict):
    return rf.run(
        reviewed=True,
        pause_on_node=True,
        pause_on_gate=True,
        resume_token=args["resume_token"],
        node_results=args.get("node_results"),
        node_failures=args.get("node_failures"),
        decisions=args.get("decisions"),
        usage_reports=args.get("usage_reports"),
        through=args.get("through", "user-research-gate"),
    )


def _trace(args: dict):
    from core import event_log
    return event_log.open_log(f"{args['run_id']}-mcp").summary()


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
                "execution_profile": {"type": "string", "enum": ["scout_e2e"]},
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
                "execution_profile": {"type": "string", "enum": ["scout_e2e"]},
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
                "execution_profile": {"type": "string", "enum": ["scout_e2e"]},
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
                       "user_approved_source_set@1 consumed by A06.",
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
        "name": "research_human_gate_prepare",
        "description": "Prepare the Human Research Gate packet from a research_state@1 ref. "
                       "Returns the research_summary@1 digest, validation packet and decision "
                       "template for user approval before Graph03 handoff.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_state_ref": {"type": "string"}
            },
            "required": ["research_state_ref"]
        }
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
                       "research_plan@1. Starts one process per topic, uses only provider "
                       "credentials collected through research_provider_setup, persists machine "
                       "artifacts under .emagents, and copies human-readable PDFs under knowledge/. "
                       "Does not run A07, A09, run or run-codex.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "research_plan_ref": {
                    "type": "string",
                    "description": "Path or artifact:// ref to a finalized research_plan@1"
                },
                "workspace": {
                    "type": "string",
                    "description": "Optional exact Scout machine-artifact workspace; defaults under .emagents"
                },
                "knowledge_root": {
                    "type": "string",
                    "description": "Optional exact public PDF root; defaults to knowledge/g02/<task_id>"
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
        "name": "research_a07_prepare",
        "description": "Prepare bounded, parallel-safe A07 light-review work items from one "
                       "Scout run directory. Reads Scout plan, requests, index, topic corpora "
                       "and sampled PDF windows, then writes reviews.json plus immutable "
                       "work/<topic_id>/<source_id>.input.json files. Does not call an LLM.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scout_run_dir": {
                    "type": "string",
                    "description": "Path to .emagents/artifacts/g02/scout/runs/<task_id> or a legacy Scout run dir"
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
        "name": "research_a07_tasks_prepare",
        "description": "Build compact a07_review_task@1 JSON files from pending A07 work "
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
        "name": "research_a07_partial_finalize",
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
        "name": "research_a07_aggregate",
        "description": "Aggregate A07 partial review files into one a07_reviews@1 "
                       "reviews.json without worker write contention. Returns envelope@1 with "
                       "the aggregated a07_reviews@1 descriptor in produced[].",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a07_dir": {
                    "type": "string",
                    "description": "Directory containing reviews.json, work/ and partial/"
                },
                "artifact_version": {
                    "type": "string",
                    "description": "Aggregated reviews artifact version; defaults to reviews.json artifact_version"
                }
            },
            "required": ["a07_dir"]
        }
    },
    {
        "name": "research_a09_synthesis_prepare",
        "description": "Prepare the Bounded A09 synthesis input from aggregated A07 reviews "
                       "and optional intake. Selects at most five bounded deep-dive source slots.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reviews_json": {
                    "type": ["string", "object"],
                    "description": "Path/artifact ref to a07_reviews@1, or envelope from research_a07_aggregate"
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
        "name": "research_a09_deep_dive_windows",
        "description": "Gather up to twelve bounded additional PDF windows for each of at most "
                       "five auditable A09 deep-dive requests. Missing PDFs fail open with "
                       "an explicit limitation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reviews_json": {
                    "type": ["string", "object"],
                    "description": "Path/artifact ref to a07_reviews@1, or envelope from research_a07_aggregate"
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
        "name": "research_a09_task_prepare",
        "description": "Build the obligatory a09_synthesis_task@1 for an Opus/medium "
                       "verification pass. The tool prepares the deterministic baseline and "
                       "bounded deep dive with at most five sources, eight windows per source "
                       "and 1200 characters per window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reviews_json": {
                    "type": ["string", "object"],
                    "description": "Path/artifact ref to aggregated a07_reviews@1, or envelope from research_a07_aggregate"
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
        "name": "research_a09_synthesis_finalize",
        "description": "Finalize the Bounded A09 output as solution_input_candidate@1 for "
                       "Graph03. The final contract must contain concrete slide-update guidance; "
                       "Graph03 must not call back into G02.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reviews_json": {
                    "type": ["string", "object"],
                    "description": "Path/artifact ref to a07_reviews@1, or envelope from research_a07_aggregate"
                },
                "intake": {
                    "type": "string",
                    "description": "Optional research_graph_input@1 path/ref for presentation context"
                },
                "output": {
                    "type": "object",
                    "description": "Raw g02-a09-synthesizer JSON with plan, priorities, optional improvements, unresolved items and confidence. Omit only after a failed or unavailable model attempt to request deterministic fallback."
                },
                "deep_dive": {
                    "type": "object",
                    "description": "Optional a07_deep_dive@1 package returned by research_a09_deep_dive_windows"
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
        "name": "research_a09_research_state_finalize",
        "description": "Materialize a research_state@1, research_summary@1 and "
                       "user_research_validation_packet@1 from the A09 "
                       "solution_input_candidate@1 so the Human Research Gate can approve the "
                       "G02->G03 bundle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "solution": {
                    "type": "object",
                    "description": "solution_input_candidate@1 returned by research_a09_synthesis_finalize"
                },
                "reviews_json": {
                    "type": "string",
                    "description": "Optional fallback: recompute the deterministic A09 solution from reviews_json"
                },
                "intake": {
                    "type": "string",
                    "description": "Optional research_graph_input@1 path/ref for fallback recomputation"
                },
                "output": {
                    "type": "object",
                    "description": "Optional raw A09 output for fallback recomputation"
                },
                "deep_dive": {
                    "type": "object",
                    "description": "Optional a07_deep_dive@1 for fallback recomputation"
                },
                "artifact_version": {
                    "type": "string",
                    "description": "Materialized artifact version; default 1.0.0"
                }
            }
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
        "description": "Run the active G02 Scout flow with NESTED Codex workers (codex exec): "
                       "deterministic Scout fanout runs in-process and each A01/A07/A09 agent is an "
                       "isolated worker, then pause at the Human Research Gate. Use research_run_hosted "
                       "instead when the calling session should play each agent itself. User gates "
                       "always use pause/resume because MCP tools cannot read interactive stdin.",
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
                        "g02-a01-planner", "research-scout-fanout", "g02-a07-paper-review",
                        "g02-a09-synthesizer", "user-research-gate"
                    ],
                    "description": "Last active stage to execute; defaults to the Human Research Gate."
                },
                "topic_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional bounded Scout topic subset."
                },
            },
        },
    },
    {
        "name": "research_provider_setup",
        "description": "Show the scholarly/OA provider catalog (what each does, what it needs, "
                       "current ready status, the OpenAlex token link) and OPTIONALLY set the session "
                       "credentials. Pass {email} to unlock arXiv, Crossref and Unpaywall. OpenAlex "
                       "needs BOTH the email AND its free {openalex_key} token (queried via API) — "
                       "without both it is skipped. Pass nothing to just view the catalog and current "
                       "tier (Semantic Scholar needs no credentials). Credentials are stored "
                       "ephemerally and the file is deleted after the first successful provider query. "
                       "Call this at the start of Research (after A01) to collect provider data from the user.",
        "inputSchema": {"type": "object", "properties": {
            "email": {"type": "string",
                      "description": "contact email for arXiv/Crossref/Unpaywall, and (with the token) OpenAlex; free, no signup"},
            "openalex_key": {"type": "string",
                             "description": "free OpenAlex API token (with the email, required to use OpenAlex); generate at openalex.org/login?redirect=/settings/api-key"}}},
    },
    {
        "name": "research_run_hosted",
        "description": "Start the active HOST-DRIVEN G02 Scout E2E run (no nested codex exec). "
                       "The runner executes deterministic Scout/A07/A09 finalizer steps itself and "
                       "pauses only for model work: A01 planning, each A07 bounded source review, "
                       "A09 synthesis and the Human Research Gate. Awaiting node payloads include "
                       "node_key, input, upstream, finalize_op and finalize_args; call the finalize "
                       "op and resume with node_results keyed by node_key.",
        "inputSchema": {"type": "object", "required": ["context"],
                        "properties": {"context": {"type": "string",
                                                   "description": "path or artifact:// ref to a research_graph_input bundle"},
                                       "through": {"type": "string"},
                                       "topic_ids": {"type": "array", "items": {"type": "string"}}}},
    },
    {
        "name": "research_resume",
        "description": "Resume a host-driven g02 Scout E2E run with exactly one of: "
                       "node_results={node_key: finalize_envelope} after playing an awaited model "
                       "node and its finalize op; node_failures={node_key: {summary, issues}}; or "
                       "decisions={gate: ...} for the Human Research Gate. Optional usage_reports={node_key: "
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

BASE_ACTIVE_TOOL_NAMES = {
    "research_front_door",
    "research_node_input",
    "research_finalize",
    "research_run_hosted",
    "research_run_codex",
    "research_resume",
}
ACTIVE_TOOL_NAMES = BASE_ACTIVE_TOOL_NAMES | _graph_operation_names()
ACTIVE_TOOLS = [tool for tool in TOOLS if tool.get("name") in ACTIVE_TOOL_NAMES]

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
        "description": "Run the Scout discovery path through A07 light reviews, A09 and the "
                       "Human Research Gate. Live Scout and host-model A07 are still performed "
                       "by the host environment.",
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
    prompt = _research_scout_e2e_prompt(context)
    prompt["description"] = (
        "Semantic 'zrob research' entrypoint for the current hosted Scout -> A07 -> A09 workflow."
    )
    return prompt


def _research_scout_prompt(context: str) -> dict:
    ops = _workflow_ops()
    sequence = " -> ".join(ops["sequence"])
    return {
        "description": "Claude-hosted A01 -> Scout workflow without A10 review.",
        "messages": [{
            "role": "user",
            "content": {
                "type": "text",
                "text": (
                    "Run only the Edu Materials scout milestone for this research_graph_input: "
                    f"{context}\n\n"
                    "Tool names and sequence are read from shared/graphs/g02.graph.json. "
                    f"Graph sequence: {sequence}.\n\n"
                    f"STEP 1 — Prepare: call {ops['planner_prepare']} with "
                    "execution_profile='scout_e2e'. This returns research_planner_input@1 and "
                    "plan_output_template.\n\n"
                    "STEP 2 — Plan (acting as g02-a01-planner, Opus/medium): create 1-6 "
                    "intake-anchored, bibliographically searchable topics following the "
                    "plan_output_template. Each topic must have a stable TOPIC_ID, 3-6 "
                    f"core_terms and coverage units linked to approved drivers. Call "
                    f"{ops['planner_finalize']} with input=<original research_graph_input>, "
                    "plan=<complete plan object> and execution_profile='scout_e2e'. The produced "
                    "research_plan descriptor uses path=<artifact:// ref>; retain that path "
                    "and artifact_version.\n\n"
                    f"STEP 3 — Provider readiness: call {ops['provider_setup']} with no arguments. "
                    "If the user provides email/openalex_key, call it again with those values before Scout.\n\n"
                    f"STEP 4 — Scout: call {ops['scout_run']} with the final "
                    f"research_plan artifact ref from STEP 2, total_target={ops['scout_target']}. Report "
                    "run_directory and index summary. Stop before A07 and A09. Do not call "
                    "research_run_stub, research_run_codex or any A10 review tool."
                ),
            },
        }],
    }


def _research_scout_e2e_prompt(context: str) -> dict:
    ops = _workflow_ops()
    sequence = " -> ".join(ops["sequence"])
    return {
        "description": "Hosted Scout -> A07 light -> A09 workflow.",
        "messages": [{
            "role": "user",
            "content": {
                "type": "text",
                "text": (
                    "Run the Edu Materials hosted Scout E2E workflow for this research_graph_input: "
                    f"{context}\n\n"
                    "The active sequence is read from shared/graphs/g02.graph.json: "
                    f"{sequence}. Use research_run_hosted as the single runtime entrypoint; "
                    "do not manually replay a copied sequence and do not run A10 review.\n\n"
                    "1. Call research_run_hosted with context=<this context> and through='user-research-gate'.\n"
                    "2. Loop on the returned status:\n"
                    "   - awaiting_node: run the named node using only the payload input. For A07 use "
                    "only selected_windows and compact intake_context; never read full PDFs. Call the "
                    "payload finalize_op with the provided finalize_args filled with the raw model JSON, "
                    "then call research_resume with node_results keyed by payload.node_key. After the "
                    "A01 planner finalizer succeeds and before resuming, call research_provider_setup "
                    "if the user wants to provide email/openalex_key for Scout.\n"
                    "   - awaiting_user: present the Human Research Gate summary and collect explicit "
                    "decisions, then call research_resume with decisions={'user-research-gate': <decision>}.\n"
                    "   - completed: output_ref is the user_approved_research_bundle@1 for Graph03.\n\n"
                    "The hosted runner performs deterministic Scout fanout, A07 aggregation, A09 "
                    "research_state materialization and bundle finalization. Graph03 must not be asked "
                    "to call G02 or do further research. Do not call research_run_stub or "
                    "research_run_codex."
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
    "research_provider_setup": _provider_setup,
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
    "research_a07_prepare": _a07_prepare,
    "research_a07_tasks_prepare": _a07_tasks_prepare,
    "research_a07_partial_finalize": _a07_partial_finalize,
    "research_a07_aggregate": _a07_aggregate,
    "research_a09_synthesis_prepare": _a09_synthesis_prepare,
    "research_a09_deep_dive_windows": _scout_deep_dive_windows,
    "research_a09_task_prepare": _a09_task_prepare,
    "research_a09_synthesis_finalize": _a09_synthesis_finalize,
    "research_a09_research_state_finalize": _a09_research_state_finalize,
    "research_human_gate_prepare": _human_gate_prepare,
    "research_run_stub": _run_stub,
    "research_run_codex": _run_codex,
    "research_run_hosted": _run_hosted,
    "research_resume": _resume,
    "research_trace": _trace,
}


DEPRECATED_TOOL_NAMES = set(DISPATCH).difference(ACTIVE_TOOL_NAMES)


def _deprecated_tool_notice(name: str) -> dict:
    return {
        "schema_version": "research_current_workflow_notice@1",
        "status": "deprecated_tool",
        "tool": name,
        "replacement_prompt": "research-scout-e2e",
        "active_tools": sorted(ACTIVE_TOOL_NAMES),
        "summary": (
            f"{name} is retained in source for legacy tests and migration only, "
            "but it is not executable through the current MCP runtime. Use the "
            "Scout -> A07 -> A09 -> Human Research Gate workflow."
        ),
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
        return _result(mid, {"tools": ACTIVE_TOOLS})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        run_id = os.environ.get("EMAGENTS_RUN_ID", "unscoped")
        node_id = os.environ.get("EMAGENTS_NODE_ID", "mcp-client")
        audit = event_log.open_log(f"{run_id}-mcp")
        audit.append(node_id, name or "unknown_tool", detail={
            "argument_keys": sorted(arguments),
            "deprecated": name in DEPRECATED_TOOL_NAMES,
        })
        if name in DEPRECATED_TOOL_NAMES:
            audit.append(node_id, name, status="deprecated", detail={
                "is_error": False,
                "deprecated": True,
            })
            return _result(mid, {"content": [{"type": "text",
                                              "text": json.dumps(
                                                  _deprecated_tool_notice(name),
                                                  ensure_ascii=False,
                                              )}]})
        if name not in ACTIVE_TOOL_NAMES:
            audit.append(node_id, name or "unknown_tool", status="failed", detail={
                "is_error": True,
                "error_type": "unknown_tool",
            })
            return _error(mid, -32602, f"unknown tool {name!r}")
        fn = DISPATCH[name]
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
