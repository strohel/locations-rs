#!/usr/bin/env python3

"""
Benchmark the /v1/city/closest endpoint.
"""

from pathlib import Path
import subprocess


def main():
    endpoint_paths = {
        'polygon': '/city/v1/closest?language=pl&lat=50.107&lon=14.574',  # Praha
        'point': '/city/v1/closest?language=cs&lat=49.84&lon=12.92',  # Kozolupy
    }
    images = ['1rt-rs', '2rt-kt', '1rt-kt']
    test_image = str(Path(__file__).parent / 'test-image.py')

    for i in range(1, 3):
        for ep_type, path in endpoint_paths.items():
            for image in images:
                outfile = f'{ep_type}-{image}-{i}.checks.bench.json'
                if Path(outfile).exists():
                    print(f'{outfile} exists, skipping this benchmark.')
                    continue

                try:
                    run([test_image, image, '--bench-url', path, '--bench-out', outfile], check=True)
                except subprocess.CalledProcessError:
                    print('Called process exited with non-zero exit status, but continuing.')


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
    main()
