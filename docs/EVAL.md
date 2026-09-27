# Evaluation

Generated 2026-09-27T18:01:31+00:00 by `npm run eval` (full pipeline with LLM).

- Dataset mode: **demo** (tiers B+C); corpus: {'standards_full_text': 4, 'guidance': 30, 'catalogue': 735, 'chunks': 670, 'clauses': 590, 'requirements': 351}
- Questions: 62 (50 answerable incl. exact/compare/follow-up, 12 unanswerable, 9 Hindi/Kannada); source: `server/eval/questions.yaml`
- Embedding model: `BAAI/bge-small-en-v1.5`; reranker: `Xenova/ms-marco-MiniLM-L-6-v2` (enabled: True); LLM: `openai/gpt-oss-120b`

## Results

| Metric | Value | Target |
|---|---|---|
| recall_at_5 | 0.980 | 0.85 |
| mrr_at_10 | 0.900 |  |
| exact_number_hit_at_1 | 1.000 | 1.0 |
| retrieval_p50_ms | 941.200 |  |
| retrieval_p95_ms | 2090.000 |  |
| refusal_accuracy | 1.000 | 0.9 |
| false_refusal_rate | 0.080 | 0.1 |
| drop_rate | 0.000 |  |
| fact_hit_rate | 0.864 |  |
| answer_p50_ms | 5789.700 |  |
| answer_p95_ms | 11685.800 |  |
| tokens_per_answer_median | 2488 |  |

Definitions: recall@5 = share of answerable questions with an expected source (document + clause) among the first 5 evidence passages; MRR@10 = mean reciprocal rank of the first expected passage; exact-number hit@1 = the named standard is the first standard listed; refusal accuracy = share of unanswerable questions answered with "not in the indexed sources"; false-refusal rate = share of answerable questions refused; drop rate = share of drafted statements removed by the validator; fact hit = the expected verbatim fragment appears in the answer.

## Evidence gate calibration

Cross-encoder score of the best passage, answerable questions: [-3.02, 1.1, 1.44, 1.57, 3.03, 3.72, 3.78, 4.37, 4.7, 5.42, 5.74, 5.84, 6.02, 6.28, 6.3, 6.58, 6.65, 6.65, 6.92, 7.02, 7.04, 7.06, 7.13, 7.3, 7.3, 7.34, 7.37, 7.45, 7.5, 7.59, 7.97, 8.32, 8.51, 8.55, 8.56, 8.63, 8.75, 8.9, 9.39, 9.63, 9.85, 10.63]

Unanswerable questions: [-9.91, -8.26, -6.22, -5.71, -5.27, -2.45, -0.98, -0.65, -0.57, -0.06, 0.08, 1.18]

Recommended `GATE_RERANK_MIN` = **1.44** (gate alone: refusal accuracy 1.0, false refusals 0.048). Method: sweep every observed score and pick the threshold that maximises refusals of unanswerable questions while penalising false refusals above 10%. Questions naming a standard explicitly bypass the gate.

## Per-question results

