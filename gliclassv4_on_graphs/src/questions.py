"""Load decision questions and build GLiClass inputs."""

import json
import re
from pathlib import Path

# The seven standard runs: run name -> build_input options.
RUNS = {
    "label_graph": {"label_source": "label", "include_graph": True, "include_edges": True, "include_rules": True},
    "label_nograph": {"label_source": "label", "include_graph": False, "include_edges": False, "include_rules": True},
    "description_graph": {"label_source": "description", "include_graph": True, "include_edges": True, "include_rules": True},
    "label_noedges": {"label_source": "label", "include_graph": True, "include_edges": False, "include_rules": True},
    "label_norules": {"label_source": "label", "include_graph": True, "include_edges": True, "include_rules": False},
    "label_nograph_norules": {"label_source": "label", "include_graph": False, "include_edges": False,
                           "include_rules": False},
    "description_nograph_norules": {"label_source": "description", "include_graph": False, "include_edges": False,
                             "include_rules": False},
}

# A graph_text line that states a relationship, such as "A1 -RECORDED_DIAGNOSIS-> each of [D1, D2]".
EDGE_LINE = re.compile(r"^\S+ -[A-Z_]+-> ")


def load_questions(path):
    """Return the questions in a JSON file as a dict keyed by id, in file order."""
    questions = json.loads(Path(path).read_text(encoding="utf-8"))["questions"]
    return {question["id"]: question for question in questions}


def build_input(question, label_source="label", include_graph=True, include_edges=True, include_rules=True):
    """Return the GLiClass inputs for one question.

    Graph facts and rules form the text, and the question is the prompt.
    Each candidate answer has a label, such as SOME_ADMISSIONS, and a label
    description. label_source picks which of the two the model is shown as its
    labels: "label" or "description". candidate_labels keeps the labels in the
    same order, for scoring against expected_answer.
    include_graph=False leaves the graph facts out, so the text is the rules only.
    include_edges=False keeps the nodes and drops the relationship lines.
    include_rules=False leaves the rules out; with neither graph nor rules the text is empty.
    """
    lines = question["graph_text"] if include_graph else []
    if not include_edges:
        lines = [line for line in lines if not EDGE_LINE.match(line)]
    graph = "\n".join(lines)
    rules = "\n".join(f"- {rule['rule']}" for rule in question["rules"]) if include_rules else ""
    candidates = question["candidate_answers"]
    return {
        "text": "\n".join(part for part in (graph, rules) if part),
        "prompt": question["question"],
        "labels": [candidate[label_source] for candidate in candidates],
        "candidate_labels": [candidate["label"] for candidate in candidates],
        "classification_type": question["answer_mode"].replace("_", "-"),
    }
