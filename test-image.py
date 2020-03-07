#!/usr/bin/env python3

from contextlib import contextmanager
import sys
import subprocess
from time import sleep, perf_counter

import requests


URL_PREFIX = "http://127.0.0.1:8080"


def test_image(image):
    with run_container(image) as container_id, requests.Session() as session:
        print(f"Container started, to tail its logs: docker logs -f {container_id}")
        start = perf_counter()
        wait_for_container_ready(session)
        end = perf_counter()
        print(f"Service has started in {end - start}s.")


@contextmanager
def run_container(image):
    # Give only 1s of CPU-core-time per each wall clock second. (can still run in parallel). Lets the rest of the
    # system breathe and better simulates Kubernetes environment (which uses the same method of capping CPU).
    cpu_limit = "--cpus=1.0"
    # 500 MB should be a conservative limit of something called a microservice. Setting swap to same value to disable.
    memory_limits = ["--memory=500m", "--memory-swap=500m"]
    process = run(["docker", "run", "--rm", "-d", "-e=GOOUT_ELASTIC_HOST", "-e=GOOUT_ELASTIC_PORT", "-p=8080:8080",
                   cpu_limit, *memory_limits, image],
                  check=True, capture_output=True, text=True)
    container_id = process.stdout.strip()
    try:
        yield container_id
    finally:
        run(["docker", "kill", container_id], capture_output=True)


def run(program_args, **kwargs):
    print(f"$ {' '.join(program_args)}")
    try:
        return subprocess.run(program_args, **kwargs)
    except subprocess.CalledProcessError as e:
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        raise


def wait_for_container_ready(session):
    timeout = 15
    last_exc = None
    for _ in range(timeout * 100):  # We wait one hundredth of a second.
        try:
            return session.get(URL_PREFIX)
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            sleep(0.01)
    raise AssertionError(f"Failed to connect to {URL_PREFIX} in {timeout}s: {last_exc}. Does it listen on 0.0.0.0?")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} docker-image-with-optional:tag")
        exit(1)
    test_image(sys.argv[1])
