## Host Adapter: Claude Code

- Enter through the skill and keep it as the only conversational surface for the Solution Graph.
- Invoke graph nodes through the Task/Agent tool with `subagent_type` equal to the manifest node name
  (e.g. `g03-a01-solution-architect`); pass only the scoped bundle and persist produced artifact refs
  between calls.
- The deterministic seams are the g03 CLI (`shared/scripts/g03/g03_flow.py`): `front-door` validates +
  registers the input; `inputs --node <name>` shows a node's scoped bundle; the run/freeze/emit produce
  the `solution_blueprint@1` deliverable. Do not construct installation paths in prompt logic.
