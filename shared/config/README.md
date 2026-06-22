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
- `TAVILY_API_KEY`, required for Tavily search and extraction and never logged.
- `CORE_API_KEY`, required only when the optional CORE resolver is enabled and never logged.

Provider references:

- OpenAlex authentication: <https://docs.openalex.org/guides/authentication>
- Semantic Scholar API tutorial: <https://www.semanticscholar.org/product/api/tutorial>
- arXiv API user manual: <https://info.arxiv.org/help/api/user-manual.html>
- Unpaywall API: <https://unpaywall.org/products/api>
- CORE API v3: <https://api.core.ac.uk/docs/v3>
- DOAB OAI and DSpace API: <https://directory.doabooks.org/oai/request?verb=Identify>
- OAPEN OAI and DSpace API: <https://library.oapen.org/oai/request?verb=Identify>

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

## A11 web provider configuration

The `web` block is active and versioned inside `literature_provider_config@1`. Tavily endpoints are
fixed in code and its key is read only from `TAVILY_API_KEY`. SearXNG is keyless but must be enabled
with one exact administrator-controlled endpoint. HTTPS is required except for an explicitly
enabled loopback DEV endpoint. Credentials in URLs, private or reserved literal addresses,
cross-origin redirects, non-JSON responses and oversized payloads are blocked.

Modes are `tavily`, `searxng` and `auto_budgeted`. The last mode uses bounded SearXNG discovery when
ready and Tavily for supplementation or priority routes. Limits are shared per task and persisted
under the configured web cache. Identical cache hits do not consume another query. Source tiers are
administrator domain lists; A11 routes may select only from their union. The model cannot provide an
endpoint, alter the mode or add a domain.

Public A11 MCP calls do not accept a configuration path. They resolve the administrator-selected
profile from `EMAGENTS_RESEARCH_CONFIG` or the standard runtime location; a test harness may inject
an explicit path only through the internal Python seam.

`research_web_case_extract` is Tavily-only. It accepts stored selection and candidate refs plus a
source ID, hydrates the referenced candidate index, verifies final `approved_for_download`
authorization and resolves the exact stored HTTPS URL. The result contains a bounded
untrusted-content artifact ref and safety flags. Official SearXNG
API reference: <https://docs.searxng.org/dev/search_api.html>.

## A06 retrieval provider configuration

The optional `retrieval` block controls legal OA resolution and bounded file retrieval. Public MCP
operations never accept a configuration path. Resolver order is approved record links and arXiv,
then Unpaywall, optional CORE, DOAB and OAPEN. Unpaywall uses the configured contact email. CORE is
disabled in the bundled example until `CORE_API_KEY` is present. DOAB is treated as a book catalog;
a landing page alone is not accepted as a document. OAPEN DSpace 6 metadata and ORIGINAL PDF
bitstreams may provide a downloadable OA book.

The downloader accepts credential-free HTTPS only, blocks private and reserved literal or resolved
addresses, strips CORE authorization on redirects, limits redirects, time, retries and bytes, and
streams into a constrained `corpus://` temporary ref. A file is promoted only after SHA-256,
content-type, `%PDF-` signature and resolver-backed identity checks. Market cases are not downloaded
by this path. They use gated `research_web_case_extract` and are copied to the same A06 run folder as
JSON with `content_boundary: untrusted_external_research`.

All metadata providers receive the fixed non-secret `User-Agent: EduMaterialsAgents/0.9`. DOAB
currently rejects Python's default `Python-urllib` identifier with HTTP 403 while its official
DSpace 6 REST endpoint remains available to identified clients. The fixed identifier is therefore
part of the deterministic transport policy, not a model-controlled header.

The human fixes the retrieval count at the Human Source Selection Gate by assigning `DOWNLOAD` to
exact source IDs and separately confirming the parsed summary. A06 attempts exactly those IDs and
rejects a confirmed set above `retrieval.limits.max_documents_per_task`. Scholarly DOWNLOAD items
produce PDFs; approved market cases produce bounded JSON files through the gated A11 extraction.
