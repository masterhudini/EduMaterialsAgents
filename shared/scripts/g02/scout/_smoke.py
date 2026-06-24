"""Phase A smoke runner for Scout inside EduMaterials.

Run from the repository root:

    python shared/scripts/g02/scout/_smoke.py "value at risk garch" -n 5

or with module syntax after adding shared/scripts to PYTHONPATH:

    PYTHONPATH=shared/scripts python -m g02.scout._smoke "value at risk garch" -n 5

The runner intentionally disables LLM verification and query expansion. Phase A
checks the deterministic Scout core only: live search, legal OA retrieval,
ranking and manifest generation. Host-model LLM integration belongs to a later
block.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow direct execution as ``python shared/scripts/g02/scout/_smoke.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from g02 import scout_request  # noqa: E402
from g02.scout import runtime  # noqa: E402
from g02.scout.engine import apply_selection, run_student  # noqa: E402
from g02.scout.providers import build_resolvers, build_search_providers, parse_sources  # noqa: E402
from g02.scout.state_store import ScoutStore  # noqa: E402


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _float_at_least_zero(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="g02.scout._smoke",
        description="Scout standalone smoke inside EduMaterials",
    )
    parser.add_argument("topic", nargs="?", help="Topic or keywords")
    parser.add_argument("-n", type=_positive_int, default=None, help="Target paper count")
    parser.add_argument("--email", default="", help="Polite-pool contact email")
    parser.add_argument(
        "--plan-json",
        default="",
        help="Path or artifact:// ref to a research_plan@1 artifact; requires --topic-id for multi-topic plans",
    )
    parser.add_argument("--topic-id", default="", help="Topic id to use from --plan-json")
    parser.add_argument(
        "--workspace",
        default="",
        help="Override Scout workspace; default: EMAGENTS_HOME/.emagents + g02/scout",
    )
    parser.add_argument(
        "--out",
        default="",
        help="PDF directory; default: <workspace>/runs/<run_id>/pdf",
    )
    parser.add_argument("--run-id", default="", help="Stable run id for repeatable smoke paths")
    parser.add_argument("--intent", default="", help="Optional intent used by token pre-ranking")
    parser.add_argument("--lang", default="", choices=["pl", "en", "both"], help="Search language override")
    parser.add_argument("--sources", default="", help="Extra sources, for example: arxiv,core,crossref")
    parser.add_argument("--openalex-api-key", default="", help="OpenAlex API key; defaults to env")
    parser.add_argument("--s2-api-key", default="", help="Semantic Scholar API key; defaults to env")
    parser.add_argument("--core-api-key", default="", help="CORE API key; defaults to env")
    parser.add_argument(
        "--polite-sleep",
        type=_float_at_least_zero,
        default=None,
        help="Delay between provider calls; defaults to POLITE_SLEEP_SECONDS or 1.0",
    )
    parser.add_argument(
        "--dedup-cross-run",
        action="store_true",
        help="Skip titles already downloaded in this Scout workspace",
    )
    parser.add_argument(
        "--no-store",
        action="store_true",
        help="Do not use the Scout sqlite store during this smoke run",
    )
    parser.add_argument(
        "--verify-llm",
        action="store_true",
        help="Accepted for compatibility, but ignored in Phase A",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    request = None
    if args.plan_json:
        if args.topic:
            parser.error("pass either a positional topic or --plan-json, not both")
        plan = scout_request.load_research_plan(args.plan_json)
        requests = scout_request.build_scout_search_requests(plan)
        request = scout_request.select_request(requests, args.topic_id or None)
        validation = scout_request.validate_scout_search_request(request)
        if not validation["ok"]:
            parser.error("invalid scout_search_request@1: " + "; ".join(validation["errors"]))
        topic = request["query"]
        n = args.n if args.n is not None else request.get("target_n", 5)
        intent = args.intent.strip() or request.get("intent", "")
        search_lang = args.lang or request.get("lang", "both")
        year_from = request.get("year_from")
        year_to = request.get("year_to")
        work_type = request.get("work_type", "")
        facets = request.get("keywords") or None
        facets_required = [request["query"]] if facets else None
    else:
        if not args.topic:
            parser.error("topic is required unless --plan-json is provided")
        topic = args.topic
        n = args.n if args.n is not None else 5
        intent = args.intent
        search_lang = args.lang or "both"
        year_from = None
        year_to = None
        work_type = ""
        facets = None
        facets_required = None

    keys = runtime.provider_keys()
    try:
        openalex_api_key = runtime.require_openalex_api_key(args.openalex_api_key)
    except runtime.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    s2_api_key = args.s2_api_key.strip() or keys["s2_api_key"]
    core_api_key = args.core_api_key.strip() or keys["core_api_key"]
    email = args.email.strip() or runtime.contact_email()
    polite_sleep = args.polite_sleep
    if polite_sleep is None:
        polite_sleep = runtime.env_float("POLITE_SLEEP_SECONDS", 1.0)

    run_id = runtime.safe_segment(args.run_id) if args.run_id else runtime.make_run_id()
    workspace = runtime.workspace_dir(args.workspace or None)
    pdf_dir = Path(args.out).expanduser().resolve() if args.out else runtime.pdf_dir(run_id, workspace)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    source_names = parse_sources(args.sources or runtime.env_str("SOURCES"))
    extra_search = build_search_providers(
        source_names,
        core_api_key=core_api_key,
        consensus_api_key="",
        openrouter_key="",
    )
    extra_resolvers = build_resolvers(source_names, core_api_key=core_api_key)
    store = None if args.no_store else ScoutStore(workspace)

    def progress(event: str, message: str) -> None:
        print(f"  [{event}] {message}")

    print(f"Scout smoke: run_id={run_id}, n={n}")
    print(f"  workspace: {workspace}")
    print(f"  pdf_dir  : {pdf_dir}")
    if request:
        print(f"  topic_id : {request['topic_id']}")
    if not email:
        print("  warning  : no contact email; OpenAlex/Unpaywall may throttle harder")
    if args.verify_llm:
        print("  warning  : --verify-llm is ignored in Phase A; host LLM bridge is not wired yet")

    result = run_student(
        topic,
        n,
        email,
        pdf_dir,
        store=store,
        polite_sleep=polite_sleep,
        intent=intent,
        year_from=year_from,
        year_to=year_to,
        work_type=work_type,
        verify_llm=False,
        openrouter_key="",
        search_lang=search_lang,
        query_expansion=False,
        facets=facets,
        facets_required=facets_required,
        openalex_api_key=openalex_api_key,
        s2_api_key=s2_api_key,
        extra_search=extra_search,
        extra_resolvers=extra_resolvers,
        quota_canonical=request.get("quota_canonical") if request else None,
        recency_year_from=request.get("recency_year_from") if request else None,
        snowball=request.get("snowball", False) if request else False,
        dedup_cross_run=args.dedup_cross_run,
        progress=progress,
    )

    print("\nResult")
    print(f"  OpenAlex candidates : {result.openalex_total}")
    print(f"  Deduped pool        : {result.total_found}")
    print(f"  Open Access         : {result.oa_count} ({result.oa_coverage:.0%})")
    print(f"  Downloaded PDFs     : {len(result.downloaded)}/{n}")
    print(f"  Stubs               : {len(result.stubs)}")
    print(f"  Rejected            : {len(result.rejected)}")
    print(f"  Manifest invariant  : {'OK' if result.manifest_ok else 'FAILED'}")

    if result.items:
        selected = [item["filename"] for item in result.items[:n] if item.get("filename")]
        selection = apply_selection(pdf_dir, result.items, selected)
        print(f"  Selected            : {len(selection['selected'])}")
        print(f"  Reserved            : {len(selection['reserved'])}")

    return 0 if result.manifest_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
