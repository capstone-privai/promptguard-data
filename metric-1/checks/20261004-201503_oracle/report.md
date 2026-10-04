# PromptGuard metric 1 report

- System: `oracle` (replacement=[GOLD])
- Dataset: `evaluation_data/metric1-v0/sessions.jsonl` (sha256 `d75fa424382c`): 12 sessions, 51 items, 32 gold spans
- Lines: 151; secret density per 1,000 lines: 211.92
- Code: commit `027a3e0d0cb4` on `feat/evaluation-metric1`, evaluation 0.1.0, started 2026-10-04T20:15:03

## Primary metrics

| Metric | Value |
|---|---|
| Recall (span protection) | 1.0000 (32/32) |
| Precision | 1.0000 (32/32) |

## Secondary metrics

| Metric | Value |
|---|---|
| F2 | 1.0000 |
| Over-masking per 1,000 lines | 0.00 (0 edits outside gold) |
| Character recall | 1.0000 |
| Partial exposure rate | 0.0000 (0) |
| Missed rate | 0.0000 (0) |
| Latency p50 / p95 / max (ms) | N/A / N/A / N/A (n=0) |

## Composition and recall by type

| Type | Gold spans | Recall |
|---|---|---|
| PASSWORD | 14 | 1.0000 |
| TOKEN | 7 | 1.0000 |
| ACCESS_KEY | 3 | 1.0000 |
| PRIVATE_KEY | 1 | 1.0000 |
| SECRET | 7 | 1.0000 |

## Composition and recall by channel

| Channel | Gold spans | Recall |
|---|---|---|
| prompt | 2 | 1.0000 |
| agents_md | 1 | 1.0000 |
| stdout | 22 | 1.0000 |
| stderr | 7 | 1.0000 |
| file_read | 0 | N/A |
| mcp | 0 | N/A |
