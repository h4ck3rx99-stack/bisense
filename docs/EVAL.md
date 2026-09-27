# Evaluation

Generated 2026-09-27T18:19:34+00:00 by `npm run eval` (full pipeline with LLM).

- Dataset mode: **demo** (tiers B+C); corpus: {'standards_full_text': 4, 'guidance': 30, 'catalogue': 735, 'chunks': 670, 'clauses': 590, 'requirements': 351}
- Questions: 62 (50 answerable incl. exact/compare/follow-up, 12 unanswerable, 9 Hindi/Kannada); source: `server/eval/questions.yaml`
- Embedding model: `BAAI/bge-small-en-v1.5`; reranker: `Xenova/ms-marco-MiniLM-L-6-v2` (enabled: True); LLM: `openai/gpt-oss-120b`

## Results

| Metric | Value | Target |
|---|---|---|
| recall_at_5 | 0.980 | 0.85 |
| mrr_at_10 | 0.900 |  |
| exact_number_hit_at_1 | 1.000 | 1.0 |
| retrieval_p50_ms | 970.100 |  |
| retrieval_p95_ms | 2154.700 |  |
| refusal_accuracy | 1.000 | 0.9 |
| false_refusal_rate | 0.020 | 0.1 |
| drop_rate | 0.015 |  |
| fact_hit_rate | 0.957 |  |
| answer_p50_ms | 5269.500 |  |
| answer_p95_ms | 14411.000 |  |
| tokens_per_answer_median | 2435.500 |  |

Definitions: recall@5 = share of answerable questions with an expected source (document + clause) among the first 5 evidence passages; MRR@10 = mean reciprocal rank of the first expected passage; exact-number hit@1 = the named standard is the first standard listed; refusal accuracy = share of unanswerable questions answered with "not in the indexed sources"; false-refusal rate = share of answerable questions refused; drop rate = share of drafted statements removed by the validator; fact hit = the expected verbatim fragment appears in the answer.

## Evidence gate calibration

Cross-encoder score of the best passage, answerable questions: [-3.02, 1.1, 1.44, 1.57, 1.85, 3.03, 3.72, 4.7, 5.42, 5.43, 5.74, 5.84, 6.28, 6.3, 6.49, 6.58, 6.65, 6.65, 6.92, 7.02, 7.04, 7.06, 7.13, 7.3, 7.3, 7.34, 7.37, 7.5, 7.59, 7.97, 8.32, 8.55, 8.56, 8.63, 8.9, 9.39, 9.63, 9.85, 10.63]

Unanswerable questions: [-9.91, -8.26, -6.22, -5.71, -5.27, -2.45, -0.98, -0.65, -0.57, -0.06, 0.08, 1.18]

Recommended `GATE_RERANK_MIN` = **1.44** (gate alone: refusal accuracy 1.0, false refusals 0.051). Method: sweep every observed score and pick the threshold that maximises refusals of unanswerable questions while penalising false refusals above 10%. Questions naming a standard explicitly bypass the gate.

## Configuration comparison (retrieval only)

| Configuration | recall@5 | MRR@10 | exact hit@1 | p50 ms | p95 ms |
|---|---|---|---|---|---|
| hybrid + reranker (BAAI/bge-small-en-v1.5) | 1.000 | 0.908 | 1.000 | 600.300 | 1539.000 |
| hybrid, no reranker (BAAI/bge-small-en-v1.5) | 0.880 | 0.803 | 1.000 | 2.300 | 1641.000 |

## Without an LLM (extractive mode, run 2026-09-27T18:12:03+00:00)

| Metric | Value |
|---|---|
| recall_at_5 | 1.000 |
| mrr_at_10 | 0.928 |
| exact_number_hit_at_1 | 1.000 |
| retrieval_p50_ms | 712.900 |
| retrieval_p95_ms | 1164.300 |
| refusal_accuracy | 0.833 |
| false_refusal_rate | 0.020 |

In this mode refusals come only from the stricter evidence gate (`GATE_RERANK_MIN_NO_LLM`); answers are verbatim passages.

