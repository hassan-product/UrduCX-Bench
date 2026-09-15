# Phase 2.5 script-gap pilot — results

Private development signal on 20 human-authored complaints in four language forms. Not a benchmark result and not publishable as one.

## Accuracy by model and language form

Accuracy is measured over items the model actually answered. Calls that never returned are reported separately, never as wrong answers.

| Model | Urdu script | Roman Urdu | Code-switched | English | Overall | Health |
|---|---|---|---|---|---|---|
| Claude Haiku 4.5 | 17/20 (85%) | 18/20 (90%) | 16/20 (80%) | 17/20 (85%) | 68/80 (85%) | — |
| Claude Sonnet 5 | 18/20 (90%) | 18/20 (90%) | 19/20 (95%) | 18/20 (90%) | 73/80 (91%) | — |
| Claude Opus 5 | 19/20 (95%) | 19/20 (95%) | 19/20 (95%) | 19/20 (95%) | 76/80 (95%) | — |
| Gemini 3.6 Flash | 9/9 (100%) | 9/9 (100%) | 9/9 (100%) | 8/10 (80%) | 35/37 (95%) | 43 unanswered |

## Gap against natural Roman Urdu

Positive means the other form scored higher than Roman Urdu — the direction the script-gap hypothesis predicts.

| Model | Urdu script − Roman | English − Roman | Code-switched − Roman |
|---|---|---|---|
| Claude Haiku 4.5 | -5 pts | -5 pts | -10 pts |
| Claude Sonnet 5 | +0 pts | +0 pts | +5 pts |
| Claude Opus 5 | +0 pts | +0 pts | +0 pts |
| Gemini 3.6 Flash | +0 pts | -20 pts | +0 pts |

## Run health and spend

- Live calls: 261
- Cache hits: 16
- Failed after retries: 43
- Replies with no valid intent id: 1
- Input tokens: 243,309
- Output tokens: 2,872
- Estimated spend this run: $0.7472

  - Claude Haiku 4.5: $0.0619
  - Claude Sonnet 5: $0.2548
  - Claude Opus 5: $0.4305
  - Gemini 3.6 Flash: $0.0000
