# Darwinbox Forward Deployed Engineer — Master Implementation Specification

> **Purpose of this document**
>
> This is the single source of truth for Cursor and any other AI coding agent working on this take-home assignment.
>
> Agents must read this document before writing code.
>
> Do not reinterpret decisions that are already settled here.
>
> The implementation is intentionally scoped for a **small, complete, defensible MVP** rather than a broad migration platform.

---

# 1. Assignment Restatement

Build a small AI-assisted employee-data migration application.

The application receives multiple CSV/XLSX exports representing the same employee entity. Source files may contain:

- inconsistent column names
- different column layouts
- mixed date/datetime formats
- whitespace/casing issues
- duplicate records
- conflicting duplicate records
- missing required values
- invalid field values

The system must:

1. ingest multiple source files
2. infer source-to-target mappings
3. reconcile records into one normalized employee dataset
4. clean and normalize data automatically where safe
5. detect when AI confidence or deterministic rules indicate ambiguity
6. escalate only genuinely uncertain/conflicting cases
7. let a human approve/correct/exclude those cases
8. push valid records to a mock target API
9. report success/failure per record
10. support retry
11. support rollback
12. maintain a clear audit history
13. preserve traceability from every final normalized record back to all contributing source rows

The panel is evaluating the **autonomy boundary** more than raw feature count:

> Safe, deterministic and explainable operations should happen automatically.  
> Ambiguous, conflicting or missing information should go to a human.

The MVP must make that boundary visible in the UI.

---

# 2. Scope

## 2.1 BUILD THIS — Tier 1

Build Tier 1 completely before doing any Tier 2 work.

### 1. Project bootstrap

Create:

- Flask backend
- Streamlit frontend
- SQLite database
- Pandas/Pydantic processing layer
- pytest test setup
- Ollama client abstraction
- demo-data directory

The complete app must run locally.

---

### 2. Employee-only migration scope

Support only:

```text
employees
```

Do not build generic multi-entity migration.

Supported input files:

```text
.csv
.xlsx
```

Multiple files may belong to the same migration.

Preserve source:

- file name
- source row number

so review screens can identify where a record came from.

---

### 3. Multi-row source lineage

This is mandatory Tier 1 functionality.

A final normalized record may come from more than one source row.

Example:

```text
employees_legacy.csv row 2
E001, Meet Mehta, ...

employee_master.xlsx row 2
E001, Meet Mehta, ...
```

If these are exact normalized duplicates and are collapsed into one final employee record, the resulting employee record must retain references to **both** original source rows.

Similarly:

```text
employees_legacy.csv row 3
E002, Ravi Shah, ravi@example.com

employee_master.xlsx row 3
E002, Ravi Shah, ravi.work@example.com
```

After the human resolves this duplicate conflict into one final E002 record, that final record must still point back to **both** contributing rows.

Do not keep only whichever source row happened to “win.”

Required concept:

```text
Final normalized record
    ↓
one or more source-row references
```

At minimum each source reference must preserve:

```text
source_file
source_row_number
```

The UI/audit layer must be able to show where a reconciled record originated.

---

### 4. Target schema

Tier 1 uses one **default employee target schema**.

Do not implement schema versioning.

Default schema:

| Field | Type | Required |
|---|---|---:|
| `employee_id` | string | Yes |
| `first_name` | string | Yes |
| `last_name` | string | No |
| `email` | email | Yes |
| `joining_date` | date | No |
| `department` | string | No |
| `city` | string | No |

The schema should be shown in the UI, including on Settings / migration setup.

Tier 1 does not need full schema editing.

Tier 2 may add basic field editing.

---

### 5. File ingestion

Support:

- multiple CSV uploads
- multiple XLSX uploads
- mixed CSV + XLSX in the same migration
- preview
- row counts
- column names
- source row numbers

Reject unsupported file formats clearly.

---

### 6. Deterministic source analysis

Before calling AI, inspect every source column.

Determine:

- column name
- sample values
- probable source type

Supported inferred categories may include:

```text
string_like
email_like
date_like
number_like
boolean_like
unknown / mixed
```

This is deterministic preprocessing.

---

### 7. Deterministic mapping fallback

Implement exact-name / alias-based mapping before or as fallback to Ollama.

Known aliases should include at least:

```text
employee_id     → employee_id
emp_id          → employee_id
employee_code   → employee_id
emp_code        → employee_id
employee_no     → employee_id

email           → email
mail            → email
work_email      → email

doj             → joining_date
joining_date    → joining_date

dept            → department
department      → department

city            → city
office          → city
```

Alias handling should be case-insensitive after reasonable header normalization.

---

### 8. One real Ollama semantic mapping path

Use Ollama for semantic source-column → target-field mapping.

The AI must return:

- proposed target field
- confidence
- short reason
- alternatives only when genuinely plausible

Example:

```json
{
  "source_column": "DOJ",
  "source_type": "date_like",
  "target_field": "joining_date",
  "confidence": 0.96,
  "reason": "DOJ commonly refers to Date of Joining and the sample values are date-like.",
  "alternatives": []
}
```

Do not force the model to invent alternatives.

For example:

```text
Work Email → email
```

may validly return:

```json
"alternatives": []
```

---

### 9. AI confidence policy

The application, not the AI, decides whether review is required.

Exact threshold:

```text
confidence >= 0.85
→ eligible for automatic acceptance

confidence < 0.85
→ human review required
```

The LLM must not control `needs_human_review`.

Conceptually:

```python
needs_human_review = confidence < 0.85
```

but structural compatibility also participates in the decision.

---

### 10. Structural compatibility check

This is mandatory Tier 1 functionality.

AI confidence cannot override deterministic structural incompatibility.

Example:

Source:

```text
DOJ
```

Samples:

```text
12/04/2024
01/06/2023
23/11/2022
```

AI result:

```text
DOJ → employee_id
confidence = 0.91
```

The source values are clearly date-like.

`employee_id` is an identifier/string field.

Therefore:

```text
0.91 confidence
DOES NOT auto-approve.
```

The deterministic compatibility layer must flag/reject/escalate the mapping.

General examples:

```text
email_like   → email      = structurally compatible
date_like    → date       = structurally compatible
number_like  → number     = structurally compatible
boolean_like → boolean    = structurally compatible

date_like    → email      = incompatible
email_like   → date       = incompatible
```

String-like → string may be compatible.

---

### 11. Final mapping-decision formula

For Tier 1, the mapping decision must follow this policy:

```text
review_required =
    confidence < 0.85
    OR structural_compatibility_failed
    OR mapping cannot be produced safely
```

The escalation UI must show **which rule fired**.

Examples:

```text
Needs review:
Confidence 0.54 < required threshold 0.85
```

or:

```text
Needs review:
Structural incompatibility — source values are date-like but target field is email.
```

Do not show only:

```text
Needs review
```

without the reason.