| id | type | lang | rank | top standard | top rerank | answer | mode | fact | ms |
|---|---|---|---|---|---|---|---|---|---|
| a01 | answerable | en | 4 | demo-101-2026 | 6.295 | requirements | live | yes | 2004.8 |
| a02 | answerable | en | 3 | demo-101-2026 | 7.298 | definition | live | yes | 1426.5 |
| a03 | answerable | en | 1 | demo-101-2026 | 5.843 | answer | live | yes | 1330.2 |
| a04 | answerable | en | 1 | demo-101-2026 | 7.496 | requirements | live | yes | 6175.1 |
| a05 | answerable | en | 1 | demo-102-2026 | 8.897 | answer | extractive | yes | 3340.8 |
| a06 | answerable | en | 1 | demo-201-2026 | 7.588 | definition | live | yes | 4863.6 |
| a07 | answerable | en | 1 | demo-201-2026 | 1.096 | summary | live | no | 5687.7 |
| a08 | answerable | en | 1 | demo-201-2026 | 7.133 | definition | live | yes | 5789.7 |
| a09 | answerable | en | 1 | demo-301-2026 | 1.442 | insufficient_evidence | live |  | 4167.9 |
| a10 | answerable | en | 1 | demo-301-2026 | 4.696 | insufficient_evidence | live |  | 4641.0 |
| a11 | answerable | en | 1 | demo-301-2026 | 6.280 | requirements | live | yes | 1467.1 |
| a12 | answerable | en | 1 | demo-301-2026 | 6.654 | definition | live | yes | 1280.1 |
| a13 | answerable | en | 1 | bis-hallmarking-faq | 10.633 | definition | live | yes | 6282.2 |
| a14 | answerable | en | 1 | bis-hallmarking-faq | 8.324 | answer | live | yes | 5397.9 |
| a15 | answerable | en | 1 | bis-hallmarking-faq | 7.342 | standards_list | live | yes | 6938.2 |
| a16 | answerable | en | 1 | bis-hallmarking-consumer-faq | 9.630 | answer | extractive |  | 3640.6 |
| a17 | answerable | en | 1 | bis-hallmarking-faq | 7.365 | standards_list | live | yes | 5571.3 |
| a18 | answerable | en | 1 | bis-product-certification-faq | 9.854 | answer | live | yes | 7299.9 |
| a19 | answerable | en | 1 | bis-product-certification-faq | 9.385 | answer | live |  | 1663.3 |
| a20 | answerable | en | 1 | bis-product-certification-faq | 6.924 | requirements | live | yes | 11685.8 |
| a21 | answerable | en | 1 | bis-product-certification-faq | 7.303 | standards_list | live |  | 6446.7 |
| a22 | answerable | en | 1 | bis-lab-faq | 8.629 | standards_list | live |  | 5269.6 |
| a23 | answerable | en | 1 | bis-scheme-x-faq | -3.020 | standards_list | live |  | 6391.1 |
| a24 | answerable | en | 1 | bis-fmcs-faq | 7.063 | requirements | live | yes | 5847.3 |
| a25 | answerable | en | 1 | bis-scheme-x-faq | 6.648 | answer | live |  | 1388.4 |
| a26 | answerable | en | 1 | bis-scheme-x-faq | 7.973 | answer | live |  | 6758.2 |
| a27 | answerable | en | 1 | is-4151-2015 | 5.735 | standards_list | live | yes | 6383.9 |
| a28 | answerable | en | 2 | demo-101-2026 | 3.718 | standards_list | live | yes | 7412.7 |
| a29 | answerable | en | 1 | qco-helmet-two-wheeler-2020 | 8.550 | answer | extractive | yes | 9389.7 |
| a30 | answerable | en | 1 | bis-guidelines-cluster-lab-msme | 8.563 | summary | live |  | 7653.2 |
| m01 | answerable | hi | 1 | demo-101-2026 | 5.417 | standards_list | live |  | 4599.8 |
| m02 | answerable | hi | 10 | bis-hallmarking-consumer-faq | 3.029 | insufficient_evidence | live |  | 2063.5 |
| m03 | answerable | hi | 2 | is-4151-2015 | 4.371 | insufficient_evidence | live |  | 6708.6 |
| m04 | answerable | hi | 1 | demo-101-2026 | 7.040 | standards_list | live |  | 15023.8 |
| m05 | answerable | kn | 1 | bis-hallmarking-faq | 6.017 | answer | live |  | 13522.1 |
| m06 | answerable | kn | 1 | demo-101-2026 | 3.783 | standards_list | live |  | 5654.2 |
| m07 | answerable | kn | 1 | bis-lab-faq | 6.583 | standards_list | live |  | 31882.1 |
| m08 | answerable | kn | 1 | is-4151-2015 | 7.020 | answer | extractive |  | 8358.8 |
| e01 | exact | en | 1 | is-4151-2015 | 3.220 | standards_list | live |  | 6608.4 |
| e02 | exact | en | 1 | is-1786-2008 | -10.893 | summary | live |  | 6125.7 |
| e03 | exact | en | 1 | demo-101-2026 | 7.892 | requirements | live | no | 9111.5 |
| e04 | exact | en | 1 | demo-201-2026 | 4.265 | standards_list | live | no | 9773.9 |
| e05 | exact | en | 1 | is-14543 | 4.460 | summary | live |  | 2130.3 |
| e06 | exact | en | 1 | demo-301-2026 | 6.790 | answer | live |  | 1850.6 |
| c01 | compare | en | 1 | demo-102-2026 | 5.761 | standards_list | live |  | 6448.0 |
| c02 | compare | en | 3 | demo-102-2026 | 5.766 | answer | extractive |  | 4544.1 |
| c03 | compare | en | 2 | demo-102-2026 | 1.567 | comparison | live |  | 6170.8 |
| f01 | followup | en | 2 | demo-101-2026 | 8.509 | requirements | live |  | 7611.1 |
| f02 | followup | en | 1 | demo-201-2026 | 8.753 | requirements | live |  | 3981.8 |
| f03 | followup | en | 1 | demo-301-2026 | 7.454 | summary | live |  | 7205.1 |
| u01 | unanswerable | en | — | demo-201-2026 | -8.257 | insufficient_evidence | none |  | 3.7 |
| u02 | unanswerable | en | — | demo-101-2026 | -0.569 | insufficient_evidence | live |  | 1068.0 |
| u03 | unanswerable | en | — | demo-301-2026 | 0.077 | insufficient_evidence | live |  | 1295.4 |
| u04 | unanswerable | en | — | demo-101-2026 | -0.064 | insufficient_evidence | live |  | 7811.9 |
| u05 | unanswerable | en | — | bis-hallmarking-consumer-faq | -2.448 | insufficient_evidence | live |  | 3946.9 |
| u06 | unanswerable | en | — | bis-guidelines-grant-of-licence-2026 | -5.714 | insufficient_evidence | none |  | 1.6 |
| u07 | unanswerable | en | — | demo-201-2026 | -5.272 | insufficient_evidence | none |  | 0.7 |
| u08 | unanswerable | en | — | is-4151-2015 | 1.183 | insufficient_evidence | live |  | 3779.7 |
| u09 | unanswerable | en | — | demo-102-2026 | -9.914 | insufficient_evidence | none |  | 1.6 |
| u10 | unanswerable | en | — | bis-guidelines-grant-of-licence-2026 | -0.982 | insufficient_evidence | live |  | 4112.6 |
| u11 | unanswerable | en | — | demo-201-2026 | -0.655 | insufficient_evidence | live |  | 3930.4 |
| u12 | unanswerable | hi | — | demo-201-2026 | -6.219 | insufficient_evidence | none |  | 4511.9 |

## Notes

- All answerable questions were auto-drafted from ingested clauses (`origin: auto_drafted`) and should be spot-checked by the team.
- The Tier C demo documents are synthetic; numbers on them measure the pipeline, not coverage of real Indian Standards.
- Latency is measured on the build laptop (CPU embeddings/reranker; local LLM on an 8 GB laptop GPU when used).
