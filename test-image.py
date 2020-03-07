#!/usr/bin/env python3

from contextlib import contextmanager
import sys
import subprocess
from subprocess import PIPE, STDOUT
from time import sleep, perf_counter
import traceback

import requests


URL_PREFIX = "http://127.0.0.1:8080"
HTTP_CHECK_FUNCS = []


def test_image(image):
    with run_container(image) as container_id, requests.Session() as session:
        print(f"Container started, to tail its logs: docker logs -f -t {container_id}")
        start = perf_counter()
        wait_for_container_ready(session)
        start_duration = perf_counter() - start
        print(f"Service has started responding in {start_duration}s.")

        check(logs_on_startup, container_id)
        check(logs_each_request, container_id, session)
        perform_http_checks(session)


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


def run(program_args, verbose=True, **kwargs):
    if verbose:
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


def check(func, *args):
    """Perform a single check and print its result."""
    print(f"{func.__doc__}: ", end="")
    try:
        func(*args)
        print("Good")
    except AssertionError as e:
        failed_line = traceback.extract_tb(sys.exc_info()[2])[-1].line  # magic to extrac the "assert line"
        print(f"Bad: {failed_line}: {e}")


def logs_on_startup(container_id):
    """Service logs a message containing 8080 (used port) on startup"""
    out = run(["docker", "logs", container_id], verbose=False, check=True, stdout=PIPE, stderr=STDOUT, text=True).stdout
    assert "8080" in out, f"got {len(out.splitlines())} lines of log: \n{out}"


def logs_each_request(container_id, session):
    """Service logs every request, message contains url path"""
    path = "/blablaGOGOthisIsCanaryValue"
    session.get(URL_PREFIX + path)
    out = run(["docker", "logs", container_id], verbose=False, check=True, stdout=PIPE, stderr=STDOUT, text=True).stdout
    assert path in out, f"got {len(out.splitlines())} lines of log: \n{out}"


def test_local():
    with requests.Session() as session:
        perform_http_checks(session)


def perform_http_checks(session):
    for func in HTTP_CHECK_FUNCS:
        check(func, session)


def http_check(func):
    """Simple decorator to mark a function as an HTTP check."""
    HTTP_CHECK_FUNCS.append(func)
    return func


@http_check
def http_check_root(session: requests.Session):
    """HTTP GET / returns 200 or 404"""
    res = session.get(URL_PREFIX + "/")
    assert res.status_code in (200, 404), (res, res.text)


@http_check
def http_check_nonexistent_path(session: requests.Session):
    """HTTP GET /fnhjkdniudsancyne returns 404"""
    res = session.get(URL_PREFIX + "/fnhjkdniudsancyne")
    assert res.status_code == 404, (res, res.text)


@http_check
def http_check_no_params(session: requests.Session):
    """HTTP GET /city/v1/get returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get")
    assert_error_reply(res, 400)


@http_check
def http_check_just_id_param(session: requests.Session):
    """HTTP GET /city/v1/get?id=123 returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=123")
    assert_error_reply(res, 400)


@http_check
def http_check_invalid_id(session: requests.Session):
    """HTTP GET /city/v1/get?id=blabla returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=blabla")
    assert_error_reply(res, 400)


@http_check
def http_check_just_language_param(session: requests.Session):
    """HTTP GET /city/v1/get?language=cs returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get?language=cs")
    assert_error_reply(res, 400)


@http_check
def http_check_nonexistent_city_id(session: requests.Session):
    """HTTP GET /city/v1/get?id=123&language=cs returns 404 (this does not exist) with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=123&language=cs")
    assert_error_reply(res, 404)


def assert_error_reply(res: requests.Response, expected_code):
    assert res.status_code == expected_code, (expected_code, res, res.text)
    assert res.headers['content-type'] == 'application/json', res.headers
    json = res.json()
    assert 'message' in json, json


@http_check
def http_check_plzen_cs(session: requests.Session):
    """HTTP GET /city/v1/get?id=101748111&language=cs returns 200 and correct object"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=101748111&language=cs")
    assert_city_reply(res, 101748111, "Plzeň", "Plzeňský kraj")


@http_check
def http_check_brno_de(session: requests.Session):
    """HTTP GET /city/v1/get?id=101748109&language=de returns 200 and correct object"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=101748109&language=de")
    assert_city_reply(res, 101748109, "Brünn", "Südmährische Region")


def assert_city_reply(res: requests.Response, expected_id, expected_city, expected_region):
    assert res.status_code == 200, (res, res.text)
    assert res.headers['content-type'] == 'application/json', res.headers
    json = res.json()
    assert json.keys() == set(['countryISO', 'id', 'isFeatured', 'name', 'regionName']), json
    assert json['countryISO'] == 'CZ', json
    assert json['id'] == expected_id, (expected_id, json)
    assert type(json['isFeatured']) == bool, json  # Not yet in Elastic, check just type
    assert json['name'] == expected_city, (expected_city, json)
    assert json['regionName'] == expected_region, (expected_region, json)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} (docker-image/with-optional:tag | --local)")
        exit(1)
    arg = sys.argv[1]
    if arg == '--local':
        test_local()
    else:
        test_image(arg)
