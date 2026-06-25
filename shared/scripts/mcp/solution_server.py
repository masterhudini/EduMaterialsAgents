"""Solution Graph (g03) MCP server — stdio JSON-RPC, pure stdlib.

Exposes the deterministic, flow-level seams of g03 so any host (Claude/Codex) drives the graph
through one stable surface, mirroring the Intake/Research servers. g03 is thin: it has no per-agent
deterministic operations (no PDF/upload seam), so only the boundary/flow tools and the producer
write path are published.

Tools: solution_front_door, solution_node_input, solution_finalize, solution_run_stub,
solution_run_codex, solution_run_hosted, solution_resume, solution_get_artifact,
solution_blueprint_build, solution_blueprint_render, solution_blueprint_finalize.
Prompt: solution (semantic 'zrob solution' entry over a solution_graph_input request).
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from g03 import g03_flow as gf  # noqa: E402
from g03 import blueprint as bp  # noqa: E402
from g03 import render as renderer  # noqa: E402
from g03 import solution  # noqa: E402
from core import graphs, handoff  # noqa: E402
from mcp import server_core  # noqa: E402

SERVER_INFO = {"name": "edu-materials-solution", "version": "0.1.0"}


# ---- tool implementations (return JSON-serializable values) --------------

def _front_door(args: dict):
    return gf.front_door(args["context"])


def _node_input(args: dict):
    inp = gf._load_any(args["ref"])
    inputs = gf.node_input_map(inp, graphs.load(gf.GRAPH_ID))
    node = args.get("node")
    if not node:
        return inputs
    if node not in inputs:
        raise ValueError(f"no agent node {node!r}; have: {', '.join(inputs)}")
    return {node: inputs[node]}


def _finalize(args: dict):
    bundle = args["bundle"]
    if isinstance(bundle, str):                       # a path
        return gf.finalize(bundle)
    return handoff.emit_handoff(bundle, gf.OUTPUT_CONTRACT, name="solution_blueprint")  # inline


def _run_stub(args: dict):
    return gf.run(gf.front_door(args["context"])["ref"])


def _run_codex(args: dict):
    """Run or resume g03 through Codex workers. MCP is not an interactive stdin surface, so the
    default gate behavior is pause/resume; human approval is never simulated."""
    if args.get("gates", "pause") != "pause":
        raise ValueError("Codex runs require gates='pause'")
    runner = gf.make_g03_codex_runner()
    resume_token = args.get("resume_token")
    if resume_token:
        return gf.run(None, node_runner=runner, pause_on_gate=True,
                      resume_token=resume_token, decisions=args.get("decisions"))
    context = args.get("context")
    if not context:
        raise ValueError("context is required when resume_token is absent")
    return gf.run(gf.front_door(context)["ref"], node_runner=runner, pause_on_gate=True)


_HOSTED = server_core.hosted_handlers(gf)   # run_hosted / resume / get_artifact, shared across graphs


def _blueprint_finalize(args: dict):
    return solution.finalize_blueprint(args["task_id"], args["blueprint"])


def _blueprint_build(args: dict):
    return bp.build_blueprint(args["context"])


def _blueprint_render(args: dict):
    if "blueprint" in args:
        value = args["blueprint"]
    elif "context" in args:
        value = bp.build_blueprint(args["context"])
    else:
        raise ValueError("solution_blueprint_render requires blueprint or context")
    return renderer.render_blueprint(value, persist=bool(args.get("persist")))


def _trace(args: dict):
    from core import event_log
    return event_log.open_log(gf.GRAPH_ID, run_id=args["run_id"]).summary()


_CONTEXT = {"type": ["object", "string"],
            "description": "the g03 boundary: a request object {lecture_baseline_ref|lecture_baseline, "
                           "research_bundle_ref|research_bundle, research_bundle_kind?, task_id?, "
                           "output_language?} joining g01's lecture_baseline@1 and g02's "
                           "solution_input_candidate@1, with legacy user_approved_research_bundle@1 "
                           "still accepted, a path to such a request JSON, or an artifact:// ref to "
                           "an existing solution_graph_input@1"}

TOOLS = [
    {"name": "solution_front_door",
     "description": "Validate a dual-input G03 request, store lecture/research sides as needed and return {ref, task_id}.",
     "inputSchema": {"type": "object", "required": ["context"], "properties": {"context": _CONTEXT}}},
    {"name": "solution_node_input",
     "description": "Show the scoped input each g03 agent node receives (all nodes, or one --node).",
     "inputSchema": {"type": "object", "required": ["ref"],
                     "properties": {"ref": {"type": "string", "description": "ref from solution_front_door"},
                                    "node": {"type": "string", "description": "restrict to this node name"}}}},
    {"name": "solution_run_stub",
     "description": "Run the whole Solution Graph with no-op stub nodes (no LLM) and emit solution_blueprint@1.",
     "inputSchema": {"type": "object", "required": ["context"], "properties": {"context": _CONTEXT}}},
    {"name": "solution_run_codex",
     "description": "Run/resume the Solution Graph through Codex workers with pause/resume gates; "
                    "returns solution_blueprint@1 or an awaiting_user resume token.",
     "inputSchema": {"type": "object",
                     "properties": {"context": _CONTEXT,
                                    "gates": {"type": "string", "enum": ["pause"]},
                                    "resume_token": {"type": "string"},
                                    "decisions": {"type": "object"}}}},
    {"name": "solution_run_hosted",
     "description": "Start a HOST-DRIVEN Solution run (no nested codex): for the LLM node the engine "
                    "pauses and returns {status:'awaiting_node', resume_token, node, input, upstream, "
                    "finalize_op}. You run that node, call its finalize_op, then solution_resume with "
                    "node_results. The engine then returns {status:'awaiting_review', node, "
                    "artifact_ref, review_profile} for EVERY producer — you play the reviewer and "
                    "resume with review_decisions. User gates return {status:'awaiting_user'}. Use "
                    "this when driving from a Codex session.",
     "inputSchema": {"type": "object", "required": ["context"], "properties": {"context": _CONTEXT}}},
    {"name": "solution_resume",
     "description": "Resume a host-driven run with exactly one of: node_results={node: artifact_ref} "
                    "(after running a node + its finalize_op); review_decisions={node: {decision, "
                    "findings}} where decision is APPROVED|REVISE|BLOCKED (after reviewing an "
                    "awaiting_review artifact); node_failures={node: {summary, issues}} (if you cannot "
                    "produce the node); or decisions={gate: ...} (for a user gate). Returns the next "
                    "awaiting_node / awaiting_review / awaiting_user, the solution_blueprint@1 "
                    "deliverable when done, or a failed descriptor.",
     "inputSchema": {"type": "object", "required": ["resume_token"],
                     "properties": {"resume_token": {"type": "string"},
                                    "node_results": {"type": "object",
                                                     "description": "{node_name: artifact:// ref from its finalize_op}"},
                                    "review_decisions": {"type": "object",
                                                         "description": "{node_name: {decision, findings}}"},
                                    "node_failures": {"type": "object",
                                                      "description": "{node_name: {summary, issues}}"},
                                    "decisions": {"type": "object",
                                                  "description": "{gate_name: decision} for a user gate"},
                                    "usage_reports": {"type": "object",
                                                      "description": "OPTIONAL token tracing: {node_name: "
                                                                     "{input_tokens, output_tokens, model}}. Attach "
                                                                     "the model usage YOU spent playing the node — "
                                                                     "only the host knows it. Omit if unavailable."}}}},
    {"name": "solution_trace",
     "description": "Return the trace summary for a run: per-agent/per-tool durations and per-node "
                    "token usage (input/output) rolled up, plus run totals. Pass the run_token "
                    "(= resume_token) as run_id.",
     "inputSchema": {"type": "object", "required": ["run_id"],
                     "properties": {"run_id": {"type": "string", "description": "the run's resume_token"}}}},
    {"name": "solution_get_artifact",
     "description": "Hydrate (read) an artifact:// ref, e.g. an upstream card bundle the current "
                    "hosted node needs as input.",
     "inputSchema": {"type": "object", "required": ["ref"],
                     "properties": {"ref": {"type": "string"}}}},
    {"name": "solution_blueprint_build",
     "description": "Build and validate an inline solution_blueprint@1 from a G03 context. This does "
                    "not persist; call solution_blueprint_finalize to store the result.",
     "inputSchema": {"type": "object", "required": ["context"], "properties": {"context": _CONTEXT}}},
    {"name": "solution_blueprint_render",
     "description": "Render a solution_blueprint@1, or a G03 context that can build one, into a "
                    "human-readable Markdown plan plus a short inline console summary. This is a "
                    "view only; it does not replace the solution_blueprint@1 deliverable.",
     "inputSchema": {"type": "object",
                     "properties": {"blueprint": {"type": ["object", "string"],
                                                  "description": "solution_blueprint@1 object, descriptor, path or artifact:// ref"},
                                    "context": _CONTEXT,
                                    "persist": {"type": "boolean",
                                                "description": "When true, store the Markdown view as an artifact."}}}},
    {"name": "solution_blueprint_finalize",
     "description": "G03-A01 write path: validate the produced solution_blueprint@1 and store it "
                    "server-side; returns envelope@1 with the artifact ref in produced[]. Use this as "
                    "the final step instead of writing the artifact from the worker.",
     "inputSchema": {"type": "object", "required": ["task_id", "blueprint"],
                     "properties": {"task_id": {"type": "string"},
                                    "blueprint": {"type": "object",
                                                  "description": "the solution_blueprint@1 artifact"}}}},
    {"name": "solution_finalize",
     "description": "Validate a result bundle (path or inline) against solution_blueprint@1 and emit the handoff.",
     "inputSchema": {"type": "object", "required": ["bundle"],
                     "properties": {"bundle": {"type": ["string", "object"],
                                               "description": "path to, or inline, solution_blueprint@1 bundle"}}}},
]

DISPATCH = {
    "solution_front_door": _front_door,
    "solution_node_input": _node_input,
    "solution_run_stub": _run_stub,
    "solution_run_codex": _run_codex,
    "solution_run_hosted": _HOSTED["run_hosted"],
    "solution_resume": _HOSTED["resume"],
    "solution_get_artifact": _HOSTED["get_artifact"],
    "solution_trace": _trace,
    "solution_blueprint_build": _blueprint_build,
    "solution_blueprint_render": _blueprint_render,
    "solution_blueprint_finalize": _blueprint_finalize,
    "solution_finalize": _finalize,
}

PROMPTS = [
    {"name": "solution",
     "description": "Semantic 'zrob solution' / 'zrób solution' entrypoint for running the Solution "
                    "Graph over a solution_graph_input request. Official research input is "
                    "solution_input_candidate@1; legacy user_approved_research_bundle@1 is accepted.",
     "arguments": [{"name": "context",
                    "description": "Path, inline object or artifact:// ref for a G03 front-door request.",
                    "required": True}]},
]


def _prompt(name: str, args: dict) -> dict:
    context = args.get("context")
    if not context:
        raise ValueError("missing required prompt argument 'context'")
    return {
        "description": "Semantic 'zrob solution' entrypoint for a G03 solution_graph_input request.",
        "messages": [{"role": "user", "content": {"type": "text", "text": (
            "The user asked to zrob solution / zrób solution. Use the edu-materials-agents "
            f"orchestrate-solution workflow for this G03 request: {context}\n\n"
            "The official research side is solution_input_candidate@1 with "
            "research_bundle_kind='solution_input_candidate'. Legacy user_approved_research_bundle@1 "
            "continues to work when explicitly provided or inferred.\n\n"
            "For the Codex workflow, call solution_run_codex with gates='pause' so the user solution "
            "gate returns an awaiting_user resume token. For a deterministic wiring check only, use "
            "solution_run_stub. After a solution_blueprint@1 is produced or approved, call "
            "solution_blueprint_render to present the Markdown plan and inline summary.")}}],
    }


handle = server_core.make_handle(server_info=SERVER_INFO, tools=TOOLS, dispatch=DISPATCH,
                                 prompts=PROMPTS, prompt_handler=_prompt)


def main() -> None:
    server_core.run_loop(handle)


if __name__ == "__main__":
    main()
