# Evaluation

Generated 2026-09-27T18:41:55+00:00 by `npm run eval` (full pipeline with LLM).

- Dataset mode: **demo** (tiers B+C); corpus: {'standards_full_text': 4, 'guidance': 30, 'catalogue': 735, 'chunks': 670, 'clauses': 590, 'requirements': 351}
- Questions: 62 (50 answerable incl. exact/compare/follow-up, 12 unanswerable, 9 Hindi/Kannada); source: `server/eval/questions.yaml`
- Embedding model: `BAAI/bge-small-en-v1.5`; reranker: `Xenova/ms-marco-MiniLM-L-6-v2` (enabled: True); LLM: `openai/gpt-oss-120b`

## Results

| Metric | Value | Target |
|---|---|---|
| recall_at_5 | 1.000 | 0.85 |
| mrr_at_10 | 0.898 |  |
| exact_number_hit_at_1 | 1.000 | 1.0 |
| retrieval_p50_ms | 558.800 |  |
| retrieval_p95_ms | 3365.300 |  |
| refusal_accuracy | 1.000 | 0.9 |
| false_refusal_rate | 0.060 | 0.1 |
| drop_rate | 0.007 |  |
| fact_hit_rate | 0.909 |  |
| answer_p50_ms | 5567.000 |  |
| answer_p95_ms | 13402.000 |  |
| tokens_per_answer_median | 2421 |  |

Definitions: recall@5 = share of answerable questions with an expected source (document + clause) among the first 5 evidence passages; MRR@10 = mean reciprocal rank of the first expected passage; exact-number hit@1 = the named standard is the first standard listed; refusal accuracy = share of unanswerable questions answered with "not in the indexed sources"; false-refusal rate = share of answerable questions refused; drop rate = share of drafted statements removed by the validator; fact hit = the expected verbatim fragment appears in the answer.

## Evidence gate calibration

Cross-encoder score of the best passage, answerable questions: [-3.02, 1.1, 1.44, 1.57, 1.85, 3.72, 3.78, 4.7, 5.21, 5.41, 5.74, 5.84, 6.02, 6.04, 6.28, 6.3, 6.65, 6.65, 6.7, 6.92, 7.04, 7.06, 7.13, 7.3, 7.3, 7.34, 7.37, 7.5, 7.59, 7.97, 8.32, 8.55, 8.56, 8.63, 8.9, 9.39, 9.63, 9.85, 10.63]

Unanswerable questions: [-9.91, -8.26, -8.14, -5.71, -5.27, -2.45, -0.98, -0.65, -0.57, -0.06, 0.08, 1.18]

Recommended `GATE_RERANK_MIN` = **1.44** (gate alone: refusal accuracy 1.0, false refusals 0.051). Method: sweep every observed score and pick the threshold that maximises refusals of unanswerable questions while penalising false refusals above 10%. Questions naming a standard explicitly bypass the gate.

## Without an LLM (extractive mode, run 2026-09-27T18:34:38+00:00)

| Metric | Value |
|---|---|
| recall_at_5 | 1.000 |
| mrr_at_10 | 0.928 |
| exact_number_hit_at_1 | 1.000 |
| retrieval_p50_ms | 506.800 |
| retrieval_p95_ms | 715.000 |
| refusal_accuracy | 0.833 |
| false_refusal_rate | 0.020 |

In this mode refusals come only from the stricter evidence gate (`GATE_RERANK_MIN_NO_LLM`); answers are verbatim passages.

## Per-question results

