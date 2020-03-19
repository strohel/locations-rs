#!/usr/bin/env python3

"""
Visualize benchmark results produced by test-image.py.

Usage:
  render-tests.py

Currently processes all *.checks.bench.json files in the current dir.
"""

import json
from glob import glob

try:
    from docopt import docopt
except ImportError as e:
    raise Exception('Some external dependencies not found, install them using: pip install -r requirements.txt') from e


def render():
    suffix = '.checks.bench.json'
    suites = {}
    for filename in glob(f'*{suffix}'):
        name = filename[:-len(suffix)]
        print(f'Loading {filename} as {name}.')
        with open(filename) as fp:
            suites[name] = json.load(fp)

    out_filename = 'bench-results.md'
    with open(out_filename, 'w') as out:
        render_checks(suites, out)
    print(f'Markdown output written to {out_filename}.')


def render_checks(suites, out):
    names = sorted(suites.keys())

    print(f'|Check|{"|".join(names)}|', file=out)
    print(f'|{"|".join(["---"] * (len(names) + 1))}|', file=out)

    per_impl_checks = {name: suite['checks'] for name, suite in suites.items()}
    check_names = sorted(set().union(*(checks.keys() for checks in per_impl_checks.values())))

    for check_name in check_names:
        values = [str(per_impl_checks[name][check_name]) for name in names]
        print(f'|{check_name}|{"|".join(values)}|', file=out)


if __name__ == '__main__':
    args = docopt(__doc__)
    render()
