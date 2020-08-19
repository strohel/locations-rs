#!/usr/bin/env python3

"""
GoOut Locations MVP Docker image tester and benchmark.

Usage:
  test-image.py <docker-image> [options] [--http-checks=<list,of,groups>]
  test-image.py --local [--http-checks=<list,of,groups>]
  test-image.py --remote=<url-prefix> [--http-checks=<list,of,groups>]

Modes:
  <docker-image>    Test a Docker image, also perform benchmark by default.
  --local           Do not use Docker, don't run bench, perform test of service running on http://127.0.0.1:8080.
  --remote=<url>    Do not use Docker, don't run bench, perform test of service running on <url> prefix.

Options:
  --no-bench        Do not run benchmarks.
  --log-threads     Log what processes and threads run in the container.
  --bench-url=<p>   Local url (the path part) to use as benchmark [default: /city/v1/get?id=101748111&language=cs].
  --bench-out=<f>   Benchmark output file name. Defaults to `<docker-image>.checks[.bench].json`.
  --http-checks=<list,of,groups>    List of http check groups to execute [default: all].
"""

from collections import defaultdict
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
HTTP_CHECK_FUNCS = defaultdict(list)  # mapping from check type to list of checks
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
    latency_50p_ms: float
    latency_90p_ms: float
    latency_99p_ms: float
    requests_per_s: float


def test_image(image: str, bench: bool, log_threads_enabled: bool, bench_url: str, groups: list,
               bench_outfile: str = None):
    dockerc = docker.from_env()

    # check_doesnt_start_with_env(dockerc, image, 'Does not start without env variables', {})
    # check_doesnt_start_with_env(dockerc, image, 'Does not start with invalid ES address',
    #                             {'GOOUT_ELASTIC_HOST': '127.0.0.1', 'GOOUT_ELASTIC_PORT': '56789'})

    session = requests.Session()

    # 512 MB should be a conservative limit of something called a microservice.
    mem_limit = "512m"
    run_opts = dict(
        image=image,
        auto_remove=True,
        detach=True,
        ports={8080: 8080},
        mem_limit=mem_limit,
        memswap_limit=mem_limit,  # Set to the same value as mem_limit to disable swap.
        environment={key: os.environ[key] for key in ('GOOUT_ELASTIC_HOST', 'GOOUT_ELASTIC_PORT')},
    )

    if log_threads_enabled:
        log_threads(dockerc, session, run_opts, "4 online vCPUs, 4.0 soft CPU limit", cpuset_cpus="0-3", soft_cpus=4.0)
        log_threads(dockerc, session, run_opts, "4 online vCPUs, 1.0 soft CPU limit (benchmarked)", cpuset_cpus="0-3", soft_cpus=1.0)
        log_threads(dockerc, session, run_opts, "1 online vCPU, 1.0 soft CPU limit", cpuset_cpus="0", soft_cpus=1.0)

    with run_container(dockerc, run_opts) as container:
        print(f"Container started, to tail its logs: docker logs -f -t {container.id}")
        start = perf_counter()
        wait_for_container_ready(session)
        log_check("Startup time (to start responding) secs", perf_counter() - start)
        collect_stats(container, "After startup")

        log_check("Docker image size (MB)", container.image.attrs['Size'] / 1024**2)

        check(logs_on_startup, container)
        check(logs_each_request, container, session)
        perform_http_checks(session, groups)

        collect_stats(container, "After HTTP checks")

        connection_range = (1, 1, 1, 1, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048) if bench else ()
        for connection_count in connection_range:
            run_benchmark(container, connection_count, bench_url)

        # Do one last HTTP call to ensure container is still alive and ready
        http_check_plzen_cs(session)

    if not bench_outfile:
        sane_name = re.sub('[^a-z0-9]+', '-', image)
        bench_outfile = f'{sane_name}.checks{".bench" if bench else ""}.json'
    save_results(bench_outfile)


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


def log_threads(dockerc, session, run_opts, message, cpuset_cpus, soft_cpus):
    container = dockerc.containers.run(cpuset_cpus=cpuset_cpus, nano_cpus=int(soft_cpus * 10**9), **run_opts)
    try:
        wait_for_container_ready(session)
        out = container.top(ps_args='-L -o pid,comm')

        threads = defaultdict(lambda: defaultdict(int))
        for pid, thread_cmd in out['Processes']:
            threads[pid][thread_cmd] += 1
        processes = [', '.join((f'{n}✕' if n > 1 else '') + cmd for cmd, n in cnt.items()) for cnt in threads.values()]

        log_check(f'Threads with {message}','<br>'.join(processes))
    finally:
        container.kill()