---

### 12. Mapping UI

For every source column show:

- source file
- source column
- sample values
- detected source type
- proposed target
- confidence
- AI reason
- review rule / status
- action

Actions:

```text
Map to target field
Ignore source field
```

Auto-approved mappings must still be editable before processing continues.

Do not implement:

```text
Mark unresolved
Keep pending
```

If the user has not resolved an open mapping, it is already unresolved.

Blocking mapping issues must be resolved before transformation continues.

---

### 13. Cleaning — string

String normalization:

1. trim leading whitespace
2. trim trailing whitespace
3. collapse repeated internal whitespace
4. preserve meaningful casing

Example:

```text
"  Meet    Gopal   Mehta  "
→
"Meet Gopal Mehta"
```

Do not title-case automatically.

Example:

```text
McDonald
```

must not become:

```text
Mcdonald
```

---

### 14. Cleaning — email

Rules:

1. trim whitespace
2. lowercase
3. validate

Example:

```text
" MEET@EXAMPLE.COM "
→
"meet@example.com"
```

Do not automatically fix speculative typos.

Example:

```text
gmail.con
```

must not silently become:

```text
gmail.com
```

---

### 15. Cleaning — null values

Treat exactly these common values as null:

```text
""
" "
"NULL"
"null"
"N/A"
"NA"
"None"
"none"
"-"
```

A real non-null string must remain intact.

---

### 16. Cleaning — employee identifiers

For employee IDs:

- trim whitespace
- preserve case
- preserve leading zeroes
- never cast to numeric

Example:

```text
" 00125 "
→
"00125"
```

---

### 17. Cleaning — number

Tier 1 supported target type:

```text
number
```

There is no separate `integer` type.

Valid examples:

```text
"42"       → 42
"42.0"     → 42
"42.75"    → 42.75
"1,250"    → 1250
"-25"      → -25
" 18.5 "   → 18.5
```

Do not interpret:

```text
₹1,250
12 years
12 lakhs
1.250,50
abc
```

These fail safe numeric parsing.

---

### 18. Cleaning — boolean

Normalize case-insensitively.

True values:

```text
true
yes
y
1
```

False values:

```text
false
no
n
0
```

Examples:

```text
" YES " → true
"False" → false
"1"     → true
```

Do not guess:

```text
active
enabled
checked
maybe
```

---

### 19. Date normalization

This logic is fixed.

For target type `DATE`:

```text
1. Detect source date/datetime format at column level.
2. Resolve ambiguous date formats once per column.
3. Parse the value.
4. Preserve its calendar-date component.
5. Drop the time component.
6. Do not perform timezone conversion.
7. Output YYYY-MM-DD.
8. Audit that time was removed when present.
9. If a particular value still cannot be parsed,
   send only that record for review.
```

Examples:

```text
12/05/2024
→ 2024-05-12
```

```text
12/05/2024 09:30
→ 2024-05-12
```

```text
2024-05-12 14:22:31
→ 2024-05-12
```

```text
2024-05-12T09:30:00+05:30
→ 2024-05-12
```

Do not timezone-shift the calendar date.

---

### 20. Column-level date ambiguity

Example source column:

```text
03/04/2024
05/06/2024
07/08/2024
```

It may mean:

```text
DD/MM/YYYY
```

or:

```text
MM/DD/YYYY
```

Do not create one escalation per row.

Create one escalation for the entire source column.

UI:

```text
Date format is ambiguous.

Choose:

○ DD/MM/YYYY
○ MM/DD/YYYY
```

The human selects once.

Apply that format to the whole column.

If one particular value still fails afterwards:

```text
around Jan 2023
```

only that record becomes a record-level review item.

---

### 21. Duplicate detection

Duplicate analysis always runs.

Tier 1 includes an option:

```text
Auto-remove exact duplicates: ON/OFF
```

Default:

```text
ON
```

Do not implement a mode that disables duplicate detection entirely.

---

### 22. Exact normalized duplicate

A record is an exact duplicate only when **all normalized target-field values are equal**.

Example:

```text
E001 | Meet | Mehta | meet@example.com
E001 | Meet | Mehta | meet@example.com
```

If auto-dedupe is ON:

- keep one
- mark the duplicate as automatically deduplicated
- add audit entry
- retain source references from **all contributing duplicate rows** on the surviving final record

Exact employee ID equality by itself is not enough.

---

### 23. Conflicting duplicate

If records share the same `employee_id` but **even one normalized value differs**:

```text
DUPLICATE_CONFLICT
```

Example:

```text
E002 | ravi@example.com
E002 | ravi.work@example.com
```

Do not automatically merge.

Send for human review.

Other records continue.

After human resolution, the final reconciled record must retain lineage to **every source row that contributed to the conflict group**.

---

### 24. Duplicate conflict UI

Show source records side by side.

Example:

| Field | Record A | Record B | Final |
|---|---|---|---|
| employee_id | E002 | E002 | E002 |
| first_name | Ravi | Ravi | Ravi |
| last_name | Shah | Shah | Shah |
| email | ravi@example.com | ravi.work@example.com | selection |
| department | Product | Product | Product |
| city | Pune | Pune | Pune |

Fields that are equal:

```text
read-only
```

Fields that differ:

```text
Use Record A value
Use Record B value
Enter custom value
```

Actions:

```text
Save Resolution
Exclude Record
```

The escalation card must say why it exists:

```text
Rule fired:
Same employee_id but normalized field "email" differs.
```

Also show source-row references when practical:

```text
Record A:
employees_legacy.csv — row 3

Record B:
employee_master.xlsx — row 3
```

---

### 25. Validation

Use Pydantic for target validation.

At minimum check:

- required values
- valid email
- valid normalized date
- valid number
- valid boolean

A record may become:

```text
READY_TO_PUSH
```

or:

```text
NEEDS_REVIEW
```

---

### 26. Required-value rule

If a target field is required and no usable value exists:

```text
REQUIRED_VALUE_MISSING
```

Do not invent a value.

UI actions:

```text
Enter Value
Exclude Record
```

Example:

```text
employee_id = E011
email = null
```

Human either supplies the email or excludes E011.

---

### 27. Validation-failure rule

Example:

```text
email = pooja@@example.com
```

If safe deterministic cleanup cannot fix it:

```text
VALIDATION_FAILURE
```

Human options:

```text
Accept Suggestion       # only if a real suggestion exists
Enter Custom Value
Exclude Record
```

Do not require an AI suggestion.

---

### 28. Human ownership after escalation

This is a core invariant.

Once the system escalates a case:

```text
the human makes the final decision.
```

Do not allow:

```text
AI re-checks itself
→ new confidence
→ auto-approves its own escalation
```

No second confidence threshold exists after escalation.

If the system was confident enough to auto-handle the case, it should not have escalated it.

---

### 29. Record-level problems must not stop the run

Example:

