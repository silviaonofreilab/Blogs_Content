"""Create, check, stop and terminate the single-GPU RunPod pod, printing each step.

RUNPOD_API_KEY must be set in the environment (run_on_pod.py loads it from .env).
Settings are a dict; see POD in run_on_pod.py.
"""

import os
import time

import runpod
from runpod.error import QueryError

VOLUME_MOUNT = "/workspace"


class PodUnavailable(Exception):
    """RunPod cannot create or start the pod right now; the message says why."""


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def find_pod(name):
    """Return the pod with this name, or None."""
    runpod.api_key = os.environ["RUNPOD_API_KEY"]
    return next((pod for pod in runpod.get_pods() if pod.get("name") == name), None)


def up(settings, timeout=600):
    """Create, resume or reuse the named pod, wait until it is RUNNING and return its id."""
    pod = find_pod(settings["name"])
    if pod is None:
        log(f"Creating pod {settings['name']!r}: 1 x {settings['gpu_type']}, {settings['cloud_type']} cloud")
        try:
            pod = runpod.create_pod(
                name=settings["name"],
                image_name=settings["image"],
                gpu_type_id=settings["gpu_type"],
                gpu_count=1,
                cloud_type=settings["cloud_type"],
                container_disk_in_gb=settings["container_disk_gb"],
                volume_in_gb=settings["volume_gb"],
                volume_mount_path=VOLUME_MOUNT,
                ports=settings["ports"],
                env=settings["env"],
            )
        except QueryError as exc:
            raise PodUnavailable(f"RunPod could not create the pod: {exc}") from None
    elif pod["status"] == "RUNNING":
        log(f"Reusing running pod {pod['id']}")
    elif "start" in pod["actions"]:
        log(f"Resuming stopped pod {pod['id']}")
        try:
            runpod.resume_pod(pod["id"])
        except QueryError as exc:
            raise PodUnavailable(f"Stopped pod {pod['id']} cannot start: {exc}") from None

    started = time.monotonic()
    last_report = None
    while True:
        status = (runpod.get_pod(pod["id"]) or {}).get("status")
        elapsed = time.monotonic() - started
        if status == "RUNNING":
            log(f"Pod {pod['id']} is RUNNING after {elapsed:.0f} s")
            return pod["id"]
        if elapsed > timeout:
            raise PodUnavailable(f"Pod {pod['id']} not RUNNING after {timeout} s (last status: {status})")
        if last_report is None or elapsed - last_report >= 30:
            log(f"Waiting for pod {pod['id']}: status {status}, {elapsed:.0f} s")
            last_report = elapsed
        time.sleep(5)


def status(settings):
    """Return the pod's id and status, or None if no pod has this name."""
    pod = find_pod(settings["name"])
    return None if pod is None else {"id": pod["id"], "status": pod["status"]}


def stop(settings):
    """Stop the pod, keeping its volume. Return its id, or None if absent."""
    pod = find_pod(settings["name"])
    if pod is None:
        log(f"No pod named {settings['name']!r}; nothing to stop")
        return None
    if "stop" in pod["actions"]:
        runpod.stop_pod(pod["id"])
        log(f"Stopped pod {pod['id']}; its volume is kept (resuming needs a free GPU on the same machine)")
    else:
        log(f"Pod {pod['id']} is already {pod['status']}")
    return pod["id"]


def terminate(settings):
    """Delete the pod and its volume. Return its id, or None if absent."""
    pod = find_pod(settings["name"])
    if pod is None:
        log(f"No pod named {settings['name']!r}; nothing to terminate")
        return None
    runpod.terminate_pod(pod["id"])
    log(f"Terminated pod {pod['id']}; its volume is deleted")
    return pod["id"]
