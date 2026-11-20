"""Load a GLiClass model and run decision questions through it."""

import json
from pathlib import Path
from time import perf_counter

import pandas as pd
import torch
from gliclass import GLiClassModel, ZeroShotClassificationPipeline

from src.questions import build_input


def load_pipeline(settings):
    """Return a single-label GLiClass pipeline built from a settings dict.

    Uses settings["model_id"], ["device"], ["max_length"] and ["dtype"],
    a torch dtype name such as "float32" or "bfloat16".
    Inputs longer than max_length are truncated by gliclass without a warning.
    """
    model = GLiClassModel.from_pretrained(
        settings["model_id"], torch_dtype=getattr(torch, settings["dtype"])
    )
    return ZeroShotClassificationPipeline(
        model,
        settings["model_id"],
        classification_type="single-label",
        max_length=settings["max_length"],
        device=settings["device"],
        progress_bar=False,
    )


def run_question(pipeline, question, label_source="label", include_graph=True, include_edges=True, include_rules=True):
    """Return the scores by label, the top-scoring label and the elapsed seconds."""
    model_input = build_input(question, label_source, include_graph, include_edges, include_rules)
    started = perf_counter()
    with torch.inference_mode():
        scores = pipeline(
            model_input["text"],
            model_input["labels"],
            prompt=model_input["prompt"],
            classification_type=model_input["classification_type"],
            return_hierarchical=True,
        )[0]
    seconds = perf_counter() - started
    scores = {
        label: scores[shown]
        for shown, label in zip(model_input["labels"], model_input["candidate_labels"])
    }
    return {"scores": scores, "selected": max(scores, key=scores.get), "seconds": seconds}


def run_all(pipeline, questions, label_source="label", include_graph=True, include_edges=True, include_rules=True,
            verbose=False):
    """Run every question in order and return one row per question.

    Each row holds the question id, the selected label, its score, the elapsed
    seconds and the scores of all candidates. verbose=True prints one line per
    question as it finishes.
    """
    rows = []
    for question in questions.values():
        result = run_question(pipeline, question, label_source, include_graph, include_edges, include_rules)
        if verbose:
            selected = result["selected"]
            print(f"  {question['id']}  {selected}  {result['scores'][selected]:.3f}  {result['seconds']:.2f} s")
        rows.append({
            "id": question["id"],
            "selected": result["selected"],
            "score": result["scores"][result["selected"]],
            "seconds": result["seconds"],
            "scores": result["scores"],
        })
    return pd.DataFrame(rows)


def save_results(answers, path, **settings):
    """Write a run to a JSON file, creating its folder if needed.

    The file holds the run's settings once, such as model_id, run and
    include_graph, then one answer per question from run_all:
    {"settings": {...}, "answers": [...]}. src.evaluate.load_results reads it back.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = json.loads(answers.to_json(orient="records", double_precision=15))
    path.write_text(json.dumps({"settings": settings, "answers": records}, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
