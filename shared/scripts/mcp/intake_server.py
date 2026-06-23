"""Intake / Understanding Graph (g01) MCP server — stdio JSON-RPC, pure stdlib.

Exposes the deterministic, flow-level seams of g01 so any host (Claude/Codex) drives the graph
through one stable surface, mirroring the Research Graph server. g01 is thin: it has no per-agent
deterministic operations yet, so only the boundary/flow tools are published.

Tools: intake_front_door, intake_node_input, intake_finalize, intake_run_stub, intake_run_codex.
Prompt: intake (semantic 'zrob intake' entry over an intake_graph_input bundle).
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # -> shared/scripts

from g01 import g01_flow as gf  # noqa: E402
from g01 import intake, pdf_extract  # noqa: E402
from core import graphs, handoff  # noqa: E402
from mcp import server_core  # noqa: E402

SERVER_INFO = {"name": "edu-materials-intake", "version": "0.1.0"}


# ---- tool implementations (return JSON-serializable values) --------------

def _upload(args: dict):
    return intake.upload(args["pdf_path"], hints=args.get("hints"),
                         ingestion_profile=args.get("ingestion_profile"),
                         task_id=args.get("task_id"))


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
    return handoff.emit_handoff(bundle, gf.OUTPUT_CONTRACT, name="intake_bundle")  # inline


def _run_stub(args: dict):
    return gf.run(gf.front_door(args["context"])["ref"])


def _run_codex(args: dict):
    """Run or resume g01 through Codex workers. MCP is not an interactive stdin surface, so the
    default gate behavior is pause/resume; human approval is never simulated."""
    if args.get("gates", "pause") != "pause":
        raise ValueError("Codex runs require gates='pause'")
    runner = gf.make_g01_codex_runner()
    resume_token = args.get("resume_token")
    if resume_token:
        return gf.run(None, node_runner=runner, pause_on_gate=True,
                      resume_token=resume_token, decisions=args.get("decisions"))
    context = args.get("context")
    if not context:
        raise ValueError("context is required when resume_token is absent")
    return gf.run(gf.front_door(context)["ref"], node_runner=runner, pause_on_gate=True)


def _pdf_extract(args: dict):
    return pdf_extract.extract(args["input"], visual_policy=args.get("visual_policy", "pending"))


def _slide_views(args: dict):
    return pdf_extract.slide_views(args["input"], visual_policy=args.get("visual_policy", "pending"))


_HOSTED = server_core.hosted_handlers(gf)   # run_hosted / resume / get_artifact, shared across graphs


def _understanding_finalize(args: dict):
    return intake.finalize_understanding(args["task_id"], args["understanding"])


def _synthesis_finalize(args: dict):
    return intake.finalize_synthesis(args["task_id"], args["research_graph_input"])


_CONTEXT = {"type": "string", "description": "path or artifact:// ref to an intake_graph_input bundle"}

TOOLS = [
    {"name": "intake_upload",
     "description": "Copy a lecture PDF into the project artifact store and return a validated "
                    "intake_graph_input@1 descriptor {ref, task_id, pdf_ref, filename}. The returned "
                    "ref feeds intake_run_stub / intake_run_codex / intake_front_door directly.",
     "inputSchema": {"type": "object", "required": ["pdf_path"],
                     "properties": {"pdf_path": {"type": "string", "description": "path to a lecture PDF"},
                                    "hints": {"type": "object",
                                              "description": "optional title/course/audience/language hints"},
                                    "ingestion_profile": {"type": "object"},
                                    "task_id": {"type": "string"}}}},
    {"name": "intake_front_door",
     "description": "Validate an intake_graph_input bundle, store it and return {ref, task_id}.",
     "inputSchema": {"type": "object", "required": ["context"], "properties": {"context": _CONTEXT}}},
    {"name": "intake_pdf_extract",
     "description": "Extract page text from a PDF using optional local pypdf. Returns a validated "
                    "pdf_extract_result@1. If pypdf is absent, returns dependency_missing instead "
                    "of failing the host.",
     "inputSchema": {"type": "object", "required": ["input"],
                     "properties": {"input": {"type": ["object", "string"],
                                               "description": "intake_graph_input object/ref/path, PDF artifact ref or PDF path"},
                                    "visual_policy": {"type": "string",
                                                      "enum": ["none", "pending"]}}}},
    {"name": "intake_slide_views",
     "description": "Build and store slide_views@1 from a PDF, intake_graph_input or "
                    "pdf_extract_result@1. Uses optional local pypdf through intake_pdf_extract "
                    "when raw PDF input is supplied.",
     "inputSchema": {"type": "object", "required": ["input"],
                     "properties": {"input": {"type": ["object", "string"],
                                               "description": "PDF/intake/pdf_extract_result object, path or artifact ref"},
                                    "visual_policy": {"type": "string",
                                                      "enum": ["none", "pending"]}}}},
    {"name": "intake_node_input",
     "description": "Show the scoped input each g01 agent node receives (all nodes, or one --node).",
     "inputSchema": {"type": "object", "required": ["ref"],
                     "properties": {"ref": {"type": "string", "description": "ref from intake_front_door"},
                                    "node": {"type": "string", "description": "restrict to this node name"}}}},
    {"name": "intake_run_stub",
     "description": "Run the whole Intake Graph with no-op stub nodes (no LLM) and emit research_graph_input@1.",
     "inputSchema": {"type": "object", "required": ["context"], "properties": {"context": _CONTEXT}}},
    {"name": "intake_run_codex",
     "description": "Run/resume the Intake Graph through Codex workers with pause/resume gates; "
                    "returns research_graph_input@1 or an awaiting_user resume token.",
     "inputSchema": {"type": "object",
                     "properties": {"context": _CONTEXT,
                                    "gates": {"type": "string", "enum": ["pause"]},
                                    "resume_token": {"type": "string"},
                                    "decisions": {"type": "object"}}}},
    {"name": "intake_run_hosted",
     "description": "Start a HOST-DRIVEN Intake run (no nested codex): deterministic nodes run "
                    "in-process; for each LLM node the engine pauses and returns "
                    "{status:'awaiting_node', run_token, node, input, upstream, finalize_op}. You run "
                    "that node, call its finalize_op, then intake_resume with node_results. The engine "
                    "then returns {status:'awaiting_review', node, artifact_ref, review_profile} for "
                    "EVERY producer — you play the reviewer and resume with review_decisions. User "
                    "gates return {status:'awaiting_user'}. Use this when driving from a Codex session.",
     "inputSchema": {"type": "object", "required": ["context"], "properties": {"context": _CONTEXT}}},
    {"name": "intake_resume",
     "description": "Resume a host-driven run with exactly one of: node_results={node: artifact_ref} "
                    "(after running a node + its finalize_op); review_decisions={node: {decision, "
                    "findings}} where decision is APPROVED|REVISE|BLOCKED (after reviewing an "
                    "awaiting_review artifact); node_failures={node: {summary, issues}} (if you cannot "
                    "produce the node); or decisions={gate: ...} (for a user gate). Returns the next "
                    "awaiting_node / awaiting_review / awaiting_user, the research_graph_input@1 "
                    "handoff when done, or a failed descriptor.",
     "inputSchema": {"type": "object", "required": ["run_token"],
                     "properties": {"run_token": {"type": "string"},
                                    "node_results": {"type": "object",
                                                     "description": "{node_name: artifact:// ref from its finalize_op}"},
                                    "review_decisions": {"type": "object",
                                                         "description": "{node_name: {decision, findings}}"},
                                    "node_failures": {"type": "object",
                                                      "description": "{node_name: {summary, issues}}"},
                                    "decisions": {"type": "object",
                                                  "description": "{gate_name: decision} for a user gate"}}}},
    {"name": "intake_get_artifact",
     "description": "Hydrate (read) an artifact:// ref, e.g. an upstream slide_views the current "
                    "hosted node needs as input.",
     "inputSchema": {"type": "object", "required": ["ref"],
                     "properties": {"ref": {"type": "string"}}}},
    {"name": "intake_understanding_finalize",
     "description": "G01-A02 write path: validate the produced intake_understanding@1 and store it "
                    "server-side; returns envelope@1 with the artifact ref in produced[]. Use this as "
                    "the final step instead of writing the artifact from the worker.",
     "inputSchema": {"type": "object", "required": ["task_id", "understanding"],
                     "properties": {"task_id": {"type": "string"},
                                    "understanding": {"type": "object",
                                                      "description": "the intake_understanding@1 artifact"}}}},
    {"name": "intake_synthesis_finalize",
     "description": "G01-A03 write path: validate the produced research_graph_input@1 and store it "
                    "server-side; returns envelope@1 with the artifact ref in produced[]. Use this as "
                    "the final step instead of writing the artifact from the worker.",
     "inputSchema": {"type": "object", "required": ["task_id", "research_graph_input"],
                     "properties": {"task_id": {"type": "string"},
                                    "research_graph_input": {"type": "object",
                                                             "description": "the research_graph_input@1 artifact"}}}},
    {"name": "intake_finalize",
     "description": "Validate a result bundle (path or inline) against research_graph_input@1 and emit the handoff.",
     "inputSchema": {"type": "object", "required": ["bundle"],
                     "properties": {"bundle": {"type": ["string", "object"],
                                               "description": "path to, or inline, research_graph_input@1 bundle"}}}},
]

DISPATCH = {
    "intake_upload": _upload,
    "intake_front_door": _front_door,
    "intake_pdf_extract": _pdf_extract,
    "intake_slide_views": _slide_views,
    "intake_node_input": _node_input,
    "intake_run_stub": _run_stub,
    "intake_run_codex": _run_codex,
    "intake_run_hosted": _HOSTED["run_hosted"],
    "intake_resume": _HOSTED["resume"],
    "intake_get_artifact": _HOSTED["get_artifact"],
    "intake_understanding_finalize": _understanding_finalize,
    "intake_synthesis_finalize": _synthesis_finalize,
    "intake_finalize": _finalize,
}

PROMPTS = [
    {"name": "intake",
     "description": "Semantic 'zrob intake' / 'zrób intake' entrypoint for running the Intake Graph "
                    "over an intake_graph_input bundle (uploaded lecture PDF).",
     "arguments": [{"name": "context",
                    "description": "Path or artifact:// ref to an intake_graph_input bundle.",
                    "required": True}]},
]


def _prompt(name: str, args: dict) -> dict:
    context = args.get("context")
    if not context:
        raise ValueError("missing required prompt argument 'context'")
    return {
        "description": "Semantic 'zrob intake' entrypoint for an intake_graph_input bundle.",
        "messages": [{"role": "user", "content": {"type": "text", "text": (
            "The user asked to zrob intake / zrób intake. Use the edu-materials-agents "
            f"orchestrate-intake workflow for this intake_graph_input bundle: {context}\n\n"
            "For the Codex workflow, call intake_run_codex with gates='pause' so the user intake "
            "gate returns an awaiting_user resume token. For a deterministic wiring check only, "
            "use intake_run_stub.")}}],
    }


handle = server_core.make_handle(server_info=SERVER_INFO, tools=TOOLS, dispatch=DISPATCH,
                                 prompts=PROMPTS, prompt_handler=_prompt)


def main() -> None:
    server_core.run_loop(handle)


if __name__ == "__main__":
    main()
