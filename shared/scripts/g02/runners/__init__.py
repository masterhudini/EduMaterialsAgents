"""Host-specific NodeRunner implementations for the Research Graph.

A NodeRunner has the signature ``(node, ctx, log) -> envelope@1`` and is injected into
``g02_flow.run``. ``ctx`` carries ``{"input": <scoped graph input>, "upstream":
{producer_node: artifact_ref, ...}}``. The graph engine stays host-agnostic; the runner is the
per-host execution strategy (stub for wiring/tests, codex for the Codex worker path).
"""
