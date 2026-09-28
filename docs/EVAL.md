# Evaluation

Generated 2026-09-28T13:47:36+00:00 by `npm run eval` (full pipeline with LLM).

- Dataset mode: **sample** (tiers A+B); corpus: {'standards_full_text': 16, 'standards_total': 741, 'standards_with_full_text': 0, 'standards_with_manual': 12, 'sample_documents': 4, 'guidance': 30, 'catalogue': 729, 'chunks': 931, 'clauses': 835, 'requirements': 557}
- Questions: 63 (51 answerable incl. exact/compare/follow-up, 12 unanswerable, 9 Hindi/Kannada); source: `server/eval/questions.yaml`
- Embedding model: `BAAI/bge-small-en-v1.5`; reranker: `Xenova/ms-marco-MiniLM-L-6-v2` (enabled: True); LLM: `openai/gpt-oss-120b`

## Results

| Metric | Value | Target |
|---|---|---|
| recall_at_5 | 0.980 | 0.85 |
| mrr_at_10 | 0.863 |  |
| exact_number_hit_at_1 | 1.000 | 1.0 |
| retrieval_p50_ms | 572.500 |  |
| retrieval_p95_ms | 1556.400 |  |
| refusal_accuracy | 0.917 | 0.9 |
| false_refusal_rate | 0.020 | 0.1 |
| drop_rate | 0.017 |  |
| fact_hit_rate | 1.000 |  |
| answer_p50_ms | 1535.300 |  |
| answer_p95_ms | 4213.200 |  |
| tokens_per_answer_median | 2937.000 |  |

Definitions: recall@5 = share of answerable questions with an expected source (document + clause) among the first 5 evidence passages; MRR@10 = mean reciprocal rank of the first expected passage; exact-number hit@1 = the named standard is the first standard listed; refusal accuracy = share of unanswerable questions answered with "not in the indexed sources"; false-refusal rate = share of answerable questions refused; drop rate = share of drafted statements removed by the validator; fact hit = the expected verbatim fragment appears in the answer.

## Evidence gate calibration

Cross-encoder score of the best passage, answerable questions: [-3.02, 1.1, 1.44, 1.48, 1.57, 2.67, 3.03, 4.54, 4.6, 4.7, 4.72, 5.84, 6.02, 6.13, 6.28, 6.3, 6.58, 6.65, 6.65, 6.92, 7.02, 7.04, 7.06, 7.13, 7.3, 7.3, 7.34, 7.37, 7.5, 7.59, 7.97, 8.32, 8.55, 8.56, 8.63, 8.9, 9.39, 9.63, 9.85, 10.63]

Unanswerable questions: [-9.91, -8.26, -6.22, -5.08, -4.96, -2.45, -0.98, -0.65, -0.32, -0.06, 0.08, 1.18]

Recommended `GATE_RERANK_MIN` = **1.44** (gate alone: refusal accuracy 1.0, false refusals 0.05). Method: sweep every observed score and pick the threshold that maximises refusals of unanswerable questions while penalising false refusals above 10%. Questions naming a standard explicitly bypass the gate.

## Without an LLM (extractive mode, run 2026-09-28T07:05:25+00:00)

| Metric | Value |
|---|---|
| recall_at_5 | 1.000 |
| mrr_at_10 | 0.890 |
| exact_number_hit_at_1 | 1.000 |
| retrieval_p50_ms | 636.600 |
| retrieval_p95_ms | 915.000 |
| refusal_accuracy | 0.833 |
| false_refusal_rate | 0.020 |

In this mode refusals come only from the stricter evidence gate (`GATE_RERANK_MIN_NO_LLM`); answers are verbatim passages.

## Per-question results

