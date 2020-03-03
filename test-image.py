#!/usr/bin/env python3

from contextlib import contextmanager
import sys
import subprocess


def test_image(image):
    with run_image(image) as container_id:
        print(f"Container id: {container_id}.")


@contextmanager
def run_image(image):
    # TODO: limit cpu, memory
    process = run(["docker", "run", "-d", "-e=GOOUT_ELASTIC_HOST", "-e=GOOUT_ELASTIC_PORT", "-p=8080:8080", image],
                  check=True, capture_output=True, text=True)
    container_id = process.stdout.strip()
    try:
        yield container_id
    finally:
        run(["docker", "kill", container_id])


def run(program_args, **kwargs):
    print(f"$ {' '.join(program_args)}")
    return subprocess.run(program_args, **kwargs)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} docker-image-with-optional:tag")
        exit(1)
    test_image(sys.argv[1])
