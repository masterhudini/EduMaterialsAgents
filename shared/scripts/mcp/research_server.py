#!/usr/bin/env python3
"""Pure-stdlib MCP (stdio) server exposing the Research Graph's deterministic seams as tools.

Implements the minimal MCP stdio protocol (JSON-RPC 2.0, newline-delimited) BY HAND — no
third-party dependencies, so it runs with the system python3 like the rest of the plugin.
Claude Code / Codex launch it via .mcp.json with ${CLAUDE_PLUGIN_ROOT}; the deterministic seams
wrap shared/scripts/g02/g02_flow.py.

Methods: initialize, notifications/* (ignored), ping, tools/list, tools/call.
Tools: research_front_door, research_node_input, research_planner_prepare,
research_planner_finalize, research_plan_review_task, research_provider_status,
research_domain_prepare, research_metadata_search, research_domain_finalize,
research_domain_review_task, research_canonical_prepare, research_citation_expand,
research_canonical_finalize, research_canonical_review_task,
research_recent_prepare, research_recent_finalize, research_recent_review_task,
research_market_cases_prepare, research_web_case_search,
research_market_cases_finalize, research_market_cases_review_task,
research_candidate_index_prepare, research_candidate_index_finalize,
research_candidate_index_review_task,
research_web_case_extract,
research_review_prepare, research_review_finalize,
research_finalize, research_run_stub, research_run_codex.
"""
from __future__ import annotations

import json
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
from g02 import web_cases  # noqa: E402
from g02 import planner  # noqa: E402
from g02 import provider_config  # noqa: E402
from g02 import providers  # noqa: E402
from g02 import review as reviewer  # noqa: E402
from core import artifacts, graphs, handoff  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "edu-materials-research", "version": "0.8.0"}


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
        return json.loads(pathlib.Path(value).read_text(encoding="utf-8"))
    return value


def _planner_prepare(args: dict):
    return planner.prepare_planner(
        _planner_payload(args["input"]),
        previous_plan_ref=args.get("previous_plan_ref"),
        revision_items=args.get("revision_items"),
    )


def _planner_finalize(args: dict):
    prepared = planner.prepare_planner(
        _planner_payload(args["input"]),
        previous_plan_ref=args.get("previous_plan_ref"),
        revision_items=args.get("revision_items"),
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
    prepared = planner.prepare_planner(_planner_payload(args["input"]))
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


def _web_case_extract(args: dict):
    return web_cases.extract_web_case(
        args["selection_ref"], args["candidate_sources_ref"], args["source_id"],
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


def _run_codex(args: dict):
    """Run or resume the graph through Codex workers.

    MCP tools are not an interactive stdin surface, so the default gate behavior is pause/resume.
    Use gates=auto only for deterministic smoke runs where human approvals may be simulated.
    """
    from g02.runners.codex import codex_node_runner

    gates = args.get("gates", "pause")
    if gates not in {"pause", "auto"}:
        raise ValueError("gates must be 'pause' or 'auto'")

    resume_token = args.get("resume_token")
    decisions = args.get("decisions")
    if resume_token:
        return rf.run(
            None,
            node_runner=codex_node_runner,
            pause_on_gate=(gates == "pause"),
            resume_token=resume_token,
            decisions=decisions,
        )

    context = args.get("context")
    if not context:
        raise ValueError("context is required when resume_token is absent")
    ref = rf.front_door(context)["ref"]
    return rf.run(ref, node_runner=codex_node_runner, pause_on_gate=(gates == "pause"))


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
                       "Returns the isolated research_planner_input@1 or a completed failure "
                       "envelope without invoking an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "description": "Research Graph input object, path or artifact:// ref"
                },
                "previous_plan_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
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
                    "description": "Research Graph or scoped planner input object, path or ref"
                },
                "plan": {"type": "object"},
                "previous_plan_ref": {"type": "string"},
                "revision_items": {"type": "array", "items": {"type": "object"}},
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
                    "description": "Research Graph or scoped planner input object, path or ref"
                },
                "artifact": {"type": "object"},
                "review_id": {"type": "string"},
                "attempt": {"type": "integer"},
                "previous_decision_ref": {"type": "string"},
                "producer_revision_response": {"type": "object"},
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
        "name": "research_review_prepare",
        "description": "Validate one review_task@1, enforce one artifact and hydrate only that "
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
            "properties": {"bundle": {"description": "the bundle object, or a path to a JSON file"}},
            "required": ["bundle"],
        },
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
                       "Validate the input and run the full Research Graph with isolated Codex "
                       "workers. Defaults to pause/resume user gates because MCP tools cannot "
                       "read interactive stdin; use gates='auto' only for smoke/dev runs.",
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
                    "enum": ["pause", "auto"],
                    "description": "pause for human gate handoff/resume (default), auto for dev smoke.",
                },
                "resume_token": {
                    "type": "string",
                    "description": "Token from an awaiting_user response to resume a paused run.",
                },
                "decisions": {
                    "type": "object",
                    "description": "Gate decisions keyed by gate name when resuming.",
                },
            },
        },
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


DISPATCH = {
    "research_front_door": _front_door,
    "research_node_input": _node_input,
    "research_planner_prepare": _planner_prepare,
    "research_planner_finalize": _planner_finalize,
    "research_plan_review_task": _plan_review_task,
    "research_provider_status": _provider_status,
    "research_domain_prepare": _domain_prepare,
    "research_metadata_search": _metadata_search,
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
    "research_web_case_extract": _web_case_extract,
    "research_review_prepare": _review_prepare,
    "research_review_finalize": _review_finalize,
    "research_finalize": _finalize,
    "research_run_stub": _run_stub,
    "research_run_codex": _run_codex,
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
        if name != "research":
            return _error(mid, -32602, f"unknown prompt {name!r}")
        args = params.get("arguments") or {}
        context = args.get("context")
        if not context:
            return _error(mid, -32602, "missing required prompt argument 'context'")
        return _result(mid, _research_prompt(context))
    if method == "tools/list":
        return _result(mid, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        fn = DISPATCH.get(name)
        if fn is None:
            return _error(mid, -32602, f"unknown tool {name!r}")
        try:
            out = fn(params.get("arguments") or {})
            return _result(mid, {"content": [{"type": "text",
                                              "text": json.dumps(out, ensure_ascii=False)}]})
        except Exception as exc:  # tool error -> result with isError, not a protocol error
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
