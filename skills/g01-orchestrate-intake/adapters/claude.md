## Host Adapter: Claude Code

- Enter through the skill and keep it as the only conversational surface for the Intake Graph.
- Invoke graph nodes through the Task/Agent tool with `subagent_type` equal to the manifest node name
  (e.g. `g01-a01-pdf-intake`); pass only the scoped bundle and persist produced artifact refs between calls.
- The deterministic seams are the g01 CLI (`shared/scripts/g01/g01_flow.py`): `front-door` validates +
  registers the input; `inputs --node <name>` shows a node's scoped bundle; the run/freeze/emit produce
  the `research_graph_input@1` handoff. Do not construct installation paths in prompt logic.