| id | type | lang | rank | top standard | top rerank | answer | mode | fact | ms |
|---|---|---|---|---|---|---|---|---|---|
| a01 | answerable | en | 4 | demo-101-2026 | 6.295 | requirements | live | yes | 5422.4 |
| a02 | answerable | en | 3 | demo-101-2026 | 7.298 | definition | live | yes | 6178.7 |
| a03 | answerable | en | 1 | demo-101-2026 | 5.843 | answer | extractive | yes | 3620.8 |
| a04 | answerable | en | 1 | demo-101-2026 | 7.496 | requirements | live | yes | 5567.0 |
| a05 | answerable | en | 1 | demo-102-2026 | 8.897 | answer | extractive | yes | 3633.4 |
| a06 | answerable | en | 1 | demo-201-2026 | 7.588 | definition | live | yes | 4828.7 |
| a07 | answerable | en | 1 | demo-201-2026 | 1.096 | summary | live | no | 5407.3 |
| a08 | answerable | en | 1 | demo-201-2026 | 7.133 | definition | live | yes | 5426.8 |
| a09 | answerable | en | 1 | demo-301-2026 | 1.442 | insufficient_evidence | live |  | 4325.0 |
| a10 | answerable | en | 1 | demo-301-2026 | 4.696 | insufficient_evidence | live |  | 4355.3 |
| a11 | answerable | en | 1 | demo-301-2026 | 6.280 | requirements | live | yes | 5454.5 |
| a12 | answerable | en | 1 | demo-301-2026 | 6.654 | definition | live | yes | 5088.1 |
| a13 | answerable | en | 1 | bis-hallmarking-faq | 10.633 | definition | live | yes | 5396.2 |
| a14 | answerable | en | 1 | bis-hallmarking-faq | 8.324 | answer | live | yes | 6186.0 |
| a15 | answerable | en | 1 | bis-hallmarking-faq | 7.342 | standards_list | live | yes | 6909.4 |
| a16 | answerable | en | 1 | bis-hallmarking-consumer-faq | 9.630 | answer | extractive |  | 3578.1 |
| a17 | answerable | en | 1 | bis-hallmarking-faq | 7.365 | standards_list | live | yes | 5465.1 |
| a18 | answerable | en | 1 | bis-product-certification-faq | 9.854 | answer | live | yes | 4845.3 |
| a19 | answerable | en | 1 | bis-product-certification-faq | 9.385 | summary | live |  | 7255.7 |
| a20 | answerable | en | 1 | bis-product-certification-faq | 6.924 | requirements | live | yes | 5402.2 |
| a21 | answerable | en | 1 | bis-product-certification-faq | 7.303 | standards_list | live |  | 6721.2 |
| a22 | answerable | en | 1 | bis-lab-faq | 8.629 | standards_list | live |  | 5098.1 |
| a23 | answerable | en | 1 | bis-scheme-x-faq | -3.020 | standards_list | live |  | 5776.1 |
| a24 | answerable | en | 1 | bis-fmcs-faq | 7.063 | standards_list | live | no | 5362.0 |
| a25 | answerable | en | 1 | bis-scheme-x-faq | 6.648 | answer | extractive |  | 3936.3 |
| a26 | answerable | en | 1 | bis-scheme-x-faq | 7.973 | answer | live |  | 6399.8 |
| a27 | answerable | en | 1 | is-4151-2015 | 5.735 | standards_list | live | yes | 13402.0 |
| a28 | answerable | en | 2 | demo-101-2026 | 3.718 | standards_list | live | yes | 5977.4 |
| a29 | answerable | en | 1 | qco-helmet-two-wheeler-2020 | 8.550 | answer | extractive | yes | 8909.6 |
| a30 | answerable | en | 1 | bis-guidelines-cluster-lab-msme | 8.563 | standards_list | live |  | 6276.7 |
| m01 | answerable | hi | 1 | demo-101-2026 | 3.783 | standards_list | live |  | 8804.6 |
| m02 | answerable | hi | 2 | bis-hallmarking-faq | 6.035 | standards_list | live |  | 9674.6 |
| m03 | answerable | hi | 2 | bis-scheme-x-faq | 1.847 | standards_list | live |  | 15179.0 |
| m04 | answerable | hi | 1 | demo-101-2026 | 7.040 | requirements | live |  | 10420.1 |
| m05 | answerable | kn | 1 | bis-hallmarking-faq | 6.017 | standards_list | live |  | 11054.2 |
| m06 | answerable | kn | 1 | demo-101-2026 | 6.697 | standards_list | live |  | 9637.9 |
| m07 | answerable | kn | 1 | bis-lab-faq | 5.212 | standards_list | live |  | 9206.3 |
| m08 | answerable | kn | 2 | is-4151-2015 | 5.410 | answer | extractive |  | 7046.4 |
| e01 | exact | en | 1 | is-4151-2015 | 3.220 | standards_list | live |  | 6371.4 |
| e02 | exact | en | 1 | is-1786-2008 | -10.893 | insufficient_evidence | live |  | 18036.6 |
| e03 | exact | en | 1 | demo-101-2026 | 7.892 | answer | live | yes | 5557.8 |
| e04 | exact | en | 1 | demo-201-2026 | 4.265 | answer | extractive | yes | 9900.9 |
| e05 | exact | en | 1 | is-14543 | 4.460 | standards_list | live |  | 4864.9 |
| e06 | exact | en | 1 | demo-301-2026 | 6.790 | standards_list | live |  | 10702.0 |
| c01 | compare | en | 1 | demo-102-2026 | 5.761 | standards_list | live |  | 6486.5 |
| c02 | compare | en | 3 | demo-102-2026 | 5.766 | answer | live |  | 7356.1 |
| c03 | compare | en | 2 | demo-102-2026 | 1.567 | comparison | live |  | 6085.7 |
| f01 | followup | en | 2 | demo-101-2026 | 8.509 | requirements | live |  | 5763.0 |
| f02 | followup | en | 1 | demo-201-2026 | 8.753 | requirements | live |  | 5409.8 |
| f03 | followup | en | 1 | demo-301-2026 | 7.454 | standards_list | live |  | 5873.2 |
| u01 | unanswerable | en | — | demo-201-2026 | -8.257 | insufficient_evidence | none |  | 2.6 |
| u02 | unanswerable | en | — | demo-101-2026 | -0.569 | insufficient_evidence | live |  | 3555.1 |
| u03 | unanswerable | en | — | demo-301-2026 | 0.077 | insufficient_evidence | live |  | 3584.3 |
| u04 | unanswerable | en | — | demo-101-2026 | -0.064 | insufficient_evidence | live |  | 3751.7 |
| u05 | unanswerable | en | — | bis-hallmarking-consumer-faq | -2.448 | insufficient_evidence | live |  | 3568.6 |
| u06 | unanswerable | en | — | bis-guidelines-grant-of-licence-2026 | -5.714 | insufficient_evidence | none |  | 1.7 |
| u07 | unanswerable | en | — | demo-201-2026 | -5.272 | insufficient_evidence | none |  | 1.1 |
| u08 | unanswerable | en | — | is-4151-2015 | 1.183 | insufficient_evidence | live |  | 3651.1 |
| u09 | unanswerable | en | — | demo-102-2026 | -9.914 | insufficient_evidence | none |  | 2.3 |
| u10 | unanswerable | en | — | bis-guidelines-grant-of-licence-2026 | -0.982 | insufficient_evidence | live |  | 3802.3 |
| u11 | unanswerable | en | — | demo-201-2026 | -0.655 | insufficient_evidence | live |  | 3706.7 |
| u12 | unanswerable | hi | — | demo-201-2026 | -8.139 | insufficient_evidence | none |  | 1519.9 |

## Notes

- All answerable questions were auto-drafted from ingested clauses (`origin: auto_drafted`) and should be spot-checked by the team.
- The Tier C demo documents are synthetic; numbers on them measure the pipeline, not coverage of real Indian Standards.
- Latency is measured on the build laptop (CPU embeddings/reranker; local LLM on an 8 GB laptop GPU when used).