@contextmanager
def run_container(dockerc: docker.DockerClient, run_opts):
    # Give only 1.5s of CPU-core-time per each wall clock second. (can still run in parallel). Lets the rest of the
    # system breathe and better simulates Kubernetes environment (which uses the same method of capping CPU).
    nano_cpus = int(1.5 * 10**9)
    cpuset_cpus = "0-3"  # Assign 4 logical CPUs to the container to simulate our real cluster.

    container = dockerc.containers.run(cpuset_cpus=cpuset_cpus, nano_cpus=nano_cpus, **run_opts)
    stopped = False
    try:
        yield container
    except ContainerDied as e:
        log_check('Stops gracefully', f'Very Bad, probably died after {e.connections} connections')
        stopped = True
    finally:
        if stopped:
            return
        timeout = 15
        start = perf_counter()
        container.stop(timeout=timeout)
        dur = perf_counter() - start
        log_check('Stops gracefully', f'Good, in {dur:.1f}s' if dur < timeout else f'Bad, did not stop in {dur:.1f}s')


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


def test_local(groups):
    with requests.Session() as session:
        perform_http_checks(session, groups)


def perform_http_checks(session, groups):
    global TOTAL_REQUESTS
    for group in groups:
        if group not in HTTP_CHECK_FUNCS:
            raise ValueError(f'HTTP check group {group} not known, available ones: {list(HTTP_CHECK_FUNCS.keys())}.')
        for func in HTTP_CHECK_FUNCS[group]:
            check(func, session)
            TOTAL_REQUESTS += 1


def http_check(group):
    """Simple decorator to mark a function as an HTTP check."""
    def wrapper(func):
        HTTP_CHECK_FUNCS[group].append(func)
        return func
    return wrapper


@http_check('get')
def http_check_root(session: requests.Session):
    """HTTP GET / returns 200 or 404"""
    res = session.get(URL_PREFIX + "/")
    assert res.status_code in (200, 404), (res, res.text)


@http_check('get')
def http_check_nonexistent_path(session: requests.Session):
    """HTTP GET /fnhjkdniudsancyne returns 404"""
    res = session.get(URL_PREFIX + "/fnhjkdniudsancyne")
    assert res.status_code == 404, (res, res.text)


@http_check('get')
def http_check_no_params(session: requests.Session):
    """HTTP GET /city/v1/get returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get")
    assert_error_reply(res, 400)


@http_check('get')
def http_check_just_id_param(session: requests.Session):
    """HTTP GET /city/v1/get?id=123 returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=123")
    assert_error_reply(res, 400)


@http_check('get')
def http_check_invalid_id(session: requests.Session):
    """HTTP GET /city/v1/get?id=blabla&language=cs returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=blabla&language=cs")
    assert_error_reply(res, 400)


@http_check('get')
def http_check_just_language_param(session: requests.Session):
    """HTTP GET /city/v1/get?language=cs returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get?language=cs")
    assert_error_reply(res, 400)


@http_check('get')
def http_check_nonexistent_city_id(session: requests.Session):
    """HTTP GET /city/v1/get?id=123&language=cs returns 404 (this does not exist) with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=123&language=cs")
    assert_error_reply(res, 404)


def assert_error_reply(res: requests.Response, expected_code):
    assert res.status_code == expected_code, (expected_code, res, res.text)
    assert res.headers.get('content-type', '').startswith('application/json'), res.headers
    json = res.json()
    assert 'message' in json, json
    print(json['message'] + ': ', end='')


@http_check('get')
def http_check_plzen_cs(session: requests.Session):
    """HTTP GET /city/v1/get?id=101748111&language=cs returns 200 and correct object"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=101748111&language=cs")
    assert_city_reply(res, 101748111, "Plzeň", "Plzeňský kraj", "CZ", True)


@http_check('get')
def http_check_praha_en(session: requests.Session):
    """HTTP GET /city/v1/get?id=101748113&language=cs returns 200 and correct object"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=101748113&language=en")
    assert_city_reply(res, 101748113, "Prague", "Praha", "CZ", True)


@http_check('get')
def http_check_brno_de(session: requests.Session):
    """HTTP GET /city/v1/get?id=101748109&language=de returns 200 and correct object"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=101748109&language=de")
    assert_city_reply(res, 101748109, "Brünn", "Südmährische Region", "CZ", True)


@http_check('get')
def http_check_graz_cs_extra_param(session: requests.Session):
    """HTTP GET /city/v1/get?id=101748063&language=cs&extra=paramShouldBeIgnored returns 200 and correct object"""
    res = session.get(URL_PREFIX + "/city/v1/get?id=101748063&language=cs&extra=paramShouldBeIgnored")
    assert_city_reply(res, 101748063, "Štýrský Hradec", "Štýrsko", "AT", False)