```text
1000 records

995 valid
5 need review
```

Process all 1000.

The five become:

```text
NEEDS_REVIEW
```

The 995 continue.

Do not halt the migration globally for one bad record.

---

### 30. Unified review page

Tier 1 uses one unified:

```text
Analysis & Review
```

page.

It should list all open escalation types.

Each card must show:

- record or mapping
- source context
- source-row reference(s)
- issue type
- exact rule fired
- relevant values
- possible human actions

At minimum distinguish:

```text
MAPPING_AMBIGUITY
DATE_FORMAT_AMBIGUITY
DUPLICATE_CONFLICT
VALIDATION_FAILURE
REQUIRED_VALUE_MISSING
```

If unsafe transformation appears later, it may use:

```text
UNSAFE_TRANSFORMATION
```

but generic transformation building is not part of Tier 1.

---

### 31. Record status model

Keep Tier 1 record states deliberately small.

Use approximately:

```text
TRANSFORMED
NEEDS_REVIEW
READY_TO_PUSH
PUSHED
EXCLUDED
PUSH_FAILED
```

Do not build a large record-level state machine.

---

### 32. Mock target API

Use Flask.

Endpoint:

```text
POST /mock-target/employees
```

Support per-record responses.

Possible responses:

```text
201 Created
400 Invalid payload
409 Duplicate
500 Simulated target failure
```

---

### 33. Deterministic API failure demo

Use employee:

```text
E009
```

E009 must be a valid migrated record.

Target behavior:

```text
first push attempt
→ HTTP 500

retry
→ HTTP 201
```

This is deliberately an integration failure, not a source-data validation failure.

---

### 34. Retry

Retry only failed records.

Do not re-send successful records.

For E009:

```text
Attempt 1 → 500
Attempt 2 → 201
```

Preserve enough history to demonstrate both attempts.

---

### 35. Rollback

Tier 1 includes one rollback action.

The current push operation should have a batch/run identifier sufficient for rollback.

Mock-target records created by that push must retain the batch identifier.

Rollback endpoint:

```text
DELETE /mock-target/batches/<batch_id>
```

Rollback removes records created by that push batch.

Audit:

```text
Rollback requested
Rollback completed
```

Do not implement production distributed-transaction semantics.

---

### 36. Minimal push/API attempt information

For push/retry activity, retain enough information to show:

```text
record ID
employee ID
attempt number
endpoint
method
HTTP status
result
error message
timestamp
```

Do not create a production observability system.

Do not store complete HR payloads in logs by default.

No configurable redacted/full-payload logging toggle is required in Tier 1.

---

### 37. Minimal audit log

Tier 1 audit table:

```text
timestamp
actor
action
entity
reason
```

Actors:

```text
AGENT
SYSTEM
HUMAN
```

At minimum log:

```text
migration created
file uploaded
mapping generated
mapping auto-approved
mapping manually changed
mapping ignored
date-format decision
exact duplicate removed
duplicate conflict created
duplicate conflict resolved
required/validation escalation created
human correction
record excluded
push attempted
push succeeded
push failed
retry requested
retry succeeded/failed
rollback requested
rollback completed
```

Audit UI does not need advanced filtering/search in Tier 1.

---

### 38. Local-run prototype

Tier 1 delivery is local-first.

Do not spend Tier 1 time deploying the application.

Local run instructions are the primary prototype deliverable because Ollama itself is local and remote hosting would introduce deployment/model-connectivity risk unrelated to the assignment's core evaluation.

---

### 39. Git repository and README

Push to Git throughout implementation.

Commit by meaningful phase.

Examples:

```text
feat: bootstrap flask and streamlit apps
feat: add csv xlsx ingestion
feat: add deterministic and ollama mapping
feat: add structural compatibility policy
feat: add cleaning and date normalization
feat: add duplicate review
feat: add validation escalation queue
feat: add mock target retry rollback
docs: add readme and demo instructions
```

README requirements are specified later in this document.

---

### 40. Demo recording readiness

The application must be designed so the full demo can be recorded in one continuous pass without manipulating database state manually.

The exact click-through sequence is defined in the Deliverables section.

---

## 2.2 BUILD ONLY IF TIER 1 IS DONE — Tier 2

Do Tier 2 only after Tier 1 works end-to-end and is stable.

### 1. Focused pytest suite

Add at least these tests:

1. date ambiguity detection
2. duplicate conflict classification
3. confidence threshold policy
4. structural compatibility overriding high AI confidence
5. required-field validation if time allows
6. source-lineage preservation for exact dedupe or duplicate resolution if time allows

Do not build a huge test suite at the expense of a working demo.

---

### 2. Full Name split

Support:

```text
Full Name
→ first_name + last_name
```

Exact rule:

```text
first token    → first_name
remaining text → last_name
```

Examples:

```text
Meet Mehta
→
first_name = Meet
last_name = Mehta
```

```text
Meet Gopal Mehta
→
first_name = Meet
last_name = Gopal Mehta
```

Single-word:

```text
Madonna
→
first_name = Madonna
last_name = null
```

If default schema remains:

```text
last_name optional
```

Madonna remains valid.

If Tier-2 schema editing changes `last_name` to required:

```text
Madonna
→ REQUIRED_VALUE_MISSING
```

Never invent a surname.

---

### 3. Basic schema field editing

If Tier 1 is stable, allow Settings UI to edit the current default target schema.

Support:

```text
Add field
Edit field
Delete field
Change supported type
Required ON/OFF
```

Supported types remain:

```text
string
email
date
number
boolean
```

Do not implement schema versions/snapshots.

This is intentionally a basic editor only.

---

### 4. Streamlit polish

Only after functionality is stable.

Optional improvements:

- clearer status badges
- migration progress indicator
- nicer review cards
- improved tables
- better empty/error states

Do not redesign architecture for visual polish.

---

## 2.3 DO NOT BUILD — Explicit Exclusions

These items were deliberately considered and cut.

### Schema versioning / snapshots

**Do not build.**

Reason: useful production feature but not necessary to demonstrate the six acceptance criteria within the time expectation.

Mention as a next step.

---

### Multi-batch push-history workflow/UI

**Do not build.**

Reason: Tier 1 only needs a working push, retry and rollback flow. Persistent multi-batch lifecycle/history adds state-management complexity without improving the core demo enough.

Mention as a next step.

---

### Configurable full-payload/redacted-payload logging toggle

**Do not build.**

Reason: logs should simply avoid storing full HR payloads by default. No runtime toggle is necessary.

---

### Advanced audit search/filter UI

**Do not build.**

Reason: a plain chronological audit table already satisfies the auditability signal.

---

### Full 10-table production data model

**Do not build.**

Reason: unnecessary persistence complexity for this take-home.

Use only the minimal storage needed by Tier 1/Tier 2.

---

### Large migration/record state machine

**Do not build.**

