"""Run one model through the seven standard runs and save the results.

Used by run_on_pod.py on the pod; works locally too. From the project root:
    python -m src.batch '{"model_id": "knowledgator/gliclass-v4-9b", "device": "cuda:0",
                          "dtype": "bfloat16", "max_length": 8192, "model_name": "9b"}'
"""

import json
import sys
import threading
import time

from src.evaluate import accuracy, score
from src.questions import RUNS, load_questions
from src.runner import load_pipeline, run_all, save_results


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def heartbeat(message, done, every=30):
    """Log message with the elapsed time every `every` seconds until done is set."""
    started = time.monotonic()
    while not done.wait(every):
        log(f"{message} ({time.monotonic() - started:.0f} s)")


def run_model(settings, questions_path="questions.json", results_dir="results"):
    """Run every question in each of RUNS and save results/<model_name>_<run>.json."""
    questions = load_questions(questions_path)
    log(f"Loading {settings['model_id']} (downloads on first use)")
    started = time.monotonic()
    loaded = threading.Event()
    threading.Thread(target=heartbeat, args=("Still loading", loaded), daemon=True).start()
    try:
        pipeline = load_pipeline(settings)
    finally:
        loaded.set()
    log(f"Loaded in {time.monotonic() - started:.0f} s")

    for number, (run, options) in enumerate(RUNS.items(), start=1):
        name = f"{settings['model_name']}_{run}"
        log(f"Run {number}/{len(RUNS)}: {name}")
        results = run_all(pipeline, questions, **options, verbose=True)
        save_results(results, f"{results_dir}/{name}.json", **settings, questions_file=questions_path,
                     run=run, **options)
        print(accuracy(score(results, questions, options["include_graph"]), by="question_type").to_string(index=False))
        log(f"Saved {results_dir}/{name}.json")


if __name__ == "__main__":
    run_model(json.loads(sys.argv[1]))
