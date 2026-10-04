# PromptGuard metric 1 report

- System: `credsweeper` (ml=False, credsweeper_version=1.18.5, channels=['stdout', 'stderr'])
- Dataset: `evaluation_data/metric1-v0/sessions.jsonl` (sha256 `d75fa424382c`): 12 sessions, 51 items, 32 gold spans
- Lines: 151; secret density per 1,000 lines: 211.92
- Code: commit `027a3e0d0cb4` on `feat/evaluation-metric1`, evaluation 0.1.0, started 2026-10-04T20:15:38

## Primary metrics

| Metric | Value |
|---|---|
| Recall (span protection) | 0.6562 (21/32) |
| Precision | 0.6765 (23/34) |

## Secondary metrics

| Metric | Value |
|---|---|
| F2 | 0.6602 |
| Over-masking per 1,000 lines | 72.85 (11 edits outside gold) |
| Character recall | 0.6782 |
| Partial exposure rate | 0.0625 (2) |
| Missed rate | 0.2812 (9) |
| Latency p50 / p95 / max (ms) | 0.16 / 0.50 / 0.99 (n=36) |

## Composition and recall by type

| Type | Gold spans | Recall |
|---|---|---|
| PASSWORD | 14 | 0.6429 |
| TOKEN | 7 | 0.5714 |
| ACCESS_KEY | 3 | 1.0000 |
| PRIVATE_KEY | 1 | 1.0000 |
| SECRET | 7 | 0.5714 |

## Composition and recall by channel

| Channel | Gold spans | Recall |
|---|---|---|
| prompt | 2 | 0.0000 |
| agents_md | 1 | 0.0000 |
| stdout | 22 | 0.6818 |
| stderr | 7 | 0.8571 |
| file_read | 0 | N/A |
| mcp | 0 | N/A |