Reason: use a compact status model sufficient for the prototype.

---

### Ollama-outage simulation test suite

**Do not build as a major testing feature.**

Fallback behavior may exist, but do not spend meaningful Tier-1 time building a full failure simulation suite.

---

### React

**Do not build.**

Streamlit is the locked frontend.

---

### FastAPI

**Do not build.**

Flask is the locked backend.

---

### LangGraph

**Do not build.**

Plain Python orchestration is sufficient.

---

### PostgreSQL

**Do not build.**

SQLite is sufficient.

---

### Redis / Celery / Kafka

**Do not build.**

No background/distributed workflow is needed.

---

### Authentication / RBAC

**Do not build.**

Out of scope for the assignment.

---

### Multi-entity migration

**Do not build.**

Only employees are required.

---

### Generic transformation-builder UI

**Do not build.**

No regex/formula/expression builder.

---

### Generic multiple-source → one-target transformations

**Do not build.**

Example intentionally unsupported:

```text
first_name + last_name → full_name
```

unless future work explicitly adds it.

Tier 2 Full Name split is the opposite direction and is a single predefined transformation.

---

### Fuzzy entity-resolution engine

**Do not build.**

Duplicate handling is based on exact normalized equality and same-employee-ID conflicts.

---

### Production observability stack

**Do not build.**

No Prometheus, ELK, distributed tracing, etc.

---

### Hosted deployment as a Tier-1 requirement

**Do not build unless everything else is already complete and stable.**

Local run + demo recording is the delivery path.

---

# 3. Locked Tech Stack

No substitutions unless explicitly approved.

| Concern | Technology |
|---|---|
| Frontend | Streamlit |
| Backend | Flask |
| Data processing | Pandas |
| Validation | Pydantic |
| AI runtime | Ollama |
| AI model | Open-source Ollama-compatible model |
| Database | SQLite |
| Testing | pytest |
| Agent/orchestration | Plain Python |
| Input | CSV/XLSX |
| Target integration | Flask mock endpoint |

Do not replace Flask with FastAPI.

Do not replace Streamlit with React.

Do not introduce LangGraph.

---

# 4. Repository Structure

Use a small structure matching Tier 1/Tier 2.

```text
darwinbox-migration-agent/
│
├── streamlit_app.py
├── flask_app.py
├── requirements.txt
├── README.md
├── IMPLEMENTATION_SPEC.md
├── .env.example
│
├── app/
│   ├── config.py
│   ├── database.py
│   │
│   ├── services/
│   │   ├── ingestion.py
│   │   ├── type_inference.py
│   │   ├── llm_client.py
│   │   ├── mapping.py
│   │   ├── compatibility.py
│   │   ├── cleaning.py
│   │   ├── dates.py
│   │   ├── duplicates.py
│   │   ├── validation.py
│   │   ├── escalation.py
│   │   ├── push.py
│   │   └── audit.py
│   │
│   └── routes/
│       ├── migrations.py
│       ├── mappings.py
│       ├── reviews.py
│       ├── pushes.py
│       └── mock_target.py
│
├── data/
│   ├── demo/
│   │   ├── employees_legacy.csv
│   │   ├── employee_master.xlsx
│   │   └── employees_extra.csv
│   └── uploads/
│
└── tests/
    ├── test_dates.py
    ├── test_mapping.py
    ├── test_duplicates.py
    └── test_validation.py
```

Do not create folders/modules solely for theoretical future features.

---

# 5. Detailed Tier-1 Capabilities

> **Precedence rule**
>
> This section expands and clarifies the Tier-1 requirements in §2.1.
>
> If §5 and §2.1 ever appear to conflict because of a later edit, **§2.1 wins** unless the user explicitly changes that precedence.
>
> Any change to an exact rule in §2.1 should also be reflected here so the document stays internally consistent.

---

## 5.1 Ingestion

### Required

Read:

```text
CSV
XLSX
```

Multiple files per migration.

For every source row preserve:

```text
source_file
source_row_number
```

Display file preview and row count.

### Multi-row lineage

When multiple source rows contribute to one normalized employee, preserve **all** source references.

Example:

```text
Final E001
sources:
- employees_legacy.csv row 2
- employee_master.xlsx row 2
```

Example after conflict resolution:

```text
Final E002
sources:
- employees_legacy.csv row 3
- employee_master.xlsx row 3
```

Do not discard one source reference merely because one value was selected over another.

The final normalized record must be able to answer:

```text
Which original file row(s) did this record come from?
```

### Errors

Unsupported extension:

```text
reject with clear user-visible error
```

Unreadable file:

```text
mark ingestion failure clearly
```

Do not silently skip a file.

---

## 5.2 Source-Type Inference

Before AI mapping, inspect representative values.

Examples:

```text
meet@example.com
ravi@example.com
→ email_like
```

```text
12/05/2024
18/08/2023
→ date_like
```

```text
42
19.5
→ number_like
```

```text
yes
no
→ boolean_like
```

Save/display enough source samples for mapping review.

---

## 5.3 AI Mapping Contract

The Ollama client should be isolated from deterministic policy.

Do not put mapping-policy rules inside the Ollama-call function.

Concept:

```python
class LLMClient:
    def infer_mapping(...):
        ...
```

Expected structured result:

```json
{
  "source_column": "DOJ",
  "source_type": "date_like",
  "target_field": "joining_date",
  "confidence": 0.96,
  "reason": "DOJ commonly refers to Date of Joining and the sample values are date-like.",
  "alternatives": []
}
```

Malformed/unparseable LLM output must not crash the migration.

Fallback:

```text
deterministic aliases
or
human mapping review
```

---

## 5.4 Mapping Decision Policy

Exact threshold:

```text
0.85
```

Rule:

```text
confidence >= 0.85 AND structurally compatible
→ auto-approved

confidence < 0.85
→ review

structurally incompatible
→ review regardless of confidence
```

Example A:

```text
DOJ → joining_date
confidence = 0.96
source = date_like
target = date

→ auto-approved
```

Example B:

```text
Date → joining_date
confidence = 0.54

→ review
Reason: confidence 0.54 < 0.85
```

Example C:

```text
DOJ → employee_id
confidence = 0.91
source = date_like
target = identifier/string

→ review
Reason: structural incompatibility
```

This policy must be visible in UI/reasoning.

---

## 5.5 Cleaning Rules

### Nulls

Exactly normalize these as null:

```text
""
" "
"NULL"
"null"
"N/A"
"NA"
"None"
"none"
"-"
```

### Strings

```text
trim edges
collapse repeated spaces
preserve casing
```

Example:

```text
"  Meet    Mehta "
→
"Meet Mehta"
```

### Email

```text
trim
lowercase
validate
```

Example:

```text
" MEET@EXAMPLE.COM "
→
"meet@example.com"
```

Do not autocorrect domain spelling.

### Employee ID