| id | type | lang | rank | top standard | top rerank | answer | mode | fact | ms |
|---|---|---|---|---|---|---|---|---|---|
| a01 | answerable | en | 5 | demo-101-2026 | 6.295 | requirements | live | yes | 3662.7 |
| a02 | answerable | en | 3 | demo-101-2026 | 7.298 | definition | live | yes | 1533.1 |
| a03 | answerable | en | 1 | demo-101-2026 | 5.843 | answer | live | yes | 3056.0 |
| a04 | answerable | en | 1 | demo-101-2026 | 7.496 | answer | live | yes | 2530.2 |
| a05 | answerable | en | 1 | demo-102-2026 | 8.897 | answer | live | yes | 2041.9 |
| a06 | answerable | en | 1 | demo-201-2026 | 7.588 | definition | live | yes | 1474.4 |
| a07 | answerable | en | 1 | demo-201-2026 | 1.096 | requirements | live | yes | 1485.3 |
| a08 | answerable | en | 1 | demo-201-2026 | 7.133 | answer | live | yes | 2031.8 |
| a09 | answerable | en | 1 | is-1786-2008 | 1.442 | definition | live | yes | 1519.9 |
| a10 | answerable | en | 1 | demo-301-2026 | 4.696 | definition | live | yes | 1351.4 |
| a11 | answerable | en | 1 | demo-301-2026 | 6.280 | requirements | live | yes | 1436.6 |
| a12 | answerable | en | 1 | demo-301-2026 | 6.654 | definition | live | yes | 1558.1 |
| a13 | answerable | en | 1 | bis-hallmarking-faq | 10.633 | definition | live | yes | 3611.4 |
| a14 | answerable | en | 1 | bis-hallmarking-faq | 8.324 | summary | live | yes | 1317.7 |
| a15 | answerable | en | 1 | bis-hallmarking-faq | 7.342 | answer | live | yes | 2218.6 |
| a16 | answerable | en | 1 | bis-hallmarking-consumer-faq | 9.630 | summary | live |  | 1164.6 |
| a17 | answerable | en | 1 | bis-hallmarking-faq | 7.365 | answer | live | yes | 2361.2 |
| a18 | answerable | en | 1 | bis-product-certification-faq | 9.854 | answer | live | yes | 1426.1 |
| a19 | answerable | en | 1 | bis-product-certification-faq | 9.385 | answer | live |  | 4414.2 |
| a20 | answerable | en | 1 | bis-product-certification-faq | 6.924 | requirements | live | yes | 1199.8 |
| a21 | answerable | en | 1 | bis-product-certification-faq | 7.303 | answer | live |  | 1317.4 |
| a22 | answerable | en | 1 | bis-lab-faq | 8.629 | requirements | live |  | 1193.7 |
| a23 | answerable | en | 1 | bis-hallmarking-consumer-faq | -3.020 | summary | live |  | 1713.7 |
| a24 | answerable | en | 1 | bis-fmcs-faq | 7.063 | requirements | live | yes | 1535.3 |
| a25 | answerable | en | 1 | bis-scheme-x-faq | 6.648 | requirements | live |  | 1690.8 |
| a26 | answerable | en | 1 | bis-scheme-x-faq | 7.973 | definition | live |  | 1613.7 |
| a27 | answerable | en | 2 | is-4151-2015 | 6.132 | summary | live | yes | 1397.9 |
| a28 | answerable | en | 2 | is-15410-2003 | 4.599 | standards_list | live | yes | 1160.6 |
| a29 | answerable | en | 1 | qco-helmet-two-wheeler-2020 | 8.550 | summary | live | yes | 1096.6 |
| a30 | answerable | en | 1 | bis-guidelines-cluster-lab-msme | 8.563 | requirements | live |  | 1483.7 |
| m01 | answerable | hi | 2 | is-15410-2003 | 4.543 | standards_list | live |  | 4129.2 |
| m02 | answerable | hi | 8 | bis-hallmarking-consumer-faq | 3.029 | answer | live |  | 3451.6 |
| m03 | answerable | hi | 2 | bis-scheme-x-faq | 1.477 | answer | extractive |  | 4039.8 |
| m04 | answerable | hi | 1 | demo-101-2026 | 7.040 | requirements | live |  | 4550.7 |
| m05 | answerable | kn | 1 | bis-hallmarking-faq | 6.017 | summary | live |  | 4782.9 |
| m06 | answerable | kn | 2 | is-15410-2003 | 4.723 | standards_list | live |  | 4213.2 |
| m07 | answerable | kn | 1 | bis-lab-faq | 6.583 | requirements | live |  | 3897.0 |
| m08 | answerable | kn | 1 | is-4151-2015 | 7.020 | summary | live |  | 3938.6 |
| j01 | answerable | en | 2 | is-6312-1994 | 2.672 | standards_list | live |  | 1188.8 |
| e01 | exact | en | 1 | is-4151-2015 | 6.955 | summary | live |  | 1514.8 |
| e02 | exact | en | 1 | is-1786-2008 | 6.309 | summary | live |  | 1488.8 |
| e03 | exact | en | 1 | demo-101-2026 | 7.892 | summary | live | yes | 1480.9 |
| e04 | exact | en | 1 | demo-201-2026 | 4.265 | summary | live | yes | 1896.2 |
| e05 | exact | en | 1 | is-14543 | 4.460 | standards_list | live |  | 1440.7 |
| e06 | exact | en | 1 | demo-301-2026 | 6.790 | summary | live |  | 1429.1 |
| c01 | compare | en | 1 | demo-102-2026 | 5.761 | comparison | live |  | 2310.3 |
| c02 | compare | en | 3 | demo-102-2026 | 5.766 | answer | extractive |  | 2714.8 |
| c03 | compare | en | 2 | is-15410-2003 | 1.567 | insufficient_evidence | live |  | 1787.5 |
| f01 | followup | en | 2 | demo-101-2026 | 8.509 | requirements | live |  | 3022.6 |
| f02 | followup | en | 1 | demo-201-2026 | 8.753 | requirements | live |  | 1137.8 |
| f03 | followup | en | 1 | demo-301-2026 | 7.454 | requirements | live |  | 1335.3 |
| u01 | unanswerable | en | — | bis-hallmarking-faq | -8.257 | insufficient_evidence | none |  | 8.4 |
| u02 | unanswerable | en | — | demo-101-2026 | -0.316 | insufficient_evidence | live |  | 1741.2 |
| u03 | unanswerable | en | — | is-1786-2008 | 0.077 | insufficient_evidence | live |  | 1160.2 |
| u04 | unanswerable | en | — | demo-102-2026 | -0.064 | insufficient_evidence | live |  | 2010.8 |
| u05 | unanswerable | en | — | bis-hallmarking-faq | -2.448 | insufficient_evidence | live |  | 1486.5 |
| u06 | unanswerable | en | — | bis-guidelines-grant-of-licence-2026 | -4.956 | insufficient_evidence | none |  | 4.3 |
| u07 | unanswerable | en | — | is-2925-1984 | -5.076 | insufficient_evidence | none |  | 1.7 |
| u08 | unanswerable | en | — | demo-201-2026 | 1.183 | requirements | live |  | 1379.9 |
| u09 | unanswerable | en | — | demo-101-2026 | -9.914 | insufficient_evidence | none |  | 2.5 |
| u10 | unanswerable | en | — | bis-guidelines-grant-of-licence-2026 | -0.982 | insufficient_evidence | live |  | 2778.6 |
| u11 | unanswerable | en | — | demo-201-2026 | -0.655 | insufficient_evidence | live |  | 1368.7 |
| u12 | unanswerable | hi | — | is-2925-1984 | -6.219 | insufficient_evidence | none |  | 2259.8 |

## Notes

- All answerable questions were auto-drafted from ingested clauses (`origin: auto_drafted`) and should be spot-checked by the team.
- The Tier C demo documents are synthetic; numbers on them measure the pipeline, not coverage of real Indian Standards.
- Latency is measured on the build laptop (CPU embeddings/reranker; local LLM on an 8 GB laptop GPU when used).
