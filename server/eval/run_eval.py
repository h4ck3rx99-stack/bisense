"""Thin wrapper so the evaluation can also be run as a script: `uv run python eval/run_eval.py`.
The implementation lives in bisense/evaluation.py (also available as `bisense eval`)."""

import sys

from bisense.evaluation import main

if __name__ == "__main__":
    main(no_llm="--no-llm" in sys.argv, smoke="--smoke" in sys.argv, compare="--compare" in sys.argv)