```text
trim
preserve leading zeroes
preserve case
never numeric-cast
```

### Number

Accept:

```text
"42"
"42.0"
"42.75"
"1,250"
"-25"
" 18.5 "
```

Reject:

```text
₹1,250
12 years
12 lakhs
1.250,50
abc
```

### Boolean

True:

```text
true
yes
y
1
```

False:

```text
false
no
n
0
```

Case-insensitive.

Reject:

```text
active
enabled
checked
maybe
```

---

## 5.6 Date Engine

Exact algorithm:

```text
1. Detect source date/datetime format at column level.
2. Resolve ambiguous date formats once per column.
3. Parse the value.
4. Preserve its calendar-date component.
5. Drop the time component.
6. Do not perform timezone conversion.
7. Output YYYY-MM-DD.
8. Audit that time was removed when present.
9. If a particular value still cannot be parsed,
   send only that record for review.
```

Examples:

```text
12/05/2024
→ 2024-05-12
```

```text
12/05/2024 09:30
→ 2024-05-12
```

```text
2024-05-12 14:22:31
→ 2024-05-12
```

```text
2024-05-12T09:30:00+05:30
→ 2024-05-12
```

Do not timezone-shift.

### Ambiguous column

Input:

```text
03/04/2024
05/06/2024
07/08/2024
```

Expected:

```text
column-level DATE_FORMAT_AMBIGUITY
```

Human selects:

```text
DD/MM/YYYY
```

or:

```text
MM/DD/YYYY
```

Apply once for the column.

---

## 5.7 Duplicate Engine

### Exact duplicate

Only if **all normalized target values match**.

Example:

```text
E001 | Meet | Mehta | meet@example.com
E001 | Meet | Mehta | meet@example.com
```

With auto-remove ON:

```text
retain one
audit duplicate removal
preserve lineage from both source rows
```

### Conflict

Same `employee_id`, any normalized field difference:

```text
DUPLICATE_CONFLICT
```

Example:

```text
E002 | ravi@example.com
E002 | ravi.work@example.com
```

Never auto-select one.

After human resolution:

```text
one final E002 record
+
lineage to all contributing E002 source rows
```

---

## 5.8 Escalation UI

Every escalation must display:

```text
issue type
rule that fired
source context
source-row reference(s)
record/mapping values
available human actions
```

Bad:

```text
Needs review
```

Good:

```text
Needs review

Rule:
Confidence 0.54 is below automatic-acceptance threshold 0.85.
```

Good:

```text
Needs review

Rule:
Same employee_id E002 but normalized email differs.
```

Good:

```text
Needs review

Rule:
Required target field email has no usable value.
```

---

## 5.9 Record Resolution

### Duplicate conflict

Human chooses A / B / custom for each conflicting field.

Final reconciled record keeps all contributing source references.

### Required missing

Human:

```text
Enter Value
Exclude Record
```

### Validation failure

Human:

```text
Accept Suggestion      # only when present
Enter Custom Value
Exclude Record
```

After correction:

```text
normalize again
validate again
```

If valid:

```text
READY_TO_PUSH
```

---

## 5.10 Exclusion

Use UI term:

```text
Exclude Record
```

not:

```text
Reject Record
```

Excluded means:

```text
do not push to target
keep audit history
```

Status:

```text
EXCLUDED
```

---

## 5.11 Push

Push only:

```text
READY_TO_PUSH
```

records.

One bad/review record must not stop ready records.

Per-record result:

```text
success
or
failure
```

E009 must fail first attempt with:

```text
500
```

and succeed after retry:

```text
201
```

---

## 5.12 Retry

Retry only failed records.

Do not resend successful records.

Preserve attempt information.

Example:

```text
E009
Attempt 1: 500
Attempt 2: 201
```

---

## 5.13 Rollback

Push operation has a batch ID.

Created target records retain that ID.

Rollback:

```text
DELETE /mock-target/batches/<batch_id>
```

removes records created in that push.

Do not implement distributed transactions.

---

## 5.14 Audit

Plain chronological table.

Columns:

```text
timestamp
actor
action
entity
reason
```

Example:

```text
10:34 AGENT  Mapping generated     DOJ         DOJ → joining_date, confidence 0.96
10:34 SYSTEM Mapping auto-approved DOJ         confidence >= 0.85 and compatible
10:39 SYSTEM Duplicate escalated   E002        same employee_id, different email
10:44 HUMAN  Duplicate resolved    E002        selected ravi.work@example.com
10:51 SYSTEM Push failed           E009        HTTP 500
10:52 HUMAN  Retry requested       E009
10:52 SYSTEM Push succeeded        E009        HTTP 201
```

---

# 6. Demo Data

Do not regenerate arbitrary demo data.

Use these concrete records as the baseline.

## 6.1 `employees_legacy.csv`

Columns:

```text
Emp Code
Employee Name
DOJ
Mail
Dept
City
```

Rows:

```text
E001,Meet Mehta,12/05/2024,MEET@EXAMPLE.COM,Engineering,Mumbai
E002,Ravi Shah,01/06/2023,ravi@example.com,Product,Pune
E003,Anita Rao,18/08/2022,anita@example.com,Finance,Bengaluru
E004,Madonna,22/09/2021,madonna@example.com,HR,Mumbai
```

Selected cells may include leading/trailing whitespace to demonstrate normalization, but do not change the semantic values above.

---

## 6.2 `employee_master.xlsx`

Columns:

```text
Employee ID
Full Name
Joining Date
Work Email
Department
Office
```

Rows:

```text
E001,Meet Mehta,2024-05-12,meet@example.com,Engineering,Mumbai
E002,Ravi Shah,2023-06-01,ravi.work@example.com,Product,Pune
E005,John Patel,2024-10-20,john@example.com,Engineering,Hyderabad
E006,Priya Desai,2024-09-15,priya@example.com,HR,Mumbai
```

Expected behavior:

```text
E001
→ exact normalized duplicate of legacy E001
→ final E001 retains both source-row references
```

```text
E002
→ duplicate conflict because email differs
→ resolved final E002 retains both source-row references
```

---

## 6.3 `employees_extra.csv`

Columns:

```text
Employee_No
Name
Date
Email
Dept
City
```

Rows:

```text
E007,Amit Kumar,03/04/2024,amit@example.com,Engineering,Mumbai
E008,Neha Joshi,05/06/2024,neha@example.com,Finance,Pune
E009,Demo Fail,07/08/2024,demo.fail@example.com,Product,Mumbai
E010,Pooja Shah,11/12/2024,pooja@@example.com,HR,Mumbai
E011,Anjali Gupta,13/09/2024,,Engineering,Mumbai
```

Expected behavior:

```text
Date
→ semantically ambiguous source header
→ DD/MM vs MM/DD ambiguity may also require one column-level review
```

```text
E009
→ valid migration record
→ target API fails once
→ retry succeeds
```

