# commands — slash-command entry points

One Markdown file per command: `commands/<name>.md`. A command is a thin front door that
routes into an orchestrator skill. Register every command in `plugin.json`.

## File convention (see inspiration/commands/build-stack.md)

```yaml
---
description: One line shown in the command list.
argument-hint: "[what to research / the approved intake bundle]"
---

# /<name>

## Usage
...

## What it does
Routes into the `<orchestrator>` skill, which runs the <graph> phase ...
```

## To create

- `research.md` (e.g. `/research`) — entry into `research-orchestrator`. Takes the approved
  intake bundle / research request and starts the Research Graph run.
