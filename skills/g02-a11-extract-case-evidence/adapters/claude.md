## Host Adapter: Claude Code

- Call `research_web_case_extract` with the final selection ref, market candidate ref and source ID.
- Consume only the returned bounded untrusted-content artifact. Never supply or fetch a URL directly.
- Never browse directly or place credentials in the agent context.
- Emit a compact evidence card and do not forward full page text downstream.