```text
E010
→ invalid email
→ validation escalation
```

```text
E011
→ missing required email
→ REQUIRED_VALUE_MISSING
```

---

# 7. Tier-2 Exact Behavior

## 7.1 Full Name Split

If implemented:

```text
Meet Mehta
→ Meet / Mehta
```

```text
Meet Gopal Mehta
→ Meet / Gopal Mehta
```

```text
Madonna
→ Madonna / null
```

Do not infer cultural naming semantics beyond this simple rule.

---

## 7.2 Basic Schema Editing

If implemented:

Settings must permit editing:

```text
field name
type
required
```

Supported types:

```text
string
email
date
number
boolean
```

No schema versioning.

Changes apply to the current prototype schema only.

Do not retroactively build historical-snapshot behavior.

---

# 8. Core Invariants

These rules must never be violated.

## Invariant 1 — AI proposes; deterministic policy decides review

The LLM does not decide whether it may auto-approve itself.

---

## Invariant 2 — Confidence threshold is exactly 0.85

```text
>= 0.85
```

may auto-approve only when structurally compatible.

```text
< 0.85
```

requires review.

---

## Invariant 3 — Structural incompatibility overrides AI confidence

Example:

```text
DOJ → employee_id at 0.91
```

still requires review.

---

## Invariant 4 — Every escalation shows the rule that fired

Do not display generic unexplained “Needs Review”.

---

## Invariant 5 — Column-wide date ambiguity is resolved once

Do not escalate every row for the same DD/MM vs MM/DD problem.

---

## Invariant 6 — Required values are never fabricated

Human supplies them or excludes the record.

---

## Invariant 7 — Exact duplicate means all normalized values match

Same employee ID alone is not an exact duplicate.

---

## Invariant 8 — Any conflicting duplicate field requires human review

Do not automatically prefer first/last/newer source.

---

## Invariant 9 — Record-level issues do not block unrelated records

The system continues processing safe records.

---

## Invariant 10 — Human owns the final decision after escalation

AI cannot self-approve after escalation.

---

## Invariant 11 — Successful target pushes are not retried

Retry only failed records.

---

## Invariant 12 — Full HR payloads are not logged by default

Store only the API/debug information needed to explain what happened.

---

## Invariant 13 — Reconciliation must never destroy source lineage

Every final normalized record must retain references to **all source rows that contributed to it**.

This applies to:

```text
exact deduplication
duplicate conflict resolution
any future reconciliation that combines source rows
```

If E001 originated from two files, the final E001 must expose both origins.

If E002 was resolved from two conflicting source rows, the final E002 must expose both origins.

---

# 9. Deliverables

## 9.1 Working Prototype

### Delivery decision

Use:

```text
LOCAL RUN INSTRUCTIONS + DEMO RECORDING
```

as the primary deliverable.

Do not make hosted deployment a blocker.

### Why

Ollama is a local model runtime.

Hosting Streamlit/Flask while also making Ollama reliably reachable remotely adds infrastructure risk without improving the main evaluation criteria.

A polished local prototype with clear instructions is safer and directly permitted by the assignment.

### Local startup should be simple

README should make it possible to run approximately:

```bash
ollama serve
```

```bash
ollama pull <chosen-model>
```

```bash
pip install -r requirements.txt
```

```bash
python flask_app.py
```

and separately:

```bash
streamlit run streamlit_app.py
```

Exact commands must match the final implementation.

---

## 9.2 Source Repository

Use Git from the beginning.

Do not dump the entire application in one final commit.

Commit per meaningful phase.

Required README sections:

### Project Purpose

Explain the employee-data migration use case.

### Architecture

Describe:

```text
Streamlit
→ Flask
→ migration services
→ Ollama
→ SQLite
→ mock target API
```

### Tech Stack

List locked stack.

### Prerequisites

Python version.

Ollama installation.

Chosen model.

### Setup

Exact commands.

### Running the Backend

Exact command.

### Running Streamlit

Exact command.

### Running Tests

Exact pytest command.

### Demo Data

Explain the three files.

### Demo Scenario

Explain what E001/E002/E009/E010/E011 demonstrate.

### Autonomy Boundary

Explain:

```text
AI proposes
deterministic policy decides review
human resolves escalated ambiguity
```

### Source Lineage

Explain that reconciled final records preserve references to all contributing source rows.

### Known Limitations / Deliberate Scope Cuts

Explicitly name:

- no schema versioning
- no production authentication
- no generic transformation engine
- no multi-entity support
- no advanced fuzzy deduplication
- no production-scale observability
- no persistent multi-batch history UI

This turns scope cuts into conscious engineering decisions rather than apparent omissions.

---

## 9.3 One-Page Write-Up

Maximum one page.

Use this exact structure.

### 1. Approach

2–3 sentences.

Explain that:

- AI handles semantic interpretation
- deterministic code handles correctness/safety
- humans only resolve genuinely ambiguous/conflicting cases

### 2. Autonomy / Escalation Boundary

State precisely:

```text
AI proposes a mapping with confidence/reason.

Application code decides whether review is required using:
- confidence threshold 0.85
- structural compatibility
- duplicate conflict detection
- required-value validation
```

Once escalated:

```text
human owns final resolution
```

### 3. Concrete Examples

Use at least these examples.

#### Example A — Auto

```text
DOJ → joining_date
confidence 0.96
date_like → date

→ automatically accepted
```

#### Example B — Low confidence

```text
Date → joining_date
confidence 0.54

→ escalated
```

#### Example C — AI confidence overridden

```text
DOJ → employee_id
confidence 0.91

but source is date-like

→ escalated due structural incompatibility
```

#### Example D — Duplicate

```text
same employee_id
different email

→ human field-by-field resolution
```

Also mention:

```text
final resolved record keeps lineage to both contributing source rows
```

### 4. What I Would Build Next

Pull directly from deliberate cuts:

- schema versioning/snapshots
- richer push-batch history
- audit filtering/search
- additional transformations
- production permissions/authentication
- broader entity support

Do not describe these as unfinished requirements.

Describe them as deliberate next steps after the MVP.

---

## 9.4 Demo Recording

The recording must be executable in one continuous pass.

Use this sequence.

### Step 1

Open the application.

Show the default employee target schema.

---

### Step 2

Start a new migration.

Upload:

```text
employees_legacy.csv
employee_master.xlsx
employees_extra.csv
```

---

### Step 3

Start analysis.

Show:

- files detected
- source columns
- mapping generation

---

### Step 4

Open Mappings.

Show:

- high-confidence mapping
- confidence
- reason
- auto-approved state

Example:

```text
DOJ → joining_date
96%
```

---

### Step 5

Resolve one ambiguous mapping or date-format decision.

Preferred required escalation moment:

```text
Date
03/04/2024
05/06/2024
07/08/2024
```

Show the exact rule:

