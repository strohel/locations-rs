#!/usr/bin/env python3

"""
Benchmark the /v1/city/get endpoint using various implementations.

Usage:
  bench-closest.py [--runs=<n>]

Options:
  --runs=<n>    Number of runs to perform [default: 4].
"""
import os
from pathlib import Path
import subprocess

from docopt import docopt


IMAGE_BASE = 'gcr.io/strohel-goout-calendar/locations'


def main(runs):
    tags = (
        ('actix-v30', {}),
        ('rocket-v04', {'ROCKET_WORKERS': '16', 'ROCKET_KEEP_ALIVE': '0'}),
        ('rocket-v05-dev', {}),
    )

    script_path = Path(__file__)
    script_dir = script_path.parent.absolute()
    test_image = str(script_dir / 'test-image.py')
    render_tests = str(script_dir / 'render-tests.py')

    for i in range(1, runs + 1):
        for tag, env_overrides in tags:
            outfile = f'{tag}-{i}.checks.bench.json'
            if Path(outfile).exists():
                print(f'{outfile} exists, skipping this benchmark.')
                continue

            env = {**os.environ, **env_overrides}
            try:
                run([test_image, f'{IMAGE_BASE}:{tag}', '--check-bad-env', '--log-threads', '--bench-out', outfile],
                    check=True, env=env)
            except subprocess.CalledProcessError:
                print('Called process exited with non-zero exit status, but continuing.')

    run([render_tests])


# TODO: deduplicate
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


if __name__ == '__main__':
    args = docopt(__doc__)
    main(int(args['--runs']))
