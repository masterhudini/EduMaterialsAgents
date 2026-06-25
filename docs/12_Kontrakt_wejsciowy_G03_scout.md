# 12. Kontrakt wejściowy G03 (tryb scout) — przewodnik dla deva

Co dostaje Graph03 na wejściu i jak to czytać. Źródłem prawdy o kształcie są schematy JSON w
`shared/contracts/`; ten dokument tłumaczy semantykę i granice.

## 0. Skrót

- G03 jest pierwszym miejscem, gdzie spotykają się **dwie strony**: szkielet wykładu z G01
  (`lecture_baseline@1`) i hand-off badawczy z G02.
- Granica wejściowa to cienka para refów: `solution_graph_input@1`.
- Strona badawcza ma **dwa warianty** wskazywane przez `research_bundle_kind`:
  - `user_approved_research_bundle` → legacy, ścieżka z Human Research Gate (`user_approved_research_bundle@1`);
  - `solution_input_candidate` → **tryb scout_fast** (deterministyczny, bez bramki ludzkiej) →
    `solution_input_candidate@1`.
- W trybie scout finalnym kontraktem G02 jest **`solution_input_candidate@1`** i to on jest
  samowystarczalnym kontekstem badawczym dla G03.

## 1. Granica wejściowa: `solution_graph_input@1`

```jsonc
{
  "schema_version": "solution_graph_input@1",
  "task_id": "awif_2025_wyk_09_fra",
  "output_language": "Polish",
  "lecture_baseline_ref": "artifact://g01/.../lecture_baseline.json",   // szkielet slajdów (G01)
  "research_bundle_ref":  "artifact://g02/.../solution_input_candidate.json",
  "research_bundle_kind": "solution_input_candidate"                    // scout_fast
}
```

`research_bundle_kind` rozstrzyga, jaki kontrakt hydratujesz spod `research_bundle_ref`. Brak pola =
domyślnie legacy (`user_approved_research_bundle`). Front-door G03 (`shared/scripts/g03/solution.py`)
przyjmuje oba warianty — jako ref albo inline — i sam ustala `research_bundle_kind` (jawnie albo z
`schema_version` inline'u).

## 2. Granica odpowiedzialności: G02 nie ma slajdów

G02 **nigdy nie widzi slajdów**. Slajdy są w `lecture_baseline@1` (z G01). Dlatego finalne mapowanie
„które ustalenie → który slajd" robi **G03**, łącząc:

- klucze złączenia z każdego update'u: `linked_intake_ids` (claim/concept/flow-issue/update-need)
  oraz `target.slide_ids` / `target.section_hint` (podpowiedzi, nie autorytet),
- z `lecture_baseline@1` (slajdy + ich `claim_ids`/`concept_ids`, `locked`).

`solution_input_candidate@1` jest „self-contained" dla **kontekstu badawczego** (findings, dowody,
opinie, powiązania z intake) — nie dla slajdów. Nie oczekuj w nim szkieletu prezentacji.

## 3. `solution_input_candidate@1` — pola

Pełny schemat: `shared/contracts/solution_input_candidate.schema.json` (x-version 1.4).
Przykład realny: `mocks/g02/EXAMPLE g02-a09-solution_input_candidate.artifact.json`.

### 3.1 Nagłówek i audyt

| Pole | Znaczenie |
|---|---|
| `schema_version` | `"solution_input_candidate@1"` |
| `task_id` | zgodny z intake/G01 |
| `synthesis_mode` | `"scout_fast"` |
| `source_pipeline` | `"intake -> a01 -> scout -> a07 -> a09"` |
| `intake_ref`, `plan_ref` | refy do `research_graph_input@1` i `research_plan@1` (mogą być null poza realnym łańcuchem) |
| `claim_assessment_performed` | `false` — **A08 jest w trybie scout pominięte** |
| `a08_status` | `"skipped_scout_fast"` |
| `a09_model_pass` | `true` jeśli realny A09 (opus/medium) zweryfikował baseline; `false` przy fallbacku |
| `synthesis_engine` | `"a09_opus_medium"` albo `"deterministic_fallback"` |
| `confidence` | `low` / `medium` / `high` |
| `generated_at` | znacznik czasu |

> Opinie pochodzą z **A07** (recenzja dowodów per artykuł) zweryfikowanej przez **A09**. A08
> (claim assessment) w trybie scout nie biegnie — `confidence` opisuje siłę dowodu z recenzji A07,
> nie formalną weryfikację twierdzeń.

### 3.2 Opinia per artykuł — `suggested_updates[]` i `optional_improvements[]`

To jest serce kontraktu: rekomendacje zmian wyprowadzone z przeczytanych artykułów. `suggested_updates`
to propozycje gotowe do zastosowania; `optional_improvements` to słabsze/uzupełniające (niższy priorytet
albo brak twardego dowodu). Oba mają tę samą strukturę:

