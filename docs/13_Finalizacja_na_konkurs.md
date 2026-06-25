# 13. Finalizacja na konkurs — ostateczne spięcia cross-graph

Lista końcowych zadań spinających całość (do zrobienia dziś wieczorem). Tylko cross-graph i
integracja — G03 sam w sobie jest domknięty (wejście → agentowy graf → `solution_blueprint@1` →
markdown + inline; testy zielone).

## Zadania

### 1. Oficjalna ścieżka candidate przez `orchestrate-workflow`
- **Gdzie:** `skills/orchestrate-workflow/SKILL.md` (+ adaptery), strona G02.
- **Co:** krok 2 ma dawać `solution_input_candidate@1` (oficjalny), a krok 3 przekazywać do G03
  `research_bundle_kind: "solution_input_candidate"`. Dziś workflow jest w wersji legacy
  (`user_approved_research_bundle@1`).
- **Zależność:** g02 musi w tym łańcuchu realnie emitować `solution_input_candidate@1`.
- **Bramki w tej ścieżce:** intake (g01) + solution (g03); g02 scout bez Human Research Gate.

### 2. Realny `lecture_baseline@1` z G01 (zamiast mocka)
- **Gdzie:** styk G01 → G03.
- **Co:** przechwycić `lecture_baseline_ref` z realnego przebiegu G01 (węzeł
  `g01-a04-lecture-baseline`, `finalize_op: intake_lecture_baseline_finalize`) i podać do G03 zamiast
  `mocks/g03/solution_request.candidate.json`.
- **Kontrakt bez zmian** — `lecture_baseline@1` już ustabilizowany.

## Operacyjne (na koniec)
- Build/install pluginu (lub MCP z source) do live testu ścieżki agentowej z modelem.
- Commit całości (robione ręcznie).
