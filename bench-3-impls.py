#!/usr/bin/env python3

"""
Benchmark the /v1/city/get endpoint using various implementations.

Usage:
  bench-closest.py [--runs=<n>]

Options:
  --runs=<n>    Number of runs to perform [default: 4].
"""

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess

from docopt import docopt


IMAGE_BASE = 'gcr.io/strohel-goout-calendar/locations'


def main(runs):
    tags = (
        # 'actix-v30-globales',
        # 'actix-v30-perworkeres',
        # 'rocket-v04-semiasync-noka',
        # 'rocket-v04-semiasync-nookapi',
        'rocket-v04-semiasync-okapi',
        # 'rocket-v04-perreqrt',
        # 'rocket-v04-perreqrtandes',
        'rocket-v04-perthreadrt',
    )

    script_path = Path(__file__)
    script_dir = script_path.parent.absolute()
    test_image = str(script_dir / 'test-image.py')
    render_tests = str(script_dir / 'render-tests.py')

    rocket_variants = [RocketParams(ka, wrkrs) for ka in (0, 5) for wrkrs in (16, 32, 64, 128, 256)]

    for i in range(1, runs + 1):
        for variant in rocket_variants:
            Path(str(variant)).mkdir(exist_ok=True)
            for tag in tags:
                outfile = f'{variant}/{tag}-{i}.checks.bench.json'

                env = {**os.environ,
                       'ROCKET_WORKERS': str(variant.workers), 'ROCKET_KEEP_ALIVE': str(variant.keep_alive)}
                try:
                    if Path(outfile).exists():
                        print(f'{outfile} exists, skipping this benchmark.')
                    else:
                        run([test_image, f'{IMAGE_BASE}:{tag}', '--check-bad-env', '--log-threads', '--bench-out',
                             outfile], check=True, env=env)
                except subprocess.CalledProcessError:
                    print('Called process exited with non-zero exit status, but continuing.')
                else:
                    # Create a symlink to per-tag results
                    symlink_path = Path(f'{tag}/{variant}-{i}.checks.bench.json')
                    if symlink_path.exists():
                        continue
                    Path(tag).mkdir(exist_ok=True)
                    symlink_path.symlink_to(f'../{outfile}')

    for cwd in (*tags, *rocket_variants):
        run([render_tests], cwd=str(cwd))


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


@dataclass
class RocketParams:
    keep_alive: int
    workers: int

    def __str__(self):
        return f'{self.keep_alive}-ka-{self.workers}-wrkrs'


if __name__ == '__main__':
    args = docopt(__doc__)
    main(int(args['--runs']))
