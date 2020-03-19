#!/usr/bin/env python3

"""
GoOut Locations MVP Docker image tester and benchmark.

Usage:
  test-image.py <docker-image> [--no-bench]
  test-image.py --local
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import os
import re
import subprocess
import sys
from time import sleep, perf_counter
import traceback

try:
    import docker
    from docopt import docopt
    import requests
except ImportError as e:
    raise Exception('Some external dependencies not found, install them using: pip install -r requirements.txt') from e


URL_PREFIX = "http://127.0.0.1:8080"
HTTP_CHECK_FUNCS = []
TOTAL_REQUESTS = 0
TOTAL_REQUEST_ERRORS = 0
STATS = []
CHECKS = {}


@dataclass
class Stats:
    message: str
    cpu_total_s: float
    cpu_new_s: float
    mem_usage_mb: float
    mem_max_mb: float
    requests_total: int
    requests_new: int
    request_errors_total: int
    request_errors_new: int
    connections: int
    latency_90p_ms: float
    requests_per_s: float


def test_image(image: str, bench: bool):
    dockerc = docker.from_env()

    check_doesnt_start_with_env(dockerc, image, 'Does not start without env variables', {})
    check_doesnt_start_with_env(dockerc, image, 'Does not start with invalid ES address',
                                {'GOOUT_ELASTIC_HOST': '127.0.0.1', 'GOOUT_ELASTIC_PORT': '56789'})

    with run_container(dockerc, image) as container, requests.Session() as session:
        print(f"Container started, to tail its logs: docker logs -f -t {container.id}")
        start = perf_counter()
        wait_for_container_ready(session)
        log_check("Startup time (to start responding) secs", perf_counter() - start)
        collect_stats(container, "After startup")

        log_check("Docker image size (MB)", container.image.attrs['Size'] / 1024**2)

        check(logs_on_startup, container)
        check(logs_each_request, container, session)
        perform_http_checks(session)
        collect_stats(container, "After HTTP checks")

        connection_range = (1, 2, 5, 10, 20, 50, 100, 200, 500) if bench else ()
        for connection_count in connection_range:
            run_benchmark(container, connection_count)

    sane_name = re.sub('[^a-z0-9]+', '-', image)
    save_results(f'{sane_name}.checks{".bench" if bench else ""}.json')


def check_doesnt_start_with_env(dockerc: docker.DockerClient, image, message, env):
    print(f'{message}: ', end='', flush=True)
    container = dockerc.containers.run(image, auto_remove=True, environment=env, detach=True)
    start = perf_counter()
    timeout = 15
    try:
        container.wait(timeout=timeout)
        value = f"Good, exited in {(perf_counter() - start):.1f}s"
        print(value)
    except Exception as e:
        value = f"Bad, did not exit in {timeout}s"
        print(f'{value}, logs: {container.logs().decode()}')
        container.kill()

    log_check(message, value, verbose=False)


def log_check(message, value, verbose=True):
    if verbose:
        print(f'{message}: {value}')
    assert message not in CHECKS
    CHECKS[message] = value


@contextmanager
def run_container(dockerc: docker.DockerClient, image):
    # Give only 1s of CPU-core-time per each wall clock second. (can still run in parallel). Lets the rest of the
    # system breathe and better simulates Kubernetes environment (which uses the same method of capping CPU).
    nano_cpus = 10**9
    # 512 MB should be a conservative limit of something called a microservice. Setting swap to same value to disable.
    mem_limit = "512m"
    environment = {key: os.environ[key] for key in ('GOOUT_ELASTIC_HOST', 'GOOUT_ELASTIC_PORT')}
    cpuset_cpus = "0-3"  # Assign 4 logical CPUs to the container to simulate our real cluster.

    container = dockerc.containers.run(
        image, auto_remove=True, detach=True, nano_cpus=nano_cpus, mem_limit=mem_limit, memswap_limit=mem_limit,
        ports={8080: 8080}, environment=environment, cpuset_cpus=cpuset_cpus)
    try:
        yield container
    finally:
        container.kill()


def wait_for_container_ready(session):
    timeout = 15
    last_exc = None
    global TOTAL_REQUESTS
    for _ in range(timeout * 100):  # We wait one hundredth of a second.
        try:
            session.get(URL_PREFIX)
            TOTAL_REQUESTS += 1
            return
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            sleep(0.01)
    raise AssertionError(f"Failed to connect to {URL_PREFIX} in {timeout}s: {last_exc}. Does it listen on 0.0.0.0?")


def check(func, *args):
    """Perform a single check and print its result."""
    print(f"{func.__doc__}: ", end='', flush=True)
    try:
        func(*args)
    except AssertionError as e:
        value = "Bad"
        failed_line = traceback.extract_tb(sys.exc_info()[2])[-1].line  # magic to extract the "assert line"
        print(f"Bad: {failed_line}: {e}")
    else:
        value = "Good"
        print(value)
    log_check(func.__doc__, value, verbose=False)  # we have already printed


def logs_on_startup(container):
    """Service logs a message containing 8080 (used port) on startup"""
    out = container.logs().decode()
    assert "8080" in out, f"got {len(out.splitlines())} lines of log: \n{out}"


def logs_each_request(container, session):
    """Service logs every request, message contains url path"""
    path = "/blablaGOGOthisIsCanaryValue"
    session.get(URL_PREFIX + path)
    global TOTAL_REQUESTS
    TOTAL_REQUESTS += 1
    out = container.logs().decode()
    assert path in out, f"got {len(out.splitlines())} lines of log: \n{out}"


def test_local():
    with requests.Session() as session:
        perform_http_checks(session)


def perform_http_checks(session):
    global TOTAL_REQUESTS
    for func in HTTP_CHECK_FUNCS:
        check(func, session)
        TOTAL_REQUESTS += 1


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
    """HTTP GET /city/v1/get?id=blabla&language=cs returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=blabla&language=cs")
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
    assert res.headers['content-type'].startswith('application/json'), res.headers
    json = res.json()
    assert 'message' in json, json


