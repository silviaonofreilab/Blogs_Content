"""Run the GLiClass models on a RunPod GPU pod and download the results.

Run locally from the project root:
    uv run run_on_pod.py                  # every model in MODELS; terminate the pod at the end
    uv run run_on_pod.py --models 9b      # only the named models
    uv run run_on_pod.py --end stop       # stop the pod instead and keep its volume
    uv run run_on_pod.py --fresh          # delete any existing pod first, then create a new one

Settings in .env: RUNPOD_API_KEY (required); RUNPOD_SSH_KEY, the private key registered
with RunPod (default ~/.ssh/id_ed25519); HF_TOKEN (optional), passed to the pod for model downloads.
The pod's environment is fixed when it is created, so use --fresh after changing HF_TOKEN.
The --end action runs however the script ends: success, error or Ctrl-C.
run_9b_27b_on_pod.ipynb runs the same job through run_job().
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import zipfile
from importlib.metadata import version
from pathlib import Path

import runpod
from dotenv import load_dotenv

from src.pod import VOLUME_MOUNT, PodUnavailable, log, stop, terminate, up

load_dotenv()

SSH_KEY = Path(os.environ.get("RUNPOD_SSH_KEY", "~/.ssh/id_ed25519")).expanduser()
HF_TOKEN = os.environ.get("HF_TOKEN")  # optional; the pod gets it for Hugging Face downloads
REMOTE_DIR = f"{VOLUME_MOUNT}/glidecide"
REMOTE_ZIP = f"{VOLUME_MOUNT}/glidecide.zip"

POD = {
    "name": "glidecide",
    "image": "runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404",  # check the tag in RunPod's templates
    "gpu_type": "NVIDIA H100 80GB HBM3",  # exact ids: runpod.get_gpus()
    "cloud_type": "SECURE",
    "container_disk_gb": 50,
    "volume_gb": 150,  # Hugging Face cache: 9B is 18 GB, 27B about 54 GB
    "ports": "22/tcp",
    "env": {"HF_HOME": f"{VOLUME_MOUNT}/hf"} | ({"HF_TOKEN": HF_TOKEN} if HF_TOKEN else {}),
}

MODELS = [
    {"model_id": "knowledgator/gliclass-v4-9b", "device": "cuda:0", "dtype": "bfloat16",
     "max_length": 8192, "model_name": "9b"},
    {"model_id": "knowledgator/gliclass-v4-27b", "device": "cuda:0", "dtype": "bfloat16",
     "max_length": 8192, "model_name": "27b"},
]

# The pod installs the versions used locally, so local and pod runs are comparable.
POD_PACKAGES = " ".join(f"{name}=={version(name)}" for name in ("gliclass", "pandas"))

# ServerAlive: a dropped connection fails within about 2 minutes instead of hanging.
SSH_OPTIONS = ["-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
               "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=4"]
# SSH sessions do not see the pod's environment (HF_HOME, HF_TOKEN); load it from the container's first process.
POD_ENV = "while IFS= read -r -d '' line; do export \"$line\"; done < /proc/1/environ"


def ssh_address(pod_id, timeout=300):
    """Return the host and port for direct SSH to the pod, waiting until RunPod reports them."""
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        pod = runpod.get_pod(pod_id) or {}
        direct = (pod.get("ssh") or {}).get("direct")
        if direct:
            return direct["host"], int(direct["port"])
        for port in (pod.get("runtime") or {}).get("ports", []):
            if port.get("private") == 22 and port.get("ip") and port.get("public"):
                return port["ip"], int(port["public"])
        log(f"Waiting for RunPod to report the SSH address ({time.monotonic() - started:.0f} s)")
        time.sleep(10)
    raise PodUnavailable(f"Pod {pod_id} reported no SSH address within {timeout} s")


def ssh(host, port, command, check=True):
    """Run a shell command on the pod.

    In a terminal, -t streams progress bars live and passes Ctrl-C to the pod;
    a notebook has no terminal, so the flag is left out there.
    """
    terminal = ["-t"] if sys.stdin.isatty() else []
    return subprocess.run(
        ["ssh", *terminal, *SSH_OPTIONS, "-p", str(port), f"root@{host}", f"{POD_ENV}; {command}"],
        check=check,
    ).returncode


def scp(port, *paths):
    """Copy files between this machine and the pod; remote paths look like root@host:/path."""
    subprocess.run(["scp", *SSH_OPTIONS, "-P", str(port), "-r", *paths], check=True)


def wait_for_ssh(host, port, timeout=300):
    """Wait until the pod accepts SSH connections."""
    started = time.monotonic()
    while ssh(host, port, "true", check=False) != 0:
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise PodUnavailable(f"No SSH connection to {host}:{port} within {timeout} s")
        log(f"SSH not ready yet ({elapsed:.0f} s)")
        time.sleep(10)


def run(models, fresh):
    """Run the models on the pod, download results/ and return the model names that failed."""
    if fresh:
        log("--fresh: deleting any existing pod first")
        terminate(POD)

    pod_id = up(POD)
    host, port = ssh_address(pod_id)
    log(f"Connecting over SSH to {host}:{port}")
    wait_for_ssh(host, port)

    log("Uploading src/ and questions.json")
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder) / "glidecide.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.write("questions.json")
            for file in Path("src").glob("*.py"):
                zipped.write(file)
        scp(port, str(archive), f"root@{host}:{REMOTE_ZIP}")

    # A clean folder drops code and results left by an earlier run on a reused volume.
    log(f"Unpacking into a clean {REMOTE_DIR} and installing {POD_PACKAGES}")
    ssh(host, port, f"rm -rf {REMOTE_DIR} && python -m zipfile -e {REMOTE_ZIP} {REMOTE_DIR}"
                    f" && mkdir -p {REMOTE_DIR}/results && pip install {POD_PACKAGES}")

    failed = []
    for number, model in enumerate(models, start=1):
        log(f"Model {number}/{len(models)}: {model['model_name']} ({model['model_id']})")
        command = f"cd {REMOTE_DIR} && python -u -m src.batch {shlex.quote(json.dumps(model))}"
        if ssh(host, port, command, check=False) != 0:
            log(f"{model['model_name']} failed; continuing")
            failed.append(model["model_name"])

    log("Downloading results/")
    scp(port, f"root@{host}:{REMOTE_DIR}/results", ".")
    log("Results downloaded to results/")
    return failed


def run_job(model_names=None, end="terminate", fresh=False):
    """Run the named models (default: all of MODELS) on the pod, then end the pod.

    end is "terminate" (delete the pod and its volume) or "stop" (keep the volume).
    The pod is ended however the run finishes: success, error or interrupt.
    Return True if every model ran.
    """
    names = [model["model_name"] for model in MODELS]
    model_names = names if model_names is None else list(model_names)
    unknown = sorted(set(model_names) - set(names))
    if unknown:
        raise ValueError(f"Unknown models {unknown}; choose from {names}")
    if end not in ("terminate", "stop"):
        raise ValueError(f'end must be "terminate" or "stop", not {end!r}')
    models = [model for model in MODELS if model["model_name"] in model_names]

    log(f"Plan: {', '.join(m['model_name'] for m in models)} on 1 x {POD['gpu_type']}; "
        f"the pod will be {'terminated' if end == 'terminate' else 'stopped'} at the end")
    succeeded = False
    try:
        failed_models = run(models, fresh)
        succeeded = not failed_models
        if failed_models:
            log(f"FAILED: {', '.join(failed_models)}")
    except PodUnavailable as exc:
        log(f"POD NOT AVAILABLE: {exc}")
        if "cannot start" in str(exc) and end == "stop":
            log("Rerun with --fresh (fresh=True in the notebook) to delete the stopped pod and create a new one.")
    except KeyboardInterrupt:
        log("Interrupted")
    finally:
        log(f"Ending: {end} pod")
        (terminate if end == "terminate" else stop)(POD)
    return succeeded


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--end", choices=["terminate", "stop"], default="terminate",
                        help="what to do with the pod at the end (default: terminate)")
    parser.add_argument("--fresh", action="store_true", help="delete any existing pod before starting")
    names = [model["model_name"] for model in MODELS]
    parser.add_argument("--models", nargs="+", choices=names, default=names, metavar="NAME",
                        help=f"models to run: {', '.join(names)} (default: all)")
    args = parser.parse_args()
    sys.exit(0 if run_job(args.models, args.end, args.fresh) else 1)


if __name__ == "__main__":
    main()
