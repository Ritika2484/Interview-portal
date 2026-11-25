"""Create a local .env with generated credentials, without printing or overwriting secrets."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = root / ".env"
if destination.exists():
    raise SystemExit(".env already exists; it was not changed.")
content = (root / ".env.example").read_text(encoding="utf-8")
content = content.replace("replace-with-a-random-local-key-before-running", secrets.token_hex(32))
content = content.replace("replace-with-a-random-local-database-password", secrets.token_hex(24))
with destination.open("x", encoding="utf-8", newline="\n") as output:
    output.write(content)
print("Created .env with generated development-only credentials. Keep it out of Git.")
