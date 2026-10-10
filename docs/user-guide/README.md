# ScoreCode user guides (P17.3)

| Guide | For |
|---|---|
| [Administrator guide](admin-guide.md) | The exam office: owner, administrators, exam controllers |
| [Faculty guide](faculty-guide.md) | Teachers who enter marks for their papers |
| [Student guide](student-guide.md) | Students, and anyone checking a statement of marks |

Each institution has its own address, `https://<institution>.<scorecode domain>`. Sign in there, and
only there: an account at one institution means nothing at another.

## Languages (decision D29)
Students and parents can read their results in English, Hindi or Punjabi, and marksheets can be bilingual
(English with Hindi or Punjabi). The Hindi and Punjabi texts were written for ScoreCode and **should be
checked by a native speaker** before a school relies on them: the student screens'
[`hi.ts`](../../frontend/apps/tenant/src/lib/i18n/hi.ts) and [`pa.ts`](../../frontend/apps/tenant/src/lib/i18n/pa.ts),
and the marksheet's [`labels.py`](../../backend/app/modules/documents/labels.py). Staff screens are in
English.
