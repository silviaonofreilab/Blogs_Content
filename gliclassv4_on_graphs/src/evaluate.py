"""Read run results, score them against the gold answers and compare runs."""

import json
from pathlib import Path

import pandas as pd

NO_GRAPH_ANSWER = "INSUFFICIENT_INFORMATION"


def load_results(path):
    """Read a result file written by src.runner.save_results.

    Return the run's settings (a dict, such as model_id, run and include_graph)
    and its answers (a DataFrame with one row per question).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["settings"], pd.DataFrame(data["answers"])


def score(answers, questions, include_graph):
    """Return one row per question with its gold answer, selection and correctness.

    answers has one row per question, as returned by run_all or load_results.
    gold is the question's expected answer. expected is what counts as correct
    for the run: gold, or INSUFFICIENT_INFORMATION when include_graph is False
    (the run left the graph out). Runs without edges or rules are scored
    against gold. twin marks a copy of an earlier question with edited
    evidence; variant_of names that question.
    """
    rows = []
    for result in answers.itertuples():
        question = questions[result.id]
        gold = question["expected_answer"][0]
        expected = gold if include_graph else NO_GRAPH_ANSWER
        rows.append({
            "id": result.id,
            "question_type": question["question_type"],
            "twin": "variant_of" in question,
            "variant_of": question.get("variant_of"),
            "hops": question["hops"],
            "gold": gold,
            "expected": expected,
            "selected": result.selected,
            "correct": result.selected == expected,
            "score": result.score,
            "seconds": result.seconds,
        })
    return pd.DataFrame(rows)


def accuracy(scored, by=None):
    """Return correct, total and accuracy overall, or per value of a column such as "question_type" or "twin"."""
    if by is None:
        table = pd.DataFrame([{"correct": int(scored["correct"].sum()), "total": len(scored)}])
    else:
        table = scored.groupby(by)["correct"].agg(correct="sum", total="count").reset_index()
    table["accuracy"] = table["correct"] / table["total"]
    return table


def twin_pairs(scored):
    """Return each twin next to its original, with both selections and whether the answer changed."""
    by_id = scored.set_index("id")
    twins = scored[scored["twin"]]
    originals = by_id.loc[twins["variant_of"]]
    return pd.DataFrame({
        "original": twins["variant_of"].values,
        "twin": twins["id"].values,
        "original_selected": originals["selected"].values,
        "twin_selected": twins["selected"].values,
        "twin_expected": twins["expected"].values,
        "original_correct": originals["correct"].values,
        "twin_correct": twins["correct"].values,
        "changed": originals["selected"].values != twins["selected"].values,
    })


def compare(runs):
    """Return the selection and correctness per question across scored runs.

    runs maps a name, such as "edge_label_graph" or "edge_label_noedges", to the output of score().
    """
    first = next(iter(runs.values()))
    table = first[["id", "question_type", "twin", "gold"]].copy()
    for name, scored in runs.items():
        by_id = scored.set_index("id")
        table[f"{name}_selected"] = table["id"].map(by_id["selected"])
        table[f"{name}_correct"] = table["id"].map(by_id["correct"])
    return table
