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

    out_filename = Path('bench-results.md')
    with open(out_filename, 'w') as out:
        render_checks(suites, out)
    print(f'Markdown output written to {out_filename}.')

    render_html(out_filename, Path('bench-results.html'))


def render_checks(suites, out):
    names = sorted(suites.keys())

    print(f'|Check|{"|".join(names)}|', file=out)
    print(f'|{"|".join(["---"] * (len(names) + 1))}|', file=out)

    per_impl_checks = {name: suite['checks'] for name, suite in suites.items()}
    check_names = sorted(set().union(*(checks.keys() for checks in per_impl_checks.values())))

    for check_name in check_names:
        values = [str(per_impl_checks[name][check_name]) for name in names]
        print(f'|{check_name}|{"|".join(values)}|', file=out)


def render_html(md_file, html_file):
    with open(md_file) as in_fp, open(html_file, 'w') as out_fp:
        rs = in_fp.read()
        html = gfm(rs)
        out_fp.write(html)
    print(f'HTML output written to {html_file.resolve().as_uri()}.')


if __name__ == '__main__':
    args = docopt(__doc__)
    render()
