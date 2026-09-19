# Demo recording script (escalation + retry)

Record one continuous screen capture (5–8 minutes) showing the consultant supervising the agent. Use `data/demo/` files and a fresh migration.

## Prerequisites

```bash
python flask_app.py          # terminal 1
streamlit run streamlit_app.py   # terminal 2
ollama serve                 # if using live mapping (optional; alias fallback works)
```

## Suggested flow

1. **New migration** — Create migration → **Load demo files** (3 files, 13 rows).
2. **Mappings & review** — **Generate column mappings** → resolve any blocking mapping reviews.
3. **Analysis & review** — **Run analysis** and narrate the **Processing status** timeline (date scan → transform → duplicates → validate).
4. **Escalation (required)** — Resolve at least one item under **Needs review**, for example:
   - **Date format** on `employees_extra.csv` / `Date` (choose DD/MM/YYYY or MM/DD/YYYY), **or**
   - **Duplicate conflict** E002 (field-by-field resolution), **or**
   - **Validation** E011 (enter email) / exclude E010.
5. Re-run analysis or continue until **Ready to push** appears.
6. **Push to target** — **Push to target** → show E009 **failure** (HTTP 500) → **Retry failed push** → E009 **success** (HTTP 201).
7. **Audit log** — Scroll audit entries: agent mapping/date/dedupe actions, human correction, push failed/succeeded, retry.

## What reviewers should see

- Autonomous steps in the audit trail (`mapping auto-approved`, `exact duplicate deduplicated`, etc.).
- At least one **human** escalation resolution before push.
- **Retry** recovering E009 without manual DB edits.

Upload the video link in your submission email or README.
