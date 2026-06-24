"""Parallel, persistent A01 -> Scout fan-out.

The production path runs one independent process per research-plan topic.  It
does not invoke A07/A09 or either reviewed graph runner.  Cross-topic
deduplication is intentionally a post-processing index operation, so a paper
relevant to multiple topics is never skipped during retrieval.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Callable

# Allow direct execution from the repository or an installed plugin.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import contracts  # noqa: E402
from g02 import scout_request  # noqa: E402
from g02.scout import runtime  # noqa: E402
from g02.scout.engine import classify_source_metadata, clean_title, run_student  # noqa: E402
from g02.scout.providers import (  # noqa: E402
    build_resolvers,
    build_search_providers,
    parse_sources,
)

SCOUT_CORPUS_CONTRACT = "scout_retrieved_corpus@1"
SCOUT_INDEX_CONTRACT = "scout_run_index@1"
EXECUTION_PROFILE = "scout"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(_json_bytes(value))
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_task_id(value: str) -> str:
    return runtime.safe_segment(value)


def _safe_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for secret in runtime.provider_keys().values():
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _real_doi(value: object) -> str | None:
    doi = str(value or "").strip().lower()
    return doi if doi.startswith("10.") and "/" in doi else None


def _dedup_identity(item: dict) -> tuple[str, str, str]:
    doi = _real_doi(item.get("doi"))
    if doi:
        return f"doi:{doi}", "doi", doi
    title_key = clean_title(str(item.get("title") or ""))
    if not title_key:
        filename = str(item.get("filename") or "unknown")
        title_key = clean_title(Path(filename).stem) or filename.casefold()
    return f"clean_title:{title_key}", "clean_title", title_key


def _source_id(dedup_key: str) -> str:
    return "SCOUT_" + hashlib.sha256(dedup_key.encode("utf-8")).hexdigest()[:20].upper()


def _run_topic_worker(job: dict) -> dict:
    """Execute one topic in a child process without persisting secrets."""
    request = job["request"]
    pdf_dir = Path(job["pdf_dir"])
    pdf_dir.mkdir(parents=True, exist_ok=True)
    keys = runtime.provider_keys()
    openalex_api_key = runtime.require_openalex_api_key()
    email = runtime.contact_email()
    source_names = parse_sources(runtime.env_str("SOURCES"))
    extra_search = build_search_providers(
        source_names,
        core_api_key=keys["core_api_key"],
        consensus_api_key="",
        openrouter_key="",
    )
    extra_resolvers = build_resolvers(source_names, core_api_key=keys["core_api_key"])
    result = run_student(
        request["query"],
        request["target_n"],
        email,
        pdf_dir,
        store=None,
        polite_sleep=runtime.env_float("POLITE_SLEEP_SECONDS", 1.0),
        intent=request.get("intent", ""),
        year_from=request.get("year_from"),
        year_to=request.get("year_to"),
        work_type=request.get("work_type", ""),
        verify_llm=False,
        openrouter_key="",
        search_lang=request.get("lang", "both"),
        query_expansion=False,
        facets=request.get("keywords") or None,
        # Fix 3: anchor fasetowy = core_terms[:2], nie pełne query (topic.name byłoby zbyt
        # długie jako anchor i generowałoby mało trafne zapytania fasetowe).
        facets_required=(request.get("keywords") or [])[:2] or None,
        openalex_api_key=openalex_api_key,
        s2_api_key=keys["s2_api_key"],
        extra_search=extra_search,
        extra_resolvers=extra_resolvers,
        oversample=1.2,
        dedup_cross_run=False,
        # Snowball is opt-in from the approved plan. Plans without a canonical-source
        # requirement keep the previous provider-call profile.
        snowball=request.get("snowball", False),
        # Kwota canonical/recent: proporcja miejsc w target_n zarezerwowanych dla źródeł
        # kanonicznych (starsze, high-fwci, snowball). None = brak kwoty.
        quota_canonical=request.get("quota_canonical"),
        recency_year_from=request.get("recency_year_from"),
    )
    return asdict(result)


def _manifest_for_topic(topic_root: Path, result: dict | None, error: str | None) -> None:
    engine_manifest = topic_root / "pdf" / "MANIFEST.md"
    target = topic_root / "MANIFEST.md"
    if engine_manifest.is_file():
        engine_manifest.replace(target)
        return
    status = "FAILED" if error else "COMPLETED"
    lines = [
        "# MANIFEST - Scout topic",
        "",
        f"- Status: {status}",
        f"- Downloaded: {len((result or {}).get('downloaded', []))}",
        f"- Stubs: {len((result or {}).get('stubs', []))}",
        f"- Rejected: {len((result or {}).get('rejected', []))}",
    ]
    if error:
        lines.append(f"- Error: {error}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _topic_corpus(run_root: Path, plan: dict, request: dict, run_id: str,
                  result: dict) -> dict:
    topic_id = request["topic_id"]
    pdf_dir = run_root / "topics" / topic_id / "pdf"
    documents = []
    for item in result.get("items", []):
        if not isinstance(item, dict) or not item.get("filename"):
            continue
        pdf_path = pdf_dir / str(item["filename"])
        if not pdf_path.is_file():
            continue
        dedup_key, _, _ = _dedup_identity(item)
        fwci_value = item.get("fwci")
        fwci = float(fwci_value) if isinstance(fwci_value, (int, float)) \
            and not isinstance(fwci_value, bool) else None
        source_type, source_type_basis = classify_source_metadata(
            year=item.get("year") if isinstance(item.get("year"), int) else None,
            fwci=fwci,
            source=str(item.get("source") or ""),
            work_type=str(item.get("work_type") or ""),
            year_from=request.get("recency_year_from"),
        )
        if item.get("source_type") in {"canonical", "recent"}:
            source_type = item["source_type"]
        if isinstance(item.get("source_type_basis"), str) \
                and item["source_type_basis"].strip():
            source_type_basis = item["source_type_basis"].strip()
        documents.append({
            "source_id": _source_id(dedup_key),
            "local_ref": pdf_path.relative_to(run_root).as_posix(),
            "sha256": _sha256(pdf_path),
            "byte_count": pdf_path.stat().st_size,
            "doi": _real_doi(item.get("doi")),
            "title": str(item.get("title") or Path(item["filename"]).stem),
            "year": item.get("year") if isinstance(item.get("year"), int) else None,
            "fwci": fwci,
            "venue": str(item.get("venue") or "") or None,
            "work_type": str(item.get("work_type") or "") or None,
            "source_type": source_type,
            "source_type_basis": source_type_basis,
            "topic_ids": [topic_id],
        })
    corpus = {
        "schema_version": SCOUT_CORPUS_CONTRACT,
        "artifact_version": "1.0.0",
        "task_id": plan["task_id"],
        "topic_id": topic_id,
        "run_id": run_id,
        "research_plan_ref": "plan.json",
        "request_ref": f"requests/{topic_id}.json",
        "documents": documents,
        "retrieval_summary": {
            "target_count": request["target_n"],
            "downloaded_count": len(result.get("downloaded", [])),
            "stub_count": len(result.get("stubs", [])),
            "rejected_count": len(result.get("rejected", [])),
        },
    }
    validation = contracts.validate(corpus, SCOUT_CORPUS_CONTRACT)
    if not validation["ok"]:
        raise ValueError("invalid Scout corpus: " + "; ".join(validation["errors"]))
    return corpus


def _apply_cross_topic_dedup(corpora: dict[str, dict]) -> list[dict]:
    works: dict[str, dict] = {}
    document_bindings: dict[str, list[dict]] = {}
    for topic_id, corpus in corpora.items():
        for document in corpus["documents"]:
            basis_item = {
                "doi": document.get("doi"),
                "title": document.get("title"),
                "filename": Path(document["local_ref"]).name,
            }
            key, basis, identity = _dedup_identity(basis_item)
            work = works.setdefault(key, {
                "dedup_id": _source_id(key),
                "identity_basis": basis,
                "identity_value": identity,
                "doi": document.get("doi"),
                "clean_title": clean_title(document.get("title") or ""),
                "title": document.get("title") or "",
                "topic_ids": [],
                "local_refs": [],
            })
            if topic_id not in work["topic_ids"]:
                work["topic_ids"].append(topic_id)
            if document["local_ref"] not in work["local_refs"]:
                work["local_refs"].append(document["local_ref"])
            document_bindings.setdefault(key, []).append(document)
    for key, work in works.items():
        work["topic_ids"].sort()
        work["local_refs"].sort()
        for document in document_bindings[key]:
            document["source_id"] = work["dedup_id"]
            document["topic_ids"] = list(work["topic_ids"])
    return sorted(works.values(), key=lambda item: item["dedup_id"])


def _load_plan(plan_or_ref: str | dict) -> dict:
    if isinstance(plan_or_ref, dict):
        validation = contracts.validate(plan_or_ref, "research_plan@1")
        if not validation["ok"]:
            raise ValueError("invalid research_plan@1: " + "; ".join(validation["errors"]))
        return deepcopy(plan_or_ref)
    return scout_request.load_research_plan(plan_or_ref)


def run_scout_fanout(
    plan_or_ref: str | dict,
    *,
    workspace: str | Path | None = None,
    total_target: int | None = None,
    max_workers: int | None = None,
    topic_runner: Callable[[dict], dict] | None = None,
) -> dict:
    """Run and persist one complete Scout profile execution.

    ``topic_runner`` is an offline-test seam. Production calls omit it and use
    separate processes; injected test runners use threads so mocks remain local.
    """
    runtime.require_openalex_api_key()
    plan = _load_plan(plan_or_ref)
    settings = scout_request.scout_profile_settings(EXECUTION_PROFILE)
    total = total_target if total_target is not None else settings["total_target"]
    requests = scout_request.build_scout_search_requests(plan, total_target=total)
    if not requests:
        raise ValueError("research plan contains no usable Scout topics")
    if not 4 <= len(requests) <= 6:
        raise ValueError("scout profile requires a research plan with 4 to 6 topics")
    topic_ids = [request["topic_id"] for request in requests]
    if len(set(topic_ids)) != len(topic_ids):
        raise ValueError("scout profile requires unique topic_id values")
    unsafe = [topic_id for topic_id in topic_ids
              if runtime.safe_segment(topic_id) != topic_id]
    if unsafe:
        raise ValueError(f"unsafe topic_id values for persistent paths: {unsafe}")

    root = runtime.runs_dir(workspace) / _safe_task_id(plan["task_id"])
    if (root / "index.json").exists():
        raise FileExistsError(f"Scout run already finalized: {root}")
    root.mkdir(parents=True, exist_ok=True)
    _write_json(root / "plan.json", plan)
    jobs = []
    for request in requests:
        validation = scout_request.validate_scout_search_request(request)
        if not validation["ok"]:
            raise ValueError("invalid Scout request: " + "; ".join(validation["errors"]))
        topic_id = request["topic_id"]
        _write_json(root / "requests" / f"{topic_id}.json", request)
        topic_root = root / "topics" / topic_id
        (topic_root / "pdf").mkdir(parents=True, exist_ok=True)
        jobs.append({
            "request": request,
            "run_id": f"{_safe_task_id(plan['task_id'])}__{runtime.safe_segment(topic_id)}",
            "pdf_dir": str((topic_root / "pdf").resolve()),
        })

    requested_workers = max_workers or settings["max_parallel_topics"]
    worker_count = max(1, min(len(jobs), int(requested_workers)))
    runner = topic_runner or _run_topic_worker
    executor_type = ThreadPoolExecutor if topic_runner is not None else ProcessPoolExecutor
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    with executor_type(max_workers=worker_count) as executor:
        futures = {executor.submit(runner, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            topic_id = job["request"]["topic_id"]
            try:
                results[topic_id] = future.result()
            except Exception as exc:  # preserve partial artifacts and a useful index
                errors[topic_id] = _safe_error(exc)

    corpora: dict[str, dict] = {}
    topic_entries = []
    for job in jobs:
        request = job["request"]
        topic_id = request["topic_id"]
        topic_root = root / "topics" / topic_id
        result = results.get(topic_id)
        error = errors.get(topic_id)
        _manifest_for_topic(topic_root, result, error)
        if result is not None:
            corpus = _topic_corpus(root, plan, request, job["run_id"], result)
            corpora[topic_id] = corpus
        topic_entries.append({
            "topic_id": topic_id,
            "run_id": job["run_id"],
            "status": "failed" if error else (
                "completed" if result and result.get("manifest_ok") else "partial"
            ),
            "target_n": request["target_n"],
            "request_ref": f"requests/{topic_id}.json",
            "pdf_dir": f"topics/{topic_id}/pdf",
            "manifest_ref": f"topics/{topic_id}/MANIFEST.md",
            "retrieved_corpus_ref": (
                f"topics/{topic_id}/retrieved_corpus.json" if result is not None else None
            ),
            "counts": {
                "downloaded": len((result or {}).get("downloaded", [])),
                "stubs": len((result or {}).get("stubs", [])),
                "rejected": len((result or {}).get("rejected", [])),
                "openalex_pool": int((result or {}).get("openalex_total", 0)),
                "deduped_pool": int((result or {}).get("total_found", 0)),
                "open_access_pool": int((result or {}).get("oa_count", 0)),
            },
            "error": error,
        })

    works = _apply_cross_topic_dedup(corpora)
    for topic_id, corpus in corpora.items():
        validation = contracts.validate(corpus, SCOUT_CORPUS_CONTRACT)
        if not validation["ok"]:
            raise ValueError("invalid deduplicated Scout corpus: " + "; ".join(validation["errors"]))
        _write_json(root / "topics" / topic_id / "retrieved_corpus.json", corpus)

    completed = sum(item["status"] == "completed" for item in topic_entries)
    failed = sum(item["status"] == "failed" for item in topic_entries)
    status = "completed" if completed == len(topic_entries) else (
        "failed" if failed == len(topic_entries) else "partial"
    )
    index = {
        "schema_version": SCOUT_INDEX_CONTRACT,
        "artifact_version": "1.0.0",
        "task_id": plan["task_id"],
        "status": status,
        "execution_profile": EXECUTION_PROFILE,
        "total_target": total,
        "allocated_target": sum(item["target_n"] for item in topic_entries),
        "plan_ref": "plan.json",
        "topics": topic_entries,
        "deduplicated_works": works,
        "summary": {
            "topic_count": len(topic_entries),
            "completed_topic_count": completed,
            "failed_topic_count": failed,
            "downloaded_pdf_count": sum(item["counts"]["downloaded"] for item in topic_entries),
            "unique_work_count": len(works),
        },
    }
    validation = contracts.validate(index, SCOUT_INDEX_CONTRACT)
    if not validation["ok"]:
        raise ValueError("invalid Scout run index: " + "; ".join(validation["errors"]))
    _write_json(root / "index.json", index)
    return {"run_directory": str(root.resolve()), "index": index}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parallel persistent A01 -> Scout fan-out")
    parser.add_argument("research_plan", help="Path or artifact:// ref to research_plan@1")
    parser.add_argument("--workspace", default="", help="Exact Scout workspace override")
    parser.add_argument("--total-target", type=int, default=None)
    parser.add_argument("--max-workers", type=int, default=None)
    args = parser.parse_args(argv)
    result = run_scout_fanout(
        args.research_plan,
        workspace=args.workspace or None,
        total_target=args.total_target,
        max_workers=args.max_workers,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["index"]["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
