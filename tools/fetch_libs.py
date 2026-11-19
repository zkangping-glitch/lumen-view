"""Install the pinned Windows runtime with pip's dependency and wheel handling."""
from pathlib import Path
import subprocess
import sys


def main():
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        print('This installer requires 64-bit Python 3.12 on Windows. For development use: pip install -e .')
        return 1
    root = Path(__file__).resolve().parent.parent
    return subprocess.call([
        sys.executable, '-m', 'pip', 'install', '--only-binary=:all:', '--upgrade',
        '--target', str(root / '.pylibs'), '-r', str(root / 'requirements.txt'),
    ])


if __name__ == '__main__':
    raise SystemExit(main())
