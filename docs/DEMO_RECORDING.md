# Demo recording script (escalation + rollback + retry)

Record one continuous screen capture (6–9 minutes) showing the consultant supervising the agent. Use `data/demo/` files and a completely fresh SQLite database.

## Prerequisites

1. Start Ollama in terminal 1:

   ```bash
   ollama serve
   ```

   In terminal 2, download once if needed and verify the locked open-source model:

   ```bash
   ollama pull llama3.2:3b
   .venv/bin/python scripts/verify_ollama.py
   ```

2. In terminal 2, start Flask with a new database filename for every rehearsal or recording. E009 is a fail-once simulation, so merely creating a new migration inside an old database is not sufficient:

   ```bash
   DATABASE_PATH=/tmp/darwinbox-demo-recording-01.sqlite3 FLASK_DEBUG=false .venv/bin/python flask_app.py
   ```

3. Start Streamlit in terminal 3:

   ```bash
   BACKEND_URL=http://127.0.0.1:5000 .venv/bin/streamlit run streamlit_app.py
   ```

Use a different database suffix for the actual recording if `recording-01` was used during rehearsal. Close unrelated tabs and hide notifications or private information before recording.

## Suggested flow

1. **Opening (15–20 seconds)** — State the problem and boundary: “The agent autonomously handles safe, deterministic decisions and asks a consultant only when a choice could corrupt client data.” Briefly show the target schema.
2. **New migration** — Create one migration and click **Load demo files**. Show 4 files and 16 source rows with different headers/formats.
3. **Mappings & review** — Click **Generate column mappings**. Point out one high-confidence auto-approved mapping, its confidence/reason, and that structural compatibility is enforced. Do not review every field.
4. **Analysis & date decision** — Click **Run analysis** and explain that the pipeline begins with its date scan. Contrast the two bundled date columns: `employees_extra.csv` auto-resolves to DD/MM/YYYY because `13/09/2024` is deterministic evidence, while `employees_ambiguous_dates.csv` stops for review because every value is dual-parse. The model may suggest a format but never applies it on ambiguity alone.
5. **Human escalation (required)** — Choose DD/MM/YYYY for `employees_ambiguous_dates.csv`, then click **Continue**. Narrate the remaining phases as they run: transform → duplicate analysis → validation. This is the clearest demonstration that a genuinely ambiguous decision stays human-owned.
6. **Duplicate decision** — Resolve **E002** field-by-field using `ravi@example.com`. Show both conflicting values and source lineage. Continue so validation is refreshed. Briefly mention that **E001** was automatically deduplicated with both source references retained.
7. **Validation decisions** — Correct **E011** with `anjali@example.com` and exclude **E010**. Continue until the page reports 13 records ready to push.
8. **First push** — Click **Push ready records (13)**. Show the latest-operation result and migration-wide state: 12 succeeded, E009 failed with HTTP 500, and 12 rows exist in the mock target.
9. **Rollback** — Click **Roll back latest batch (12)**. Show: 12 removed from target, 12 returned to ready, E009 unchanged as failed, and 0 rows in target. Explain: “E009 never reached the target, so rollback correctly preserves its failed state.”
10. **Selective recovery** — Click **Push ready records (12)** and show that E009 remains the one migration-wide failure. Then click **Retry failed records (1)**, show E009 succeeding with HTTP 201 on attempt 2, and confirm the final state: 13 pushed, 0 failed, 13 in target.
11. **Audit log** — Show automatic mapping/cleanup/deduplication, the human date/E002/E010/E011 decisions, first push failure, rollback explanation, second push, and retry success. Finish by opening target records or attempt history long enough to show per-record traceability.

## What reviewers should see

- Autonomous multi-file reconciliation and cleanup without field-by-field confirmation.
- At least one human escalation resolved with enough context to decide in one glance.
- Per-record target success/failure, batch-scoped rollback, selective re-push, and retry.
- A migration-wide state that remains accurate across operations.
- An audit trail explaining what changed, who decided, and why.

Upload the video and add its link to the README before submitting.