```text
confidence below 0.85
and/or date format ambiguous
```

Human chooses the appropriate mapping/format.

This already satisfies the assignment requirement to show a human resolving an escalation through the UI.

---

### Step 6

Continue processing.

Show exact duplicate handling:

```text
E001
```

was automatically deduplicated because all normalized values matched.

Also show, if practical:

```text
Sources:
employees_legacy.csv row 2
employee_master.xlsx row 2
```

to demonstrate reconciliation/source lineage.

---

### Step 7

Open duplicate conflict:

```text
E002
```

Show:

```text
ravi@example.com
vs
ravi.work@example.com
```

Resolve it field-by-field.

Show both source-row references.

---

### Step 8

Show record validation review.

Example:

```text
E010
pooja@@example.com
```

or:

```text
E011
missing email
```

Correct or exclude.

---

### Step 9

Show remaining records ready for push.

Push them to the mock target.

---

### Step 10

Show E009 target failure.

```text
HTTP 500
```

Show per-record failure.

---

### Step 11

Click Retry.

E009:

```text
HTTP 201
```

Show that only failed E009 was retried.

---

### Step 12

Show rollback control.

If stable and fast enough, demonstrate it.

If demonstrating rollback would make the recording unnecessarily long, at minimum show that the action exists and explain it in README/write-up.

---

### Step 13

Open Audit Log.

Show sequence such as:

```text
AI mapping generated
mapping auto-approved
date review resolved
exact duplicate removed
duplicate conflict resolved
validation issue resolved
push attempted
E009 failed
retry requested
E009 succeeded
```

---

# 10. Testing Plan

Do not let testing become larger than the product.

Tier 1 first.

If stable early, implement Tier-2 tests.

## Test 1 — Date ambiguity

Input:

```text
03/04/2024
05/06/2024
07/08/2024
```

Expected:

```text
one column-level DATE_FORMAT_AMBIGUITY
```

Not:

```text
three row-level escalations
```

---

## Test 2 — Duplicate classification

Input normalized records:

```text
E001 | Meet | Mehta | meet@example.com
E001 | Meet | Mehta | meet@example.com
```

Expected:

```text
EXACT_DUPLICATE
```

Input:

```text
E002 | Ravi | Shah | ravi@example.com
E002 | Ravi | Shah | ravi.work@example.com
```

Expected:

```text
DUPLICATE_CONFLICT
```

---

## Test 3 — Confidence threshold

AI result:

```text
DOJ → joining_date
confidence = 0.96
compatible
```

Expected:

```text
auto-approved
```

AI result:

```text
Date → joining_date
confidence = 0.54
```

Expected:

```text
review
```

---

## Test 4 — Structural compatibility

AI result:

```text
DOJ → employee_id
confidence = 0.91
```

Detected source type:

```text
date_like
```

Expected:

```text
review
```

Reason:

```text
structural incompatibility
```

---

## Test 5 — Required field

Target:

```text
email required
```

Record:

```text
E011
email = null
```

Expected:

```text
REQUIRED_VALUE_MISSING
NEEDS_REVIEW
```

Human enters valid email:

```text
READY_TO_PUSH
```

Human excludes:

```text
EXCLUDED
```

---

## Test 6 — Source-lineage preservation

Exact duplicate inputs:

```text
employees_legacy.csv row 2 → E001
employee_master.xlsx row 2 → E001
```

After exact dedupe:

```text
one final E001
```

Expected lineage:

```text
employees_legacy.csv row 2
employee_master.xlsx row 2
```

Conflict inputs:

```text
employees_legacy.csv row 3 → E002
employee_master.xlsx row 3 → E002
```

After human resolution:

```text
one final E002
```

Expected lineage:

```text
both original source rows retained
```

---

# 11. Build Order for Cursor

Cursor should implement in this exact order.

## Phase 1 — Bootstrap

Create:

- Flask
- Streamlit
- SQLite
- config
- requirements
- directories

Verify both applications launch.

### Checkpoint before Phase 2

Verify:

```text
Flask starts successfully
Streamlit starts successfully
SQLite connection works
```

Commit:

```text
feat: bootstrap flask streamlit and sqlite
```

Do not proceed until verified.

---

## Phase 2 — Migration + file ingestion

Implement:

- migration creation
- CSV upload
- XLSX upload
- source-file storage
- source row numbers
- previews
- source-lineage representation capable of storing multiple rows per final record

Do not add AI.

### Checkpoint

Upload all three demo files.

Verify:

- row counts
- columns
- row numbers
- original source identities preserved

Commit.

---

## Phase 3 — Type inference + deterministic aliases

Implement:

- source sampling
- type inference
- alias mapper

Verify obvious mappings.

### Checkpoint

Test exact examples from this spec.

Commit.

---

## Phase 4 — Ollama semantic mapping

Implement isolated `LLMClient`.

Add:

- confidence
- reason
- alternatives
- safe JSON parsing
- fallback behavior

### Checkpoint

Verify one valid Ollama mapping.

Verify malformed/failure path does not crash.

Commit.

---

## Phase 5 — Mapping policy

Implement separately from AI call:

```text
0.85 confidence threshold
structural compatibility
review reason
```

Build Mappings UI.

This phase is critical.

### Checkpoint

Verify exact examples:

```text
DOJ → joining_date @ 0.96
→ auto
```

```text
Date → joining_date @ 0.54
→ review
```

```text
DOJ → employee_id @ 0.91
→ review due structural incompatibility
```

Commit only after all three behave correctly.

---

## Phase 6 — Cleaning

Implement deterministic:

- nulls
- strings
- emails
- numbers
- booleans
- employee IDs

### Checkpoint

Verify exact examples from §5.5.

Commit.

---

## Phase 7 — Date engine

Implement exact date rules.

Build one-column ambiguity review.

### Checkpoint

Verify:

```text
03/04/2024
05/06/2024
07/08/2024
```

creates one column-level review, not three row reviews.

Verify time removal.

Commit.

---

## Phase 8 — Duplicate engine

Implement:

- exact-normalized comparison
- auto-remove toggle
- conflict detection
- field-by-field resolution UI
- multi-row source-lineage preservation

### Checkpoint

Verify:

```text
E001
→ exact duplicate
→ one final record
→ both source rows retained
```

Verify:

```text
E002
→ conflict
→ human resolution
→ one final record
→ both source rows retained
```

Commit.

---

## Phase 9 — Validation / unified review

Implement:

- Pydantic validation
- required-value detection
- invalid email
- correction
- exclusion
- rule-fired display

Do not let record review block unrelated records.

### Checkpoint

Verify E010 and E011.

Commit.

---

## Phase 10 — Mock target

Implement:

```text
POST /mock-target/employees
DELETE /mock-target/batches/<batch_id>
```

Implement deterministic E009 failure.

### Checkpoint

Verify E009 first attempt = 500.

