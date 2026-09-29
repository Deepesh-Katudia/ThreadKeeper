"""Score a story's approved episodes in LangSmith from the command line.

    python -m evals.run_evals --story 1

Same experiment as the "Run evaluation" button on the Evals tab; see story/evaluation.py.
"""

import argparse

from story.db import create_tables
from story.evaluation import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story", type=int, required=True, help="story id to evaluate")
    args = parser.parse_args()

    create_tables()
    result = run_experiment(args.story)
    print(f"Scored {result.episodes_scored} episodes for ${result.cost_usd:.4f}")
    for key, score in result.scores.items():
        print(f"  {key:<20} {'-' if score is None else f'{score:.2f}'}")
    print(f"LangSmith experiment: {result.experiment_url or result.experiment_name}")


if __name__ == "__main__":
    main()
