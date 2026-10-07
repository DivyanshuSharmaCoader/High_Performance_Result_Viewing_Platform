# 13 · Result Ingestion — Excel/CSV Import Pipeline

> Covers §8 (result import as a major feature). This is ScoreCode's most important admin-facing feature commercially: it's where "easier than doing it manually" is won or lost.
> Diagrams: [import activity diagram](diagrams/activity-diagrams.md#2-marks-import-pipeline) · [import sequence](diagrams/sequence-diagrams.md#3-marks-import-upload-validate-commit) · [import job state machine](diagrams/state-diagrams.md#4-import-job)

---

## 1. Design principles
1. **Never touch live data until the human confirms.** Everything lands in staging (`import_rows`) first.
2. **Accept the institution's spreadsheet, don't force ours.** Provide a template, but support column mapping for arbitrary layouts (wide or long format).
3. **Every problem is reported at row + column level, in plain language, downloadable as an annotated spreadsheet.**
4. **Re-uploading a fixed file is the normal path, not an error path.**
5. **Imports are deterministic and idempotent** — the same file with the same mapping produces the same result; duplicate uploads are detected by hash.
6. Same framework for **students, courses, staff and marks** (`ImportProfile` per kind) — build once, reuse.

---

## 2. Supported file shapes

**Long format** (one row per student × paper):
```
Enrollment No | Course Code | Internal | External | Attendance
102303001     | UCS301      | 35       | 48       |
102303002     | UCS301      | AB       |          | absent
```
**Wide format** (one row per student, column groups per paper — common in schools):
```
Roll No | Name        | Maths_Int | Maths_Ext | Science_Int | Science_Ext
8A01    | Aarav Gupta | 18        | 62        | 19          | 58
```
The mapping step lets the admin map columns → `{student identifier, course, component}` or declare the wide pattern (`<course>_<component>`). Mappings can be **saved as a named preset** per tenant and auto-suggested next time (by header similarity).

Template download (`GET /exams/{id}/papers/{pid}/marks-template.xlsx` or per exam) is **pre-filled** with enrollment numbers and names for the cohort and has data-validation dropdowns/ranges in Excel — the best way to prevent errors is to give a file that can't easily be wrong.

---

## 3. Pipeline stages

```
 ① Upload ─► ② Store & fingerprint ─► ③ Parse ─► ④ Map ─► ⑤ Validate ─► ⑥ Review/Fix ─► ⑦ Commit ─► ⑧ Post-commit
     API          object store + sha256   worker     UI/auto    worker        UI            worker (1 tx)    stale results
```

| # | Stage | Detail |
|---|---|---|
| ① | Upload | Multipart to API; size/type checks; `import_jobs` row `uploaded`; returns 202 + job id. Faculty uploads are restricted to assigned papers. |
| ② | Store | Raw bytes to `tenants/{tid}/imports/{uuid}` (private), SHA-256 recorded; warn if the same hash was already committed for this exam ("This file was already imported on 3 Oct by Mrs. Kaur"). |
| ③ | Parse (worker) | CSV: detect encoding (UTF-8/UTF-8-BOM/Windows-1252), delimiter; XLSX: `openpyxl` read-only, values only, first sheet or chosen sheet; trim whitespace, normalise Unicode (NFC), detect header row. Limits: rows, columns, cell length, uncompressed size, time budget. |
| ④ | Map | Auto-map by header names/presets; admin confirms. Mapping stored on the job (`mapping jsonb`). Changing mapping re-runs ⑤ only. |
| ⑤ | Validate (worker) | Row-level and file-level rules (below) → `import_rows` with `normalized`, `issues`, `status` + job counters. Batch inserts (COPY). |
| ⑥ | Review & fix | UI shows summary + filterable issue table; **download annotated XLSX** (original columns + `Errors` column, red cells); options: fix & re-upload (new job linked as `supersedes`), edit individual cells in staging (small fixes), or exclude rows. |
| ⑦ | Commit | Allowed when `rows_error = 0`, or admin explicitly chooses "commit valid rows only" (excluded rows listed in audit). Single DB transaction: upsert `mark_entries` (`ON CONFLICT (tenant_id, exam_paper_id, student_id) DO UPDATE` **only if values changed**, with version bump), audit event with counts + reference to job, job → `committed`. Idempotency key = job id. |
| ⑧ | Post-commit | Paper submissions for affected papers marked (if import done by faculty → may auto-submit by choice); existing result runs for the exam marked `stale`. |

---

## 4. Validation rules

| Code | Severity | Rule | Example message |
|---|---|---|---|
| `MISSING_COLUMN` | file error | Required mapped column absent | "Column for 'External' marks not found. Map it or add a column." |
| `UNKNOWN_STUDENT` | error | Identifier not found in tenant | "Row 14: enrollment no. 1023O3001 not found (did you mean 102303001?)" — fuzzy suggestion for O/0, I/1 swaps |
| `STUDENT_NOT_IN_EXAM` | error | Student exists but not in a cohort sitting this exam | |
| `DUPLICATE_IN_FILE` | error | Same student × paper appears twice | "Rows 14 and 87 both contain 102303001 / UCS301" |
| `UNKNOWN_COURSE` / `PAPER_NOT_IN_EXAM` | error | Course code unknown or not part of exam | |
| `UNKNOWN_EXAM` | file error | Exam column (if present) doesn't match target exam | |
| `NOT_A_NUMBER` | error | Non-numeric, non-code value | "Row 9, 'Internal': 'thirty' is not a number" |
| `OUT_OF_RANGE` | error | `< 0` or `> component max` | "Row 9, 'External': 65 exceeds maximum 60" |
| `INVALID_PRECISION` | error | More decimals than allowed (e.g. 0.5 steps only) | |
| `MISSING_MARK` | warning (configurable to error) | Blank component for present student | |
| `ABSENT_WITH_MARKS` | error | Attendance = absent but marks given | |
| `TOTAL_MISMATCH` | warning | File's own "Total" ≠ computed sum | "Row 22: file total 83 ≠ 35 + 50 = 85" — catches the spreadsheet's formula errors |
| `NAME_MISMATCH` | warning | Name in file differs from roster (fuzzy) | Catches shifted rows — a very common Excel error |
| `NOT_ASSIGNED` | error | Faculty uploading for a paper/cohort not assigned | |
| `PAPER_LOCKED` | error | Paper submitted/locked or exam approved | |
| `OVERWRITES_EXISTING` | info | Row changes an existing mark | Shown as diff "45 → 48" |
| `MISSING_STUDENTS` | file warning | Students in cohort with no row | "12 students in CSE-G3 have no marks for UCS301" |

Special values are tenant-configurable codes (`AB` absent, `EX` exempt, `MP` malpractice, `WH` withheld).

---

## 5. UX outline

```
┌ Import marks — End Semester Dec 2025 ───────────────────────────────────────────┐
│ ① Upload  ─ ② Map columns ─ ③ Review ─ ④ Confirm                                 │
│                                                                                  │
│  File: cse_ucs301_marks.xlsx · 1,204 rows                                        │
│  ✓ 1,180 ready   ⚠ 16 warnings   ✗ 8 errors                                     │
│                                                                                  │
│  [Errors ▾] [Warnings] [Changes vs existing] [All]          ⬇ Download annotated │
│  Row  Enrollment   Course  Column    Problem                                     │
│  14   1023O3001    UCS301  —         Student not found. Did you mean 102303001?  │
│  87   102303001    UCS301  —         Duplicate of row 14                         │
│  ...                                                                             │
│  [Re-upload fixed file]  [Commit 1,196 valid rows, skip 8]  [Fix all first ✓]    │
└──────────────────────────────────────────────────────────────────────────────────┘
```
- Progress via polling (`GET /imports/{id}`), counts update live.
- Confirm dialog states exactly what will happen: *"1,196 marks will be saved (312 new, 884 updated). Results for this exam will need re-processing."*

---

## 6. Performance & limits (targets to measure — PT-5)
- Validation is set-based: load all tenant students/cohort memberships/papers for the exam into memory **once** (dictionary lookups), not one query per row.
- 10,000 rows target < 60 s end-to-end validation; commit via batched upserts.
- Max rows per import (e.g. 50,000) and per-tenant concurrency (e.g. 2 imports at a time).

## 7. Testing
- Golden-file tests: a corpus of messy real-world spreadsheets (merged cells, BOMs, trailing spaces, numbers stored as text, `1.0E+11` enrollment numbers mangled by Excel, hidden rows, multiple sheets) with expected issue lists.
- Property tests: valid generated files always import with zero errors; random corruption always produces at least one issue and never a commit.
- Security tests: zip bomb XLSX, huge cell, formula cells, CSV injection in error report, wrong-tenant identifiers.

## 8. Implementation status (kept in sync with the code)
Built in Phase 6 (`backend/app/modules/ingestion/`), shared by every import kind:
- **Pipeline**: upload (`POST /api/v1/admin/imports`, multipart) → `imports.analyse` job (parse, header detection, auto-mapping, validation, staging) → review (`GET …/{id}`, `GET …/{id}/rows?status=problems`, `GET …/{id}/report.xlsx`) → `POST …/{id}/commit` → `imports.commit` job (one transaction). States as in the [import state diagram](diagrams/state-diagrams.md#4-import-job), including `needs_mapping`/`validating` and "commit refused → back to validated".
- **Parsing**: UTF-8 / UTF-8-BOM / UTF-16-BOM / Windows-1252 CSV with `, ; tab |` sniffing; XLSX via `openpyxl` read-only, cached values only, after a ZIP pre-check (no macros, uncompressed size and ratio caps). Hidden rows are imported like any other row (read-only mode can't see them); merged cells keep their top-left value only.
- **Mapping**: alias + fuzzy header matching; the header row is found among the first 20 rows; with several sheets the one whose header names the most known fields wins. A re-upload that supersedes an earlier import keeps the admin's mapping when the columns are identical. *Named mapping presets are not built yet.*
- **Duplicates**: the same bytes resume the open import; bytes that were already committed are refused with the date and person (`uq_import_jobs__active_file`).
- **Review**: row/column issues with codes from §4 (students use `MISSING_VALUE`, `INVALID_FORMAT`, `MANGLED_NUMBER`, `DUPLICATE_IN_FILE`, `UNKNOWN_COHORT` with suggestions, `ARCHIVED_COHORT`, `INVALID_EMAIL`, `INVALID_DATE`, `IMPLAUSIBLE_DATE`, `INVALID_YEAR`, `INVALID_PHONE`, `FORMULA_LIKE`, `ALREADY_EXISTS`, `NOT_ACTIVE`, `OVERWRITES_EXISTING`, file-level `MISSING_COLUMN`, `NO_DATA`, `LIMIT_EXCEEDED`). The annotated report is generated on demand (never stored) and written formula-safe. *Editing single cells in staging and excluding individual rows are not built yet* — the options are "fix and re-upload" and "import only the valid rows".
- **Marks** (Phase 8, `ingestion/marks.py`): one profile per exam, whose fields come from its papers and components. It accepts three shapes: single paper (a column per component), long (a course-code column) and wide (`<COURSE>_<COMPONENT>`). Columns missing from the file leave existing marks alone. Rule codes are `UNKNOWN_STUDENT`, `STUDENT_NOT_IN_EXAM`, `PAPER_NOT_IN_EXAM`, `UNKNOWN_COMPONENT`, `NOT_A_NUMBER`, `OUT_OF_RANGE`, `INVALID_PRECISION`, `UNKNOWN_CODE`, `ABSENT_WITH_MARKS`, `TOTAL_MISMATCH`, `NAME_MISMATCH`, `MISSING_MARK`, `NO_MARKS`, `MISSING_STUDENTS`, `DUPLICATE_IN_FILE`, `OVERWRITES_EXISTING`, `NOT_ASSIGNED`, `PAPER_LOCKED` and `EXAM_NOT_OPEN`. Faculty may import only for their assigned paper × cohort pairs and see only their own imports. The commit re-checks each entry's version: if a mark was changed in the grid after the check, the whole commit is refused. `GET …/template.xlsx?kind=marks&exam_id=…[&paper_id=…&cohort_id=…]` returns a roster pre-filled in the importer's own column layout, with Excel data validation for each component's range and the attendance codes. Golden files are in `tests/fixtures/imports/marks/`. In the UI, administrators use the **Marks** tab of Imports (pick an exam, then all papers or one paper) or *Import marks from Excel* in the exam workspace. Anyone who may import can use *Import from Excel* on a mark sheet, which downloads that cohort's template. Faculty review their imports at `/marking/imports/{id}`, since they have no admin area. A mark sheet always loads fresh when opened, so marks imported or saved elsewhere are never hidden behind a cached copy.
- **Tests**: golden corpus in `backend/tests/fixtures/imports/` (`tests/unit/test_import_golden.py`), hostile-file and report-safety unit tests, end-to-end API tests in `tests/integration/test_imports.py`. The 10,000-row target (§6) was measured on a laptop for P8.7: validated report in 1.6 s (CSV) / 2.7 s (XLSX), commit 2.7 s ([result](../benchmarks/results/2026-10-07-marks-import-10k.md)); not yet measured on production hardware. Import-sized membership queries bind arrays (`app/core/sql.py`), never one parameter per row.
