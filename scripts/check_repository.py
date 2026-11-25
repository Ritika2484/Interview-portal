"""Small dependency-free pre-commit check; filenames come from Git/pre-commit."""

import re
import sys
from pathlib import Path


def main():
    failures = []
    for name in sys.argv[1:]:
        path = Path(name)
        if path.name.startswith(".env") and path.name != ".env.example":
            failures.append(f"Environment file must not be committed: {name}")
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if re.search(r"^(<{7} |={7}$|>{7} )", text, re.MULTILINE):
                failures.append(f"Unresolved conflict marker: {name}")
    for failure in failures:
        print(failure)
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