## Per-question results

| id | type | lang | rank | top standard | top rerank | answer | mode | fact | ms |
|---|---|---|---|---|---|---|---|---|---|
| a01 | answerable | en | 4 | demo-101-2026 | 6.295 | requirements | live | yes | 2623.4 |
| a02 | answerable | en | 3 | demo-101-2026 | 7.298 | definition | live | yes | 3047.6 |
| a03 | answerable | en | 1 | demo-101-2026 | 5.843 | answer | live | yes | 2530.3 |
| a04 | answerable | en | 1 | demo-101-2026 | 7.496 | answer | live | yes | 3215.4 |
| a05 | answerable | en | 1 | demo-102-2026 | 8.897 | answer | extractive | yes | 13398.1 |
| a06 | answerable | en | 1 | demo-201-2026 | 7.588 | definition | live | yes | 4799.8 |
| a07 | answerable | en | 1 | demo-201-2026 | 1.096 | summary | live | no | 5767.0 |
| a08 | answerable | en | 1 | demo-201-2026 | 7.133 | definition | live | yes | 5800.2 |
| a09 | answerable | en | 1 | demo-301-2026 | 1.442 | definition | live | yes | 5958.7 |
| a10 | answerable | en | 1 | demo-301-2026 | 4.696 | insufficient_evidence | live |  | 5269.5 |
| a11 | answerable | en | 1 | demo-301-2026 | 6.280 | requirements | live | yes | 10705.8 |
| a12 | answerable | en | 1 | demo-301-2026 | 6.654 | definition | live | yes | 6117.7 |
| a13 | answerable | en | 1 | bis-hallmarking-faq | 10.633 | definition | live | yes | 5847.0 |
| a14 | answerable | en | 1 | bis-hallmarking-faq | 8.324 | answer | live | yes | 6294.4 |
| a15 | answerable | en | 1 | bis-hallmarking-faq | 7.342 | answer | live | yes | 2587.4 |
| a16 | answerable | en | 1 | bis-hallmarking-consumer-faq | 9.630 | answer | live |  | 1563.0 |
| a17 | answerable | en | 1 | bis-hallmarking-faq | 7.365 | answer | live | yes | 1963.9 |
| a18 | answerable | en | 1 | bis-product-certification-faq | 9.854 | answer | live | yes | 2190.6 |
| a19 | answerable | en | 1 | bis-product-certification-faq | 9.385 | summary | live |  | 8868.5 |
| a20 | answerable | en | 1 | bis-product-certification-faq | 6.924 | requirements | live | yes | 9036.8 |
| a21 | answerable | en | 1 | bis-product-certification-faq | 7.303 | standards_list | cached |  | 363.6 |
| a22 | answerable | en | 1 | bis-lab-faq | 8.629 | standards_list | live |  | 5628.7 |
| a23 | answerable | en | 1 | bis-scheme-x-faq | -3.020 | standards_list | live |  | 6761.4 |
| a24 | answerable | en | 1 | bis-fmcs-faq | 7.063 | standards_list | live | yes | 5955.6 |
| a25 | answerable | en | 1 | bis-scheme-x-faq | 6.648 | answer | live |  | 2236.5 |
| a26 | answerable | en | 1 | bis-scheme-x-faq | 7.973 | answer | live |  | 7097.6 |
| a27 | answerable | en | 1 | is-4151-2015 | 5.735 | standards_list | cached | yes | 360.4 |
| a28 | answerable | en | 2 | demo-101-2026 | 3.718 | standards_list | cached | yes | 596.3 |
| a29 | answerable | en | 1 | qco-helmet-two-wheeler-2020 | 8.550 | answer | extractive | yes | 9697.7 |
| a30 | answerable | en | 1 | bis-guidelines-cluster-lab-msme | 8.563 | summary | live |  | 8169.0 |
| m01 | answerable | hi | 1 | demo-101-2026 | 5.417 | standards_list | live |  | 10749.1 |
| m02 | answerable | hi | 10 | bis-hallmarking-consumer-faq | 3.029 | answer | live |  | 5293.1 |
| m03 | answerable | hi | 2 | bis-scheme-x-faq | 1.847 | answer | live |  | 23303.7 |
| m04 | answerable | hi | 1 | demo-101-2026 | 7.040 | requirements | live |  | 14411.0 |
| m05 | answerable | kn | 1 | bis-hallmarking-faq | 6.491 | standards_list | cached |  | 1485.2 |
| m06 | answerable | kn | 1 | demo-101-2026 | 5.427 | standards_list | live |  | 4114.8 |
| m07 | answerable | kn | 1 | bis-lab-faq | 6.583 | standards_list | live |  | 16366.0 |
| m08 | answerable | kn | 1 | is-4151-2015 | 7.020 | answer | extractive |  | 7116.6 |
| e01 | exact | en | 1 | is-4151-2015 | 3.220 | standards_list | live |  | 5909.8 |
| e02 | exact | en | 1 | is-1786-2008 | -10.893 | summary | live |  | 7052.0 |
| e03 | exact | en | 1 | demo-101-2026 | 7.892 | answer | live | yes | 1607.1 |
| e04 | exact | en | 1 | demo-201-2026 | 4.265 | answer | live | yes | 1505.1 |
| e05 | exact | en | 1 | is-14543 | 4.460 | summary | live |  | 2305.3 |
| e06 | exact | en | 1 | demo-301-2026 | 6.790 | summary | live |  | 2385.1 |
| c01 | compare | en | 1 | demo-102-2026 | 5.761 | comparison | live |  | 3371.6 |
| c02 | compare | en | 3 | demo-102-2026 | 5.766 | requirements | live |  | 6770.2 |
| c03 | compare | en | 2 | demo-102-2026 | 1.567 | comparison | live |  | 6731.5 |
| f01 | followup | en | 2 | demo-101-2026 | 8.509 | requirements | cached |  | 640.1 |
| f02 | followup | en | 1 | demo-201-2026 | 8.753 | requirements | live |  | 4171.6 |
| f03 | followup | en | 1 | demo-301-2026 | 7.454 | summary | live |  | 7215.1 |
| u01 | unanswerable | en | — | demo-201-2026 | -8.257 | insufficient_evidence | none |  | 464.5 |
| u02 | unanswerable | en | — | demo-101-2026 | -0.569 | insufficient_evidence | live |  | 4155.2 |
| u03 | unanswerable | en | — | demo-301-2026 | 0.077 | insufficient_evidence | live |  | 3941.2 |
| u04 | unanswerable | en | — | demo-101-2026 | -0.064 | insufficient_evidence | live |  | 1523.6 |
| u05 | unanswerable | en | — | bis-hallmarking-consumer-faq | -2.448 | insufficient_evidence | live |  | 2297.2 |
| u06 | unanswerable | en | — | bis-guidelines-grant-of-licence-2026 | -5.714 | insufficient_evidence | none |  | 575.7 |
| u07 | unanswerable | en | — | demo-201-2026 | -5.272 | insufficient_evidence | none |  | 551.8 |
| u08 | unanswerable | en | — | is-4151-2015 | 1.183 | insufficient_evidence | live |  | 1706.6 |
| u09 | unanswerable | en | — | demo-102-2026 | -9.914 | insufficient_evidence | none |  | 534.9 |
| u10 | unanswerable | en | — | bis-guidelines-grant-of-licence-2026 | -0.982 | insufficient_evidence | live |  | 4526.1 |
| u11 | unanswerable | en | — | demo-201-2026 | -0.655 | insufficient_evidence | live |  | 4125.0 |
| u12 | unanswerable | hi | — | demo-201-2026 | -6.219 | insufficient_evidence | none |  | 3431.6 |

## Notes

- All answerable questions were auto-drafted from ingested clauses (`origin: auto_drafted`) and should be spot-checked by the team.
- The Tier C demo documents are synthetic; numbers on them measure the pipeline, not coverage of real Indian Standards.
- Latency is measured on the build laptop (CPU embeddings/reranker; local LLM on an 8 GB laptop GPU when used).
