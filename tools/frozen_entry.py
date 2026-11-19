"""PyInstaller entry point kept outside the package for reliable imports."""

from lumenview.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
