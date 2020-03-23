#!/usr/bin/env python3

"""
Visualize benchmark results produced by test-image.py.

Usage:
  render-tests.py

Currently processes all *.checks.bench.json files in the current dir.
"""

import json
from pathlib import Path

try:
    from docopt import docopt
    from marko.ext.gfm import gfm
    import pygal
except ImportError as e:
    raise Exception('Some external dependencies not found, install them using: pip install -r requirements.txt') from e


def render():
    suffix = '.checks.bench.json'
    suites = {}
    for filepath in Path('.').glob(f'*{suffix}'):
        name = filepath.name[:-len(suffix)]
        print(f'Loading {filepath} as {name}.')
        with open(filepath) as fp:
            suites[name] = json.load(fp)

    def sort_key(name):
        hardcoded_sort = ('vertx', 'ktor', 'http4k', 'rs')
        for i, hardcoded_name in enumerate(hardcoded_sort):
            if name.startswith(f'locations-{hardcoded_name}'):
                return i, name
        return len(hardcoded_sort), name

    names = sorted(suites.keys(), key=sort_key)

    figure_filenames = render_figures(names, suites)

    out_filename = Path('bench-results.md')
    with open(out_filename, 'w') as out:
        print(f'# Benchmark of {", ".join(names)}', file=out)

        notes_file = Path('notes.md')
        if notes_file.exists():
            print(f'Including {notes_file} in resulting Markdown.')
            with notes_file.open() as fp:
                out.write(fp.read())
        else:
            print(f'File {notes_file} does not exist, create it to include it in resulting Markdown.')

        print('## General Info & Checks', file=out)
        render_checks(names, suites, out)

        print('## Graphs', file=out)
        print('*The graphs are interactive, view the rendered HTML locally to enjoy it.*\n', file=out)
        for filename in figure_filenames:
            # Use HTML instead of Markdown image to specify the width
            print(f'<img type="image/svg+xml" src="{filename}" alt="{filename}" width="49%"/>', file=out)

    print(f'Markdown output written to {out_filename}.')

    render_html(out_filename, Path('bench-results.html'))


def render_checks(names, suites, out):
    print(f'|Check|{"|".join(names)}|', file=out)
    print(f'|{"|".join(["---"] * (len(names) + 1))}|', file=out)

    per_impl_checks = {name: suite['checks'] for name, suite in suites.items()}
    check_names = sorted(set().union(*(checks.keys() for checks in per_impl_checks.values())))

    def sanitize(value):
        if type(value) is float:
            value = float(f'{value:.3g}')  # round to 3 significant figures
            return str(int(value) if value >= 100 else value)
        return str(value)

    for check_name in check_names:
        values = [sanitize(per_impl_checks[name].get(check_name)) for name in names]
        if len(values) > 1 and len(set(values)) > 1:
            values = [f'**{value}**' for value in values]
        print(f'|{check_name}|{"|".join(values)}|', file=out)


FIGURE_FUNCS = []


def figure(func):
    """Simple decorator to mark a function as a figure generator."""
    FIGURE_FUNCS.append(func)
    return func


def render_figures(names, suites):
    filenames = []
    config = pygal.Config(legend_at_bottom=True)
    if len(names) <= 4:
        config.legend_at_bottom_columns = len(names)

    for figure_func in FIGURE_FUNCS:
        chart = figure_func(names, suites, config)
        filename = f'bench-results.{figure_func.__name__}.svg'
        chart.render_to_file(filename)
        filenames.append(filename)

    return filenames


@figure
def startup_time_figure(names, suites, config):
    chart = pygal.Bar(config)
    chart.title = 'Startup Time (s)'
    for name in names:
        chart.add(name, suites[name]['checks']['Startup time (to start responding) secs'])
    return chart


@figure
def errors_vs_connections_figure(names, suites, config):
    chart = pygal.Line(config)
    chart.title = 'Error Response Ratio vs. Connections (%)'
    connections_x_labels(chart, suites, skip=2)
    for name in names:
        chart.add(name, [100*s['request_errors_new']/(s['request_errors_new'] + s['requests_new'])
                         for s in suites[name]['stats'][2:]])
    return chart


@figure
def requests_vs_connections_figure(names, suites, config):
    chart = pygal.Line(config)
    chart.title = 'Success Requests per Second vs. Connections (Req/s)'
    connections_x_labels(chart, suites, skip=2)
    for name in names:
        chart.add(name, [s['requests_per_s'] for s in suites[name]['stats'][2:]])
    return chart


@figure
def latency_vs_connections_figure(names, suites, config):
    chart = pygal.Line(config)
    chart.title = '90th Percentile Latency vs. Connections (ms)'
    connections_x_labels(chart, suites, skip=2)
    for name in names:
        chart.add(name, [s['latency_90p_ms'] if s['requests_new'] else None for s in suites[name]['stats'][2:]])
    return chart


@figure
def max_mem_usage_figure(names, suites, config):
    chart = pygal.Line(config)
    chart.title = 'Max Memory Usage vs. Connections (MiB)'
    connections_x_labels(chart, suites)
    for name in names:
        chart.add(name, [s['mem_max_mb'] for s in suites[name]['stats']])
    return chart


@figure
def max_mem_usage_per_requests_figure(names, suites, config):
    chart = pygal.Line(config)
    chart.title = 'Max Memory Usage per Success Requests/s vs. Connections (MB-second/Req)'
    connections_x_labels(chart, suites, skip=2)
    for name in names:
        chart.add(name, [s['mem_max_mb']/s['requests_per_s'] if s['requests_per_s'] else None
                         for s in suites[name]['stats'][2:]])
    return chart


@figure
def cpu_figure(names, suites, config):
    chart = pygal.Line(config)
    chart.title = 'CPU Time per Round vs. Connections (CPU-seconds)'
    connections_x_labels(chart, suites, skip=2)
    for name in names:
        chart.add(name, [s['cpu_new_s'] for s in suites[name]['stats'][2:]])
    return chart


@figure
def cpu_per_request_figure(names, suites, config):
    chart = pygal.Line(config)
    chart.title = 'CPU Time per Success Request vs. Connections (CPU-milliseconds/Req)'
    connections_x_labels(chart, suites, skip=2)
    for name in names:
        chart.add(name, [1000*s['cpu_new_s']/s['requests_new'] if s['requests_new'] else None
                         for s in suites[name]['stats'][2:]])
    return chart


@figure
def cpu_vs_requests_figure(names, suites, config):
    chart = pygal.XY(config)
    chart.title = 'Cumulative CPU Usage vs. Cumulative Requests'
    chart.x_title = 'cumulative requests'
    chart.y_title = 'CPU-seconds'
    for name in names:
        chart.add(name, [(s['requests_total'], s['cpu_total_s']) if s['request_errors_total'] == 0 else None
                         for s in suites[name]['stats']])
    return chart


def connections_x_labels(chart, suites, skip=0):
    chart.x_labels = [f"{s['connections']} conn's" if s['connections'] else s['message']
                      for s in next(iter(suites.values()))['stats']][skip:]
    chart.x_label_rotation = -30


def render_html(md_file, html_file):
    with open(md_file) as in_fp, open(html_file, 'w') as out_fp:
        rs = in_fp.read()
        html = gfm(rs)
        # Replace <img> by <embed> for pygal interactivity, http://www.pygal.org/en/latest/documentation/web.html
        html = html.replace('<img', '<embed')
        out_fp.write(html)
    print(f'HTML output written to {html_file.resolve().as_uri()}.')


if __name__ == '__main__':
    args = docopt(__doc__)
    render()