```jsonc
{
  "update_id": "UPD_FRA_PRICING",
  "finding": "Post-crisis FRA pricing uses multi-curve (OIS) discounting...",   // co mówi źródło
  "rationale": "Obecny wykład zakłada single-curve; to dezaktualizuje slajd.",   // opinia: czemu zmienić
  "extension_relation": "updates_outdated",   // werdykt: confirms|updates_outdated|adds_new_angle|contradicts|qualifies|didactic_example
  "confidence": "supported_by_reviewed_source",
  "linked_intake_ids": { "claim_ids": ["CL01"], "concept_ids": ["C01"], "flow_issue_ids": [], "update_need_ids": [] },
  "target": { "slide_ids": ["12"], "section_hint": "...", "placement": "best_fit_by_graph03" },  // podpowiedź dla G03
  "ready_to_apply_text": { "slide_bullet": "...", "speaker_note": "...", "optional_detail": "..." },
  "evidence_refs": [ { "source_id": "...", "location": "p. 5, sec. 3", "quote": "After 2008..." } ],  // konkretny cytat
  "source_refs":   [ { "source_id": "...", "doi": "10...", "title": "...", "year": 2014, "venue": "..." } ]
}
```

Jak czytać:
- `extension_relation` = werdykt opinii. `contradicts`/`updates_outdated` to sygnał, że obecny slajd
  jest sprzeczny/nieaktualny; `confirms` wzmacnia; `adds_new_angle`/`qualifies` rozszerzają;
  `didactic_example` to materiał ilustracyjny.
- `evidence_refs[].quote` + `location` pozwalają zacytować źródło **bez** czytania PDF-a.
- `ready_to_apply_text` to gotowy draft (bullet + notatka prelegenta) — G03 może go użyć wprost lub
  doszlifować, ale nie musi wymyślać treści od zera.
- `target` jest **podpowiedzią**; autorytatywne `slide_id` ustala G03 przez join (sekcja 2).

### 3.3 Pokrycie i to, co otwarte

| Pole | Znaczenie |
|---|---|
| `coverage_summary[]` | per claim/driver: `{element_type, element_id, status: covered\|partial\|uncovered, source_count}` |
| `topics_covered[]` | per topic: powiązane claim/concept/flow/update-need, liczba źródeł, nota pokrycia |
| `coverage_gaps[]` | jawne luki dowodowe (z A07) |
| `unresolved_items[]` | pytania/wątki bez rozstrzygnięcia: `{question, linked_intake_ids, why_unresolved, what_would_resolve}` — w tym nieskonsumowane `lookup_pointers` |
| `limitations[]` | ograniczenia (m.in. „A08 skipped", „A09 nie czytał pełnych PDF-ów") |
| `source_refs[]` | globalna lista wszystkich recenzowanych źródeł |
| `slide_revision_priorities[]` | kolejność rewizji wg siły dowodu + typu relacji (z uzasadnieniem) |
| `do_not_change[]` | (opcjonalnie z A09) czego świadomie nie ruszać |
| `deep_dive_used[]` | audyt bounded deep-dive (≤5 źródeł) |

`coverage_summary` daje szybką odpowiedź „co badanie rozstrzygnęło, a co zostało otwarte" bez
sięgania po A07.

### 3.4 Ograniczenia hand-offu — `graph03_handoff_constraints`

```jsonc
{
  "compact": true,
  "no_full_text": true,
  "no_full_pdfs": true,
  "no_full_extracted_text": true,
  "no_verbose_paper_reviews": true,
  "ready_to_apply_updates_required": true,
  "graph03_must_not_call_g02": true,
  "output_language": "Polish",
  "locked_sections": ["..."]
}
```

`graph03_must_not_call_g02: true` — G03 **nie** wywołuje z powrotem G02 ani nie dociąga PDF-ów; cały
potrzebny kontekst badawczy jest w tym artefakcie. `locked_sections` / per-slide `locked` (z
`lecture_baseline`) — nie planuj zmian na zablokowanych slajdach.

## 4. Checklist konsumenta G03 (scout)

1. Z `solution_graph_input@1` weź `research_bundle_kind`; jeśli `solution_input_candidate` →
   hydratuj `research_bundle_ref` jako `solution_input_candidate@1`.
2. Zhydratuj `lecture_baseline_ref` (slajdy + `claim_ids`/`concept_ids` + `locked`).
3. Dla każdego `suggested_updates[]`: zrób join `linked_intake_ids` → slajd(y) (fallback: `target`).
   Brak dopasowania = `needs_input`/`deferred_items`, nie zgadywanie.
4. Użyj `ready_to_apply_text` + `evidence_refs` jako treści i atrybucji; respektuj `locked_sections`.
5. `optional_improvements` traktuj jako niższy priorytet; `unresolved_items`/`coverage_gaps` →
   `deferred_items` z powodem.
6. Nigdy nie wołaj G02 i nie czytaj PDF-ów (`graph03_must_not_call_g02`).
