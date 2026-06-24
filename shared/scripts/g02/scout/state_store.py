from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .app_config import APP_STATE_DIR

# Wzorowane na llmwiki_pdf/state_store.py (KnownFilesStore), ale schemat jest
# właściwy dla Scouta: cache metadanych artykułów + werdyktów LLM per DOI +
# rejestr przebiegów. Cel zgodny z koncepcją §7: odporność na limity zapytań
# i zasada "nie płać dwa razy za to samo DOI".


class ScoutStore:
    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir.resolve()
        state_dir = self.workspace_dir / APP_STATE_DIR
        db = state_dir / "radar_cache.sqlite"
        if not db.exists() and (state_dir / "scout_cache.sqlite").exists():
            db = state_dir / "scout_cache.sqlite"
        self.db_path = db

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS papers (
                doi TEXT PRIMARY KEY,
                title TEXT,
                year INTEGER,
                authors TEXT,
                oa_status TEXT,
                source TEXT,
                clean_title TEXT,
                json_openalex TEXT,
                first_seen TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS verdicts (
                doi TEXT NOT NULL,
                tier TEXT NOT NULL,
                relevant INTEGER,
                model TEXT,
                framework TEXT,
                method TEXT,
                gap TEXT,
                rationale TEXT,
                ts TEXT NOT NULL,
                PRIMARY KEY (doi, tier)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                query TEXT,
                hypothesis TEXT,
                n_target INTEGER,
                tier TEXT,
                ts TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS downloads (
                doi TEXT PRIMARY KEY,
                clean_title TEXT,
                path TEXT,
                ts TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_stats (
                source_id TEXT PRIMARY KEY,
                h_index INTEGER,
                mean2yr REAL,
                ts TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS translations (
                src TEXT NOT NULL,
                lang TEXT NOT NULL,
                query TEXT NOT NULL,
                ts TEXT NOT NULL,
                PRIMARY KEY (src, lang)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS query_forms (
                name TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                ts TEXT NOT NULL
            )
            """
        )
        # — Radar 2.0: szkielet bazy kandydatów + proweniencja first-class (spec §6.3, §11.2).
        # Addytywne (CREATE TABLE IF NOT EXISTS) — istniejące dane (papers/verdicts/runs/...)
        # nietknięte. NIE wpięte jeszcze w logikę wyszukiwania (to Etap 1) — tu sam schemat.
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidate (
                candidate_id           TEXT PRIMARY KEY,
                openalex_id            TEXT,
                doi                    TEXT,
                s2_id                  TEXT,
                arxiv_id               TEXT,
                title                  TEXT,
                title_norm             TEXT,
                year                   INTEGER,
                venue                  TEXT,
                work_type              TEXT,
                abstract               TEXT,
                oa_status              TEXT,
                oa_url                 TEXT,
                citations_count        INTEGER,
                state                  TEXT,
                role                   TEXT,
                tier                   TEXT,
                metadata_quality_score REAL,
                version_preprint_url   TEXT,
                version_published_doi  TEXT,
                cluster_of             TEXT,
                created_at             TEXT,
                updated_at             TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_candidate_doi ON candidate(doi);
            CREATE INDEX IF NOT EXISTS idx_candidate_state ON candidate(state);

            CREATE TABLE IF NOT EXISTS query (
                query_id   TEXT PRIMARY KEY,
                run_id     TEXT,
                string     TEXT NOT NULL,
                source     TEXT,
                profile    TEXT,
                provenance TEXT,
                ts         TEXT
            );

            CREATE TABLE IF NOT EXISTS hit (
                hit_id       TEXT PRIMARY KEY,
                query_id     TEXT,
                source       TEXT,
                candidate_id TEXT,
                raw_position INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_hit_candidate ON hit(candidate_id);
            CREATE INDEX IF NOT EXISTS idx_hit_query ON hit(query_id);

            CREATE TABLE IF NOT EXISTS verdict (
                verdict_id   TEXT PRIMARY KEY,
                candidate_id TEXT,
                tier         TEXT,
                role         TEXT,
                reason       TEXT,
                user         TEXT,
                ts           TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_verdict_candidate ON verdict(candidate_id);

            CREATE TABLE IF NOT EXISTS pdf (
                candidate_id      TEXT PRIMARY KEY,
                source_pdf_sha256 TEXT,
                path              TEXT,
                provider          TEXT,
                version           TEXT,
                license           TEXT,
                retrieved_at      TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_pdf_sha ON pdf(source_pdf_sha256);
            """
        )
        # Migracja idempotentna: dolacz kolumny wzbogaconego schematu metadanych
        # do istniejacych baz (literature-harvester). ALTER TABLE ADD COLUMN jest
        # bezpieczny przy ponownym uruchomieniu - dodajemy tylko brakujace.
        existing = {row[1] for row in connection.execute("PRAGMA table_info(papers)").fetchall()}
        for col in ("license", "version", "venue", "landing_page_url", "jel_codes", "publication_type"):
            if col not in existing:
                connection.execute(f"ALTER TABLE papers ADD COLUMN {col} TEXT")
        if "retracted" not in existing:
            connection.execute("ALTER TABLE papers ADD COLUMN retracted INTEGER")
        # Migracja runs: migawka formularza i wyniku (Historia: kryteria, ranking, pliki).
        existing_runs = {row[1] for row in connection.execute("PRAGMA table_info(runs)").fetchall()}
        for col in ("form", "result"):
            if col not in existing_runs:
                connection.execute(f"ALTER TABLE runs ADD COLUMN {col} TEXT")
        connection.commit()
        return connection

    # — Artykuły ————————————————————————————————————————————————
    def register_paper(self, paper: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            existing = conn.execute("SELECT first_seen FROM papers WHERE doi = ?", (paper.get("doi"),)).fetchone()
            first_seen = str(existing["first_seen"]) if existing else now
            conn.execute(
                """
                INSERT OR REPLACE INTO papers
                    (doi, title, year, authors, oa_status, source, clean_title, json_openalex,
                     license, version, venue, landing_page_url, jel_codes, publication_type, retracted, first_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    paper.get("doi"),
                    paper.get("title"),
                    paper.get("year"),
                    paper.get("authors"),
                    paper.get("oa_status"),
                    paper.get("source"),
                    paper.get("clean_title"),
                    paper.get("json_openalex"),
                    paper.get("license"),
                    paper.get("version"),
                    paper.get("venue"),
                    paper.get("landing_page_url"),
                    paper.get("jel_codes"),
                    paper.get("publication_type"),
                    paper.get("retracted"),
                    first_seen,
                ),
            )
            conn.commit()

    # — Radar 2.0: baza kandydatów + proweniencja (Etap 1, część addytywna) ————
    # Warstwa zapisu dla schematu z Etapu 0 (candidate/query/hit/verdict). NIE wpięta
    # jeszcze w live-search — to data-access do wykorzystania w Etapie 1 (planer/triage).
    _CANDIDATE_COLS = (
        "openalex_id", "doi", "s2_id", "arxiv_id", "title", "title_norm", "year",
        "venue", "work_type", "abstract", "oa_status", "oa_url", "citations_count",
        "state", "role", "tier", "metadata_quality_score", "version_preprint_url",
        "version_published_doi", "cluster_of",
    )

    def upsert_candidate(self, candidate_id: str, **fields: Any) -> None:
        """MERGE: nadpisuje tylko przekazane pola, resztę zachowuje (discovery -> enrich)."""
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM candidate WHERE candidate_id = ?", (candidate_id,)).fetchone()
            current = dict(row) if row else {}
            merged = {c: fields.get(c, current.get(c)) for c in self._CANDIDATE_COLS}
            created = current.get("created_at") or now
            cols = ["candidate_id", *self._CANDIDATE_COLS, "created_at", "updated_at"]
            values = [candidate_id, *[merged[c] for c in self._CANDIDATE_COLS], created, now]
            conn.execute(
                f"INSERT OR REPLACE INTO candidate ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                values,
            )
            conn.commit()

    def set_candidate_state(self, candidate_id: str, state: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            conn.execute(
                "UPDATE candidate SET state = ?, updated_at = ? WHERE candidate_id = ?",
                (state, now, candidate_id),
            )
            conn.commit()

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM candidate WHERE candidate_id = ?", (candidate_id,)).fetchone()
        return dict(row) if row else None

    def list_candidates(self, state: str | None = None) -> list[dict[str, Any]]:
        with closing(self.connect()) as conn:
            if state is None:
                rows = conn.execute("SELECT * FROM candidate ORDER BY updated_at DESC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM candidate WHERE state = ? ORDER BY updated_at DESC", (state,)
                ).fetchall()
        return [dict(r) for r in rows]

    def record_query(self, query_id: str, *, run_id: str | None = None, string: str = "",
                     source: str | None = None, profile: str | None = None,
                     provenance: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO query (query_id, run_id, string, source, profile, provenance, ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (query_id, run_id, string, source, profile, provenance, now),
            )
            conn.commit()

    def record_hit(self, hit_id: str, *, query_id: str | None = None, source: str | None = None,
                   candidate_id: str | None = None, raw_position: int | None = None) -> None:
        with closing(self.connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO hit (hit_id, query_id, source, candidate_id, raw_position)"
                " VALUES (?, ?, ?, ?, ?)",
                (hit_id, query_id, source, candidate_id, raw_position),
            )
            conn.commit()

    def record_candidate_verdict(self, verdict_id: str, *, candidate_id: str | None = None,
                                 tier: str | None = None, role: str | None = None,
                                 reason: str | None = None, user: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO verdict (verdict_id, candidate_id, tier, role, reason, user, ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (verdict_id, candidate_id, tier, role, reason, user, now),
            )
            conn.commit()

    # — Werdykty LLM (cache per DOI+tier) ————————————————————————
    def get_verdict(self, doi: str, tier: str) -> dict[str, Any] | None:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM verdicts WHERE doi = ? AND tier = ?", (doi, tier)).fetchone()
        return dict(row) if row else None

    def put_verdict(self, doi: str, tier: str, **fields: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO verdicts
                    (doi, tier, relevant, model, framework, method, gap, rationale, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doi,
                    tier,
                    fields.get("relevant"),
                    fields.get("model"),
                    fields.get("framework"),
                    fields.get("method"),
                    fields.get("gap"),
                    fields.get("rationale"),
                    now,
                ),
            )
            conn.commit()

    # — Pobrane PDF (dedup cross-RUN: "nie pobieraj dwa razy tej samej pracy") —
    def mark_downloaded(self, doi: str, clean_title: str, path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO downloads (doi, clean_title, path, ts) VALUES (?, ?, ?, ?)",
                (doi, clean_title, path, now),
            )
            conn.commit()

    def downloaded_clean_titles(self) -> set[str]:
        """Zbior clean_title prac pobranych w poprzednich przebiegach, KTORYCH
        plik nadal istnieje na dysku (skasowany/przeniesiony plik nie blokuje
        ponownego pobrania). Sluzy do dedup cross-RUN w `run_student`."""
        out: set[str] = set()
        with closing(self.connect()) as conn:
            rows = conn.execute("SELECT clean_title, path FROM downloads").fetchall()
        for row in rows:
            ct = (row["clean_title"] or "").strip()
            path = row["path"] or ""
            if ct and path and Path(path).is_file():
                out.add(ct)
        return out

    # — Prestiz venue: cache summary_stats zrodla OpenAlex (jeden call per zrodlo) —
    def get_source_stats(self, source_id: str) -> dict[str, Any] | None:
        with closing(self.connect()) as conn:
            row = conn.execute(
                "SELECT h_index, mean2yr FROM source_stats WHERE source_id = ?", (source_id,)
            ).fetchone()
        return {"h_index": row["h_index"], "mean2yr": row["mean2yr"]} if row else None

    def put_source_stats(self, source_id: str, stats: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO source_stats (source_id, h_index, mean2yr, ts) VALUES (?, ?, ?, ?)",
                (source_id, stats.get("h_index"), stats.get("mean2yr"), now),
            )
            conn.commit()

    # — Cache tlumaczen zapytan (P1: jezyk wyszukiwania) ————————————————
    def get_translation(self, src: str, lang: str) -> str | None:
        """Zwroc zapisane tlumaczenie zapytania `src` na `lang` (albo None)."""
        with closing(self.connect()) as conn:
            row = conn.execute(
                "SELECT query FROM translations WHERE src = ? AND lang = ?", (src, lang)
            ).fetchone()
        return str(row["query"]) if row else None

    def put_translation(self, src: str, lang: str, query: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO translations (src, lang, query, ts) VALUES (?, ?, ?, ?)",
                (src, lang, query, now),
            )
            conn.commit()

    # — Zapisane formularze zapytan (presety do reedycji i ponownego uruchomienia) —
    def save_query_form(self, name: str, payload: dict[str, Any]) -> None:
        """Zapisz (lub nadpisz po nazwie) cały formularz Zwiadu jako preset."""
        import json
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO query_forms (name, payload, ts) VALUES (?, ?, ?)",
                (name, json.dumps(payload, ensure_ascii=False), now),
            )
            conn.commit()

    def list_query_forms(self, limit: int = 100) -> list[dict[str, Any]]:
        """Zapisane formularze (najnowsze pierwsze): {name, payload(dict), ts}."""
        import json
        with closing(self.connect()) as conn:
            rows = conn.execute(
                "SELECT name, payload, ts FROM query_forms ORDER BY ts DESC LIMIT ?", (int(limit),)
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (ValueError, TypeError):
                payload = {}
            out.append({"name": row["name"], "payload": payload, "ts": row["ts"]})
        return out

    def delete_query_form(self, name: str) -> None:
        with closing(self.connect()) as conn:
            conn.execute("DELETE FROM query_forms WHERE name = ?", (name,))
            conn.commit()

    # — Audyt werdyktow LLM (D2: werdykt to pomiar, nie prawda) ——————————
    def sample_verdicts(self, limit: int = 20, tier: str | None = None) -> list[dict[str, Any]]:
        """Losowa probka zapisanych werdyktow LLM do recznej oceny zgodnosci
        (koncepcja §9 D2). Read-only — nie zmienia stanu."""
        with closing(self.connect()) as conn:
            if tier:
                rows = conn.execute(
                    "SELECT * FROM verdicts WHERE tier = ? ORDER BY RANDOM() LIMIT ?",
                    (tier, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM verdicts ORDER BY RANDOM() LIMIT ?", (int(limit),)
                ).fetchall()
        return [dict(row) for row in rows]

    # — Przebiegi (reprodukowalność) ——————————————————————————————
    def record_run(self, run_id: str, *, query: str, hypothesis: str, n_target: int, tier: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs (run_id, query, hypothesis, n_target, tier, ts) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, query, hypothesis, int(n_target or 0), tier, now),
            )
            conn.commit()

    def save_run_snapshot(self, run_id: str, form: dict[str, Any] | None, result: dict[str, Any] | None) -> None:
        """Dopisz do przebiegu migawkę: formularz (do „Powtórz") i kompaktowy wynik
        (ranking + pobrane pliki) — do bogatej Historii."""
        import json
        with closing(self.connect()) as conn:
            conn.execute(
                "UPDATE runs SET form = ?, result = ? WHERE run_id = ?",
                (json.dumps(form or {}, ensure_ascii=False), json.dumps(result or {}, ensure_ascii=False), run_id),
            )
            conn.commit()

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """Ostatnie przebiegi (Historia): run_id, zapytanie, hipoteza, N, tier, czas
        oraz migawka formularza (`form`) i wyniku (`result`) — parsowane z JSON."""
        import json
        with closing(self.connect()) as conn:
            rows = conn.execute(
                "SELECT run_id, query, hypothesis, n_target, tier, ts, form, result FROM runs ORDER BY ts DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            for key in ("form", "result"):
                try:
                    d[key] = json.loads(d[key]) if d.get(key) else None
                except (ValueError, TypeError):
                    d[key] = None
            out.append(d)
        return out

    def delete_runs(self, run_ids: list[str]) -> int:
        """Skasuj wskazane przebiegi z Historii (po run_id). Zwraca liczbę usuniętych.
        Bezpieczne: puste/niepoprawne id → 0; nie rusza papers/downloads/cache."""
        ids = [str(r).strip() for r in (run_ids or []) if str(r).strip()]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with closing(self.connect()) as conn:
            cur = conn.execute(f"DELETE FROM runs WHERE run_id IN ({placeholders})", ids)
            conn.commit()
            return int(cur.rowcount or 0)

    def stats(self) -> dict[str, int]:
        """Liczność tabel — używane przez `doctor` do raportu stanu cache."""
        with closing(self.connect()) as conn:
            return {
                "papers": conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
                "verdicts": conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0],
                "runs": conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
                "downloads": conn.execute("SELECT COUNT(*) FROM downloads").fetchone()[0],
                "source_stats": conn.execute("SELECT COUNT(*) FROM source_stats").fetchone()[0],
            }
