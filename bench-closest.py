#!/usr/bin/env python3

"""
Benchmark the /v1/city/closest endpoint.

Usage:
  bench-closest.py [--runs=<n>]

Options:
  --runs=<n>    Number of runs to perform [default: 2].
"""

from pathlib import Path
import subprocess

from docopt import docopt


def main(runs):
    endpoint_paths = {
        'praha-by-geometry': '/city/v1/closest?language=pl&lat=50.107&lon=14.574',
        'otice-by-geometry': '/city/v1/closest?language=pl&lat=49.915&lon=17.870',
        'otice-by-centroid': '/city/v1/closest?language=pl&lat=49.914&lon=17.877',
    }
    images = ['1rt-rs', '2rt-kt', '1rt-kt']

    script_dir = Path(__file__).parent.absolute()
    test_image = str(script_dir / 'test-image.py')
    render_tests = str(script_dir / 'render-tests.py')

    for i in range(1, runs + 1):
        for ep_type, path in endpoint_paths.items():
            Path(ep_type).mkdir(exist_ok=True)
            for image in images:
                outfile = f'{ep_type}/{image}-{i}.checks.bench.json'
                if Path(outfile).exists():
                    print(f'{outfile} exists, skipping this benchmark.')
                    continue

                try:
                    run([test_image, image, '--bench-url', path, '--bench-out', outfile], check=True)
                except subprocess.CalledProcessError:
                    print('Called process exited with non-zero exit status, but continuing.')

    html_lines = []
    for ep_type in endpoint_paths:
        run([render_tests], cwd=ep_type)
        html_lines.append(f'<a href="{ep_type}/bench-results.html">{ep_type}</a>')

    html = '<br>\n'.join(html_lines)
    with open('index.html', 'w') as f:
        f.write(html)


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