@http_check
def http_check_plzen_cs(session: requests.Session):
    """HTTP GET /city/v1/get?id=101748111&language=cs returns 200 and correct object"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=101748111&language=cs")
    assert_city_reply(res, 101748111, "Plzeň", "Plzeňský kraj", "CZ")


@http_check
def http_check_brno_de(session: requests.Session):
    """HTTP GET /city/v1/get?id=101748109&language=de returns 200 and correct object"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=101748109&language=de")
    assert_city_reply(res, 101748109, "Brünn", "Südmährische Region", "CZ")


@http_check
def http_check_graz_cs_extra_param(session: requests.Session):
    """HTTP GET /city/v1/get?id=1108839329&language=cs&extra=paramShouldBeIgnored returns 200 and correct object"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=1108839329&language=cs&extra=paramShouldBeIgnored")
    assert_city_reply(res, 1108839329, "Štýrský Hradec", "Štýrsko", "AT")


def assert_city_reply(res: requests.Response, expected_id, expected_city, expected_region, expected_country):
    assert res.status_code == 200, (res, res.text)
    assert res.headers['content-type'].startswith('application/json'), res.headers
    json = res.json()
    assert json.keys() == {'countryISO', 'id', 'isFeatured', 'name', 'regionName'}, json
    assert json['countryISO'] == expected_country, (expected_country, json)
    assert json['id'] == expected_id, (expected_id, json)
    assert type(json['isFeatured']) == bool, json  # Not yet in Elastic, check just type
    assert json['name'] == expected_city, (expected_city, json)
    assert json['regionName'] == expected_region, (expected_region, json)


def collect_stats(container, message, connections=None, latency_90p_ms=None, requests_per_s=None):
    docker_stats = container.stats(stream=False)
    stats = Stats(
        message,
        cpu_total_s=docker_stats['cpu_stats']['cpu_usage']['total_usage'] / 1000**3,  # docker stats are in nanosecs
        cpu_new_s=None,
        mem_usage_mb=docker_stats['memory_stats']['usage'] / 1024**2,
        mem_max_mb=docker_stats['memory_stats']['max_usage'] / 1024**2,
        requests_total=TOTAL_REQUESTS,
        requests_new=None,
        request_errors_total=TOTAL_REQUEST_ERRORS,
        request_errors_new=None,
        connections=connections,
        latency_90p_ms=latency_90p_ms,
        requests_per_s=requests_per_s,
    )
    if STATS:
        prev_stats: Stats = STATS[-1]
        stats.cpu_new_s = stats.cpu_total_s - prev_stats.cpu_total_s
        stats.requests_new = stats.requests_total - prev_stats.requests_total
        stats.request_errors_new = stats.request_errors_total - prev_stats.request_errors_total
    print(stats)
    STATS.append(stats)


def run_benchmark(container, connection_count):
    threads = min(connection_count, 4)  # count with 4 physical cores; wrk requires connections >= threads
    duration_s = 10
    process = run(['wrk', f'-c{connection_count}', f'-t{threads}', f'-d{duration_s}', '--latency',
                   f'{URL_PREFIX}/city/v1/get?id=101748111&language=cs'], check=True, capture_output=True, text=True)
    lines = process.stdout.splitlines()

    # Running 10s test @ http://127.0.0.1:8080/city/v1/get?id=101748111&language=cs
    #   1 threads and 50 connections
    #   Thread Stats   Avg      Stdev     Max   +/- Stdev
    #     Latency   142.80ms   31.56ms 302.00ms   76.92%
    #     Req/Sec   349.72     81.58   494.00     74.00%
    #   Latency Distribution
    #     50%  136.22ms
    #     75%  155.05ms
    #     90%  182.81ms
    #     99%  269.44ms
    #   3485 requests in 10.01s, 772.55KB read
    #   Non-2xx or 3xx responses: 25
    #   Socket errors: connect 3980, read 0, write 0, timeout 0
    # Requests/sec:    348.13
    # Transfer/sec:     77.17KB

    def match_line(pattern):
        for line in lines:
            m = re.fullmatch(pattern, line)
            if m:
                return m
        else:
            raise ValueError(f'Pattern "{pattern}" not found in lines:' + ''.join(f'\n"{l}"' for l in lines))

    matches = match_line(' +90% +([0-9.]+)(m?)s *')
    latency_90p_ms = float(matches.group(1))
    if matches.group(2) == '':
        latency_90p_ms *= 1000  # if the value is in seconds, multiply to get msecs

    requests_new = int(match_line(' +([0-9]+) requests in .* read').group(1))
    errors_new = 0

    try:
        matches = match_line(' +Non-2xx or 3xx responses: ([0-9]+) *')
    except ValueError:
        pass  # the line is not printed when there are no such errors
    else:
        errors_new += int(matches.group(1))

    try:
        matches = match_line(' +Socket errors: connect ([0-9]+), read ([0-9]+), write ([0-9]+), timeout ([0-9]+) *')
    except ValueError:
        pass  # the line is not printed when there are no such errors
    else:
        errors_new += sum(int(g) for g in matches.groups())

    global TOTAL_REQUESTS
    global TOTAL_REQUEST_ERRORS
    requests_new -= errors_new  # wrk reports errors into all requests, subtract because we want just OK ones.
    TOTAL_REQUESTS += requests_new
    TOTAL_REQUEST_ERRORS += errors_new

    requests_per_s = requests_new / duration_s
    collect_stats(container, 'Bench', connection_count, latency_90p_ms, requests_per_s)


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


def save_results(filename):
    payload = {'checks': CHECKS, 'stats': [asdict(s) for s in STATS]}
    with open(filename, 'w') as f:
        json.dump(payload, f)
    print(f'Results dumped to {filename}.')


if __name__ == '__main__':
    args = docopt(__doc__)
    if args['--local']:
        test_local()
    else:
        test_image(args['<docker-image>'], bench=not args['--no-bench'])
