# Runtime provider configuration

Copy `g02.providers.example.json` to
`<project>/.emagents/config/g02-providers.json` and adjust enabled providers, limits, cache and
relative runtime subdirectories. The runtime also accepts an explicit path through
`EMAGENTS_RESEARCH_CONFIG`.

Resolution order is: a path passed directly to the MCP operation, `EMAGENTS_RESEARCH_CONFIG`,
the project file above, then the bundled example. The bundled example is a safe starting profile,
but its enabled OpenAlex service requires both the contact environment variable and an API key
before provider startup can succeed. arXiv requires the contact environment variable. These
requirements were checked against official provider documentation on 2026-06-21.

Secrets and contact data never belong in JSON configuration. Use environment variables:

- `EMAGENTS_RESEARCH_CONTACT_EMAIL`, required when OpenAlex or arXiv is enabled;
- `OPENALEX_API_KEY`, required when OpenAlex is enabled and never logged;
- `SEMANTIC_SCHOLAR_API_KEY`, optional, recommended and never logged.

Provider references:

- OpenAlex authentication: <https://docs.openalex.org/guides/authentication>
- Semantic Scholar API tutorial: <https://www.semanticscholar.org/product/api/tutorial>
- arXiv API user manual: <https://info.arxiv.org/help/api/user-manual.html>

All configured subdirectories must remain relative to `<project>/.emagents/`. Provider endpoints
are fixed in code to official HTTPS origins and cannot be replaced through configuration.

## Planned first-run credential setup

Manual environment-variable setup is temporary and remains the development and test path until a
first-run setup flow is implemented. The local product must request the following values together
in one credential step:

- `EMAGENTS_RESEARCH_CONTACT_EMAIL`;
- `OPENALEX_API_KEY`;
- `TAVILY_API_KEY`.

The same step may offer `SEMANTIC_SCHOLAR_API_KEY`, but it must be explicitly optional and allow
the user to continue without it. arXiv does not require an API key. Tavily is collected together
with OpenAlex and the contact email even when the A11 runtime slice is not active yet, so later
activation of Market Cases does not require a second onboarding flow.

Production credentials must be stored in the host operating-system credential store or an
equivalent host secret manager. They must never enter graph intake, JSON provider configuration,
LLM context, artifacts, cache, logs or repository files. First-run validation must report only
secret-free readiness, support retry and credential replacement, and distinguish missing
credentials from failed network connectivity.

## Planned A11 Tavily configuration

The A11 scaffold does not yet expose Tavily operations. Its runtime slice will read the credential
from `TAVILY_API_KEY`, keep endpoints fixed in code and expose only a secret-free readiness status.
Do not add that key to `g02.providers.example.json`, prompts, fixtures or artifacts. Non-secret
search depth, result limits, tier-domain policy and extraction limits will be added to an explicit
versioned config together with `research_web_case_search` and `research_web_case_extract`; until
then, absence of those MCP operations is expected.

The same provider-neutral search operation will support a controlled keyless SearXNG adapter.
SearXNG is a self-hosted metasearch service, so it avoids a per-request API credential but still
requires an operator-managed instance and infrastructure. The runtime will not select arbitrary
public instances. Its non-secret administrative configuration will pin one exact origin, require
JSON output, enforce query budgets, cache, timeout, rate limiting, response-size limits and redirect
checks, and allow plain HTTP only for an explicitly configured loopback DEV instance. Planned modes
are `tavily`, `searxng` and `auto_budgeted`; free discovery does not grant the agent unrestricted
browser access. Official API reference: <https://docs.searxng.org/dev/search_api.html>.
