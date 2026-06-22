## Host Adapter: Claude Code

- Call `research_web_case_extract` only for cases approved at the Human Source Selection Gate.
- Pass the approved source URL and consume the persisted page artifact reference.
- Never browse directly or place credentials in the agent context.
- Emit a compact evidence card and do not forward full page text downstream.