Commit.

---

## Phase 11 — Push, retry, rollback

Implement:

- push READY_TO_PUSH records
- per-record result
- retry failed only
- rollback current push batch

### Checkpoint

Verify:

```text
E009 first attempt → 500
retry → 201
successful records not resent
rollback removes batch-created records
```

Commit.

---

## Phase 12 — Audit

Implement minimal chronological audit log.

Do not build advanced filters.

### Checkpoint

Run full demo path and verify all meaningful actions create audit entries.

Commit.

---

## Phase 13 — Tier-2 only

Only if all Tier 1 works:

- focused pytest tests
- Full Name split
- basic schema editor
- visual polish

Each Tier-2 addition gets its own verification and commit.

---

## Phase 14 — Deliverables

Before adding any unrelated feature:

- README
- Git cleanup
- demo run
- one-page write-up
- demo recording

---

# 12. Rules for AI Coding Agents

1. **This document is authoritative.**
   Do not reinterpret settled decisions.

2. **Re-read this document at the beginning of every new coding session.**
   Do not rely on memory from a prior Cursor/agent session.

3. **Before starting a phase, read that phase and every section it references.**

4. **Stop after each implementation phase and verify the exact acceptance examples before moving on.**

5. **Do not proceed to the next phase merely because code compiles.**
   The phase-specific examples/checkpoint must behave correctly.

6. **Commit after every verified phase.**
   Do not accumulate many unrelated phases into one commit.

7. **If a later phase breaks an already-verified invariant, fix the regression before continuing.**

8. **Do not add dependencies outside the locked stack** without explicit user approval.

9. **Do not mix LLM inference and deterministic policy in the same function.**

   Bad:

   ```python
   def ask_llm_and_decide_everything():
   ```

   Preferred:

   ```text
   llm_client
   → mapping proposal

   policy/compatibility service
   → review decision
   ```

10. **Do not let the AI decide its own escalation policy.**

11. **Do not weaken the 0.85 threshold.**

12. **Do not auto-resolve structural incompatibility because AI confidence is high.**

13. **Do not create generic review cards without explaining which rule fired.**

14. **Do not create a generic transformation framework.**

15. **Do not make one invalid record stop unrelated records.**

16. **Do not invent missing required employee values.**

17. **Do not auto-merge conflicting duplicates.**

18. **Do not lose source lineage while deduplicating or reconciling records.**

19. **Do not retry successful API records.**

20. **Do not log complete employee HR payloads by default.**

21. **Do not spend Tier-1 time implementing anything listed under DO NOT BUILD.**

22. **Do not start Tier 2 until Tier 1 works end-to-end.**

23. **If the implementation spec is genuinely ambiguous, stop and ask the user instead of guessing.**

24. **Prefer the simplest implementation that visibly demonstrates the acceptance criterion.**

25. **When modifying an existing rule, search this document for duplicate mentions of that rule and keep them consistent.**
    §2.1 has precedence over §5 if a conflict accidentally remains.

---

# 13. Operating Prompt for Cursor / AI Coding Agents

Use this prompt together with this specification whenever a new Cursor/agent implementation session begins.

```text
You are implementing the Darwinbox Forward Deployed Engineer take-home project.

Before writing or modifying code:

1. Read IMPLEMENTATION_SPEC.md in full.
2. Treat it as the authoritative source of truth.
3. Do not rely on memory from previous sessions.
4. Identify the current implementation phase from Section 11.
5. Read that phase plus every detailed section it depends on.
6. Implement only the current phase unless explicitly instructed otherwise.
7. Do not add anything listed under DO NOT BUILD.
8. Do not silently reinterpret or simplify an exact rule, threshold, example, demo row, normalization list, or escalation condition.

While implementing:

- Keep LLM inference separate from deterministic policy.
- AI proposes; application policy decides review.
- The confidence threshold is exactly 0.85.
- Structural incompatibility overrides AI confidence.
- Mapping-level ambiguity may block transformation.
- Record-level problems must not block unrelated records.
- Once escalated, the human owns final resolution.
- Required values must never be invented.
- Exact duplicate means all normalized target values match.
- Conflicting duplicate values require human review.
- Reconciled records must preserve references to all contributing source rows.
- Successful API records must not be retried.
- Do not log full employee payloads by default.

At the end of the current phase:

1. Stop.
2. Run the phase's exact checkpoint examples from IMPLEMENTATION_SPEC.md.
3. Run relevant tests if they exist.
4. Compare actual behavior to the specification.
5. Fix any mismatch before continuing.
6. Summarize:
   - files changed
   - behavior implemented
   - verification performed
   - remaining issues
7. Create/prepare one meaningful Git commit for the verified phase.
8. Do not begin the next phase until the current phase is verified.

If the specification is ambiguous or two requirements genuinely conflict:

STOP AND ASK.

Do not guess a product decision.

If Section 5 and Section 2.1 appear to conflict, Section 2.1 wins unless the user explicitly says otherwise.

Your goal is not maximum feature count.
Your goal is a small, reliable prototype that visibly demonstrates:
- autonomous multi-file migration
- AI semantic mapping
- deterministic safeguards around AI
- a defensible escalation boundary
- human-in-the-loop resolution
- mock target integration
- retry/rollback
- auditability
- source traceability.
```

---

# 14. Definition of Done

Tier 1 is complete only when the following flow works locally:

```text
Upload 3 CSV/XLSX demo files
↓
Analyze source columns
↓
Generate mappings
↓
Show confidence + reason
↓
Apply confidence 0.85 policy
↓
Override bad high-confidence mapping via compatibility policy
↓
Resolve ambiguous mapping/date format
↓
Normalize strings/emails/nulls/numbers/booleans/dates
↓
Auto-dedupe E001
↓
Verify final E001 retains BOTH source-row references
↓
Escalate E002 duplicate conflict
↓
Resolve E002 field-by-field
↓
Verify final E002 retains BOTH source-row references
↓
Escalate invalid/missing required record
↓
Correct or exclude it
↓
Push ready records
↓
E009 fails with HTTP 500
↓
Retry E009
↓
E009 succeeds with HTTP 201
↓
Rollback action works
↓
Audit table explains what happened
```

Then complete:

```text
README
Git history
one-page write-up
demo recording
```

Only after that may Tier 2 or deployment work begin.

This now covers all three issues: lineage is a hard invariant, §2.1 explicitly wins if duplicate sections ever diverge, and Cursor gets a separate operating discipline it should follow phase-by-phase rather than reading the spec once and drifting.


The reference ui for Streamlit is in folder - /data/Work/Assignments/DarwinBox/stitch_data_migration_studio_ui
So: keep the UI as-is for visual reference, but add a note to Cursor that all counts, filenames, row numbers, lineage, statuses, and mapping values shown in Stitch are illustrative and must come from runtime state. The only actual unresolved product decision is the Full Name split.