def assert_city_reply(res: requests.Response, expected_id, expected_city, expected_region, expected_country,
                      expected_is_featured=None):
    assert_ok_json_reply(res)
    assert_city_payload(res.json(), expected_id, expected_city, expected_region, expected_country, expected_is_featured)


def assert_ok_json_reply(res: requests.Response):
    assert res.status_code == 200, (res, res.text)
    assert res.headers['content-type'].startswith('application/json'), res.headers


def assert_city_payload(json, expected_id, expected_city, expected_region, expected_country, expected_is_featured):
    assert json.keys() == {'countryIso', 'id', 'isFeatured', 'name', 'regionName'}, json
    assert json['countryIso'] == expected_country, (expected_country, json)
    assert json['id'] == expected_id, (expected_id, json)
    assert json['isFeatured'] == expected_is_featured, (expected_is_featured, json)
    assert json['name'] == expected_city, (expected_city, json)
    assert json['regionName'] == expected_region, (expected_region, json)


@http_check('featured')
def http_check_featured_no_lang(session: requests.Session):
    """HTTP GET /city/v1/featured returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/featured")
    assert_error_reply(res, 400)


@http_check('featured')
def http_check_featured_invalid_lang(session: requests.Session):
    """HTTP GET /city/v1/featured?language=invalid returns 400 with error JSON with message"""
    res = session.get(URL_PREFIX + "/city/v1/featured?language=invalid")
    assert_error_reply(res, 400)


@http_check('featured')
def http_check_featured_cs(session: requests.Session):
    """HTTP GET /city/v1/featured?language=cs returns 200 and correct list of cities"""
    res = session.get(URL_PREFIX + "/city/v1/featured?language=cs")
    cities = assert_cities_reply(res, 10, 10)
    names = [c['name'] for c in cities]
    assert names == [
        "Praha", "Brno", "Ostrava", "Plzeň", "Berlín", "Varšava", "Krakov", "Vratislav", "Poznaň", "Bratislava"], names
    assert_city_payload(cities[0], 101748113, "Praha", "Hlavní město Praha", "CZ", True)


@http_check('featured')
def http_check_featured_sk(session: requests.Session):
    """HTTP GET /city/v1/featured?language=sk returns 200 and correct list of cities"""
    res = session.get(URL_PREFIX + "/city/v1/featured?language=sk")
    cities = assert_cities_reply(res, 10, 10)
    names = [c['name'] for c in cities]
    assert names == [
        "Bratislava", "Praha", "Brno", "Ostrava", "Plzeň", "Berlín", "Varšava", "Krakov", "Vroclav", "Poznaň"], names


def assert_cities_reply(res, min_len, max_len):
    """Assert correct 'cities' response, return cities array."""
    assert_ok_json_reply(res)
    json = res.json()

    assert json.keys() == {'cities'}, json
    cities = json['cities']
    assert type(cities) == list, json
    assert min_len <= len(cities) <= max_len, (min_len, max_len, json)
    return cities


@http_check('search')
def http_check_search_brunn(session: requests.Session):
    """HTTP GET /city/v1/search?language=de&query=Brno returns 200 and just Brünn"""
    res = session.get(URL_PREFIX + "/city/v1/search?language=de&query=Brno")
    cities = assert_cities_reply(res, 0, 10)
    names = [c['name'] for c in cities]
    assert names == ['Brünn'], names


@http_check('search')
def http_check_search_kremze_diacritics(session: requests.Session):
    """HTTP GET /city/v1/search?language=cs&query=křemže returns 200 and CZ city first"""
    res = session.get(URL_PREFIX + "/city/v1/search?language=cs&query=křemže")
    cities = assert_cities_reply(res, 0, 10)
    names = [c['name'] for c in cities]
    assert names == ['Křemže', 'Kremže'], names  # assert that correct diacritics boost match


@http_check('search')
def http_check_search_kremze_ascii(session: requests.Session):
    """HTTP GET /city/v1/search?language=cs&query=kremze returns 200 and AT city first"""
    res = session.get(URL_PREFIX + "/city/v1/search?language=cs&query=kremze")
    cities = assert_cities_reply(res, 0, 10)
    names = [c['name'] for c in cities]
    assert names == ['Kremže', 'Křemže'], names  # assert that ascii-only match orders by population


@http_check('search')
def http_check_search_kremze_diacritics_in_at(session: requests.Session):
    """HTTP GET /city/v1/search?language=cs&query=křemže&countryIso=at returns 200 and AT city only"""
    res = session.get(URL_PREFIX + "/city/v1/search?language=cs&query=křemže&countryIso=AT")
    cities = assert_cities_reply(res, 0, 10)
    names = [c['name'] for c in cities]
    assert names == ['Kremže'], names


@http_check('closest')
def http_check_closest_invalid_no_lang(session: requests.Session):
    """HTTP GET /city/v1/closest returns 400"""
    res = session.get(URL_PREFIX + "/city/v1/closest")
    assert_error_reply(res, 400)


@http_check('closest')
def http_check_closest_invalid_lat_only(session: requests.Session):
    """HTTP GET /city/v1/closest?language=cs&lat=50 returns 400"""
    res = session.get(URL_PREFIX + "/city/v1/closest?language=cs&lat=50")
    assert_error_reply(res, 400)


@http_check('closest')
def http_check_closest_invalid_lon_only(session: requests.Session):
    """HTTP GET /city/v1/closest?language=cs&lon=14 returns 400"""
    res = session.get(URL_PREFIX + "/city/v1/closest?language=cs&lon=14")
    assert_error_reply(res, 400)


@http_check('closest')
def http_check_closest_invalid_lat(session: requests.Session):
    """HTTP GET /city/v1/closest?language=cs&lat=-90.3&lon=14 returns 400"""
    res = session.get(URL_PREFIX + "/city/v1/closest?language=cs&lat=-90.3&lon=14")
    assert_error_reply(res, 400)


@http_check('closest')
def http_check_closest_invalid_lon(session: requests.Session):
    """HTTP GET /city/v1/closest?language=cs&lat=50&lon=192 returns 400"""
    res = session.get(URL_PREFIX + "/city/v1/closest?language=cs&lat=50&lon=192")
    assert_error_reply(res, 400)


@http_check('closest')
def http_check_closest_lat_lon_kozolupy(session: requests.Session):
    """HTTP GET /city/v1/closest?language=cs&lat=49.84&lon=12.92 returns 200 Kozolupy"""
    res = session.get(URL_PREFIX + "/city/v1/closest?language=cs&lat=49.84&lon=12.92")
    assert_city_reply(res, 1125935959, "Horní Kozolupy", "Plzeňský kraj", "CZ", False)


@http_check('closest')
def http_check_closest_lat_lon_tricky_cernak(session: requests.Session):
    """HTTP GET /city/v1/closest?language=pl&lat=50.107&lon=14.574 returns 200 Praha (even tho Hostavice are closer)"""
    res = session.get(URL_PREFIX + "/city/v1/closest?language=pl&lat=50.107&lon=14.574")
    assert_city_reply(res, 101748113, "Praga", "Praga", "CZ", True)


@http_check('closest')
def http_check_closest_geoip_praha(session: requests.Session):
    """HTTP GET /city/v1/closest?language=de + 50,14 Fastly headers returns 200 Praha"""
    headers = {
        "Fastly-Geo-Lat": "50",
        "Fastly-Geo-Lon": "14",
    }
    res = session.get(URL_PREFIX + "/city/v1/closest?language=de", headers=headers)
    # This should be Praha, because GeoIP lookups use only featured cities.
    assert_city_reply(res, 101748113, "Prag", "Prag", "CZ", True)


@http_check('closest')
def http_check_closest_lang_fallback(session: requests.Session):
    """HTTP GET /city/v1/closest?language=de returns 200 Berlin (lang fallback)"""
    res = session.get(URL_PREFIX + "/city/v1/closest?language=de")
    assert_city_reply(res, 101909779, "Berlin", "Berlin", "DE", True)


@http_check('closest')
def http_check_closest_geoip_invalid(session: requests.Session):
    """HTTP GET /city/v1/closest?language=pl + 0,0 Fastly headers returns 200 Warszava (lang fallback)"""
    headers = {
        "Fastly-Geo-Lat": "0",
        "Fastly-Geo-Lon": "0",
    }
    res = session.get(URL_PREFIX + "/city/v1/closest?language=pl", headers=headers)
    # This should be Bratislava due to lang fallback, because 0, 0 coords from Fastly are special.
    assert_city_reply(res, 101752777, "Warszawa", "Mazowieckie", "PL", True)


@http_check('associatedFeatured')
def http_check_associated_featured_graz(session: requests.Session):
    """HTTP GET /city/v1/associatedFeatured?id=101748063&language=cs (Graz) returns 200 and Bratislava"""
    res = session.get(URL_PREFIX + "/city/v1/associatedFeatured?id=101748063&language=cs")
    assert_city_reply(res, 1108800123, "Bratislava", "Bratislavský kraj", "SK", True)


@http_check('associatedFeatured')
def http_check_associated_featured_praha(session: requests.Session):
    """HTTP GET /city/v1/associatedFeatured?id=101748113&language=pl (Praha) returns 200 and Praha itself"""
    res = session.get(URL_PREFIX + "/city/v1/associatedFeatured?id=101748113&language=pl")
    assert_city_reply(res, 101748113, "Praga", "Praga", "CZ", True)


@http_check('associatedFeatured')
def http_check_associated_featured_invalid(session: requests.Session):
    """HTTP GET /city/v1/associatedFeatured?id=123456&language=en (invalid id) returns 404"""
    res = session.get(URL_PREFIX + "/city/v1/associatedFeatured?id=123456&language=en")
    assert_error_reply(res, 404)


@dataclass
class ContainerDied(Exception):
    connections: int = None


def collect_stats(container, message, connections=None, latency_50p_ms=None, latency_90p_ms=None, latency_99p_ms=None,
                  requests_per_s=None):
    try:
        docker_stats = container.stats(stream=False)
    except docker.errors.NotFound as e:
        raise ContainerDied(connections) from e

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
        latency_50p_ms=latency_50p_ms,
        latency_90p_ms=latency_90p_ms,
        latency_99p_ms=latency_99p_ms,
        requests_per_s=requests_per_s,
    )
    if STATS:
        prev_stats: Stats = STATS[-1]
        stats.cpu_new_s = stats.cpu_total_s - prev_stats.cpu_total_s
        stats.requests_new = stats.requests_total - prev_stats.requests_total
        stats.request_errors_new = stats.request_errors_total - prev_stats.request_errors_total
    print(stats)
    STATS.append(stats)


def run_benchmark(container, connection_count, bench_url):
    threads = min(connection_count, 4)  # count with 4 physical cores; wrk requires connections >= threads
    duration_s = 10
    timeout_s = duration_s + 5
    process = run(['wrk', f'-c{connection_count}', f'-t{threads}', f'-d{duration_s}', '--latency',
                   f'--timeout={timeout_s}', f'{URL_PREFIX}{bench_url}'], check=True, capture_output=True, text=True)
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

    def match_latency(percentile):
        matches = match_line(f' +{percentile}% +([0-9.]+)([mu]?)s *')
        latency_ms = float(matches.group(1))
        if matches.group(2) == '':
            latency_ms *= 1000  # if the value is in seconds, multiply to get msecs
        if matches.group(2) == 'u':
            latency_ms /= 1000  # if the value is in microseconds, divide to get msecs
        return latency_ms

    latency_50p_ms = match_latency(50)
    latency_90p_ms = match_latency(90)
    latency_99p_ms = match_latency(99)

    requests_new = int(match_line(' +([0-9]+) requests in .* read').group(1))

    try:
        matches = match_line(' +Non-2xx or 3xx responses: ([0-9]+) *')
    except ValueError:
        request_errors_new = 0  # the line is not printed when there are no such errors
    else:
        request_errors_new = int(matches.group(1))

    try:
        matches = match_line(' +Socket errors: connect ([0-9]+), read ([0-9]+), write ([0-9]+), timeout ([0-9]+) *')
    except ValueError:
        other_errors_new = 0  # the line is not printed when there are no such errors
    else:
        assert int(matches[4]) == 0, ('Timeout errors can be included in Non-2/3xx, prevent double-count.', process.stdout)
        other_errors_new = sum(int(g) for g in matches.groups())

    global TOTAL_REQUESTS
    global TOTAL_REQUEST_ERRORS
    requests_new -= request_errors_new  # wrk reports HTTP status errors into all requests, subtract because we want just OK ones.
    TOTAL_REQUESTS += requests_new
    TOTAL_REQUEST_ERRORS += request_errors_new + other_errors_new

    requests_per_s = requests_new / duration_s
    collect_stats(container, 'Bench', connection_count, latency_50p_ms, latency_90p_ms, latency_99p_ms, requests_per_s)


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
    if args['--http-checks'] == 'all':
        groups = list(HTTP_CHECK_FUNCS.keys())
    else:
        groups = args['--http-checks'].split(',')

    if args['--local']:
        test_local(groups)
    elif args['--remote']:
        URL_PREFIX = args['--remote']
        test_local(groups)
    else:
        test_image(args['<docker-image>'], bench=not args['--no-bench'], log_threads_enabled=args['--log-threads'],
                   bench_url=args['--bench-url'], groups=groups, bench_outfile=args['--bench-out'])
