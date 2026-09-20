# Ollama setup (Darwinbox migration agent)

## Locked model

| Setting | Value |
|---------|--------|
| **Model** | `llama3.2:3b` |
| **Runtime** | [Ollama](https://ollama.com) (local) |
| **Role** | Semantic **column → target field** proposals only |

The application — not the model — decides auto-accept vs human review (Phase 5+: confidence threshold, structural compatibility, validation). Deterministic **aliases** run before Ollama.

### Why this model

- Fits **4GB GPU** laptops (e.g. GTX 1650 Ti) without relying on an 8B model spilling to CPU.
- Good enough for short JSON mapping calls with `format: json`.
- Wrong or unsure outputs should surface as **review**, which matches the take-home escalation story.

### Optional upgrade

Consider `llama3.1:8b` or `qwen2.5:7b` only if the [evaluation checklist](#model-evaluation-checklist) shows repeated wrong high-confidence mappings or unstable JSON — not for benchmark chasing.

---

## One-time setup

```bash
# Install Ollama (Linux): https://ollama.com/download

ollama serve          # or use your OS service
ollama pull llama3.2:3b

cp .env.example .env   # OLLAMA_MODEL=llama3.2:3b
```

Verify:

```bash
.venv/bin/python scripts/verify_ollama.py
.venv/bin/python scripts/eval_mapping_samples.py
```

---

## What the app calls

- **Endpoint:** `POST {OLLAMA_BASE_URL}/api/generate`
- **Client:** `app/services/llm_client.py` (`LLMClient.infer_mapping`)
- **Trigger:** `POST /api/migrations/<id>/mappings/generate?include_semantic=true` or Streamlit **Generate column mappings** (Ollama per column, then deterministic alias fallback)

---

## Why the mapping cutoff is 0.80

`0.80` is a product-policy cutoff for this MVP, not a statistically calibrated probability of correctness. I chose it as a practical balance: lower-confidence semantic guesses should stop for review, while clear proposals should not make a consultant confirm every column. Crossing the cutoff only makes a proposal *eligible* for automatic acceptance. Structural compatibility, target-field collision checks and deterministic validation can still force review regardless of model confidence.

This value should be recalibrated against representative client mappings before production use. It is separate from the **75% evaluation pass rate** below: `0.80` applies to one mapping proposal, whereas `75%` decides whether the configured model passes the four-case MVP smoke test.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Connection refused on `:11434` | Start `ollama serve` |
| Model not found | `ollama pull llama3.2:3b` |
| Wrong model in app | Set `OLLAMA_MODEL` in `.env`, restart Flask |
| Slow first request | Model load; later calls are faster |
| Parse / `ollama_failed` | App continues; column stays unmapped or goes to review in Phase 5 |

---

## Model evaluation checklist

Run **after Phase 5** (mapping policy + review reasons) on the four demo files. Use results for your 1-page write-up (2–3 concrete auto vs escalated examples).

### A. Coverage

Unaliased columns (e.g. `Employee Name`, `Full Name`, `Date` on `employees_extra.csv`): how many get a non-null `target_field` from Ollama?

### B. Accuracy

For each proposal, mark **correct / wrong / unsure**. Obvious HR headers should not be nonsense.

### C. Calibration

When you would hesitate, does **confidence &lt; 0.80** so review triggers? High confidence on wrong maps is a signal to tune policy or consider a larger model.

### D. Stability

Run semantic mapping **3×** on the same migration. Targets should not flip wildly; the app must not crash on bad JSON.

### E. Latency

Full semantic pass on demo files: aim for **under ~2–3 minutes** on your machine for a smooth demo recording.

### Decision

| Outcome | Action |
|---------|--------|
| ≥ ~80% plausible targets on unaliased columns; safe failures | **Keep `llama3.2:3b`** |
| Frequent wrong **and** high confidence; or unstable JSON | Re-run `eval_mapping_samples.py`; consider upgrade or prompt tweak |
| Mistakes but **low confidence + clear review rule** | **Keep model** — boundary is working |

Automated golden-column check (before/after model change):

```bash
.venv/bin/python scripts/eval_mapping_samples.py
```

Default pass threshold: **≥ 75%** of golden cases (see script output). With the
current four-case set, this means at least **3 of 4** cases must pass. The MVP
allows one miss because semantic mappings are suggestions and low-confidence
results are sent for human review. Two or more misses would mean the configured
model or prompt is not dependable enough for the demo, so investigate before
Phase 5 lock-in.

This threshold is a pragmatic MVP smoke-test gate, not a production accuracy
target or service-level guarantee. Reassess it against a larger, representative
golden set before production use.
