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
