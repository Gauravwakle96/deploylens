"""Create local-only credentials once, without printing them."""

import secrets
from pathlib import Path

path = Path(".env")
if path.exists():
    print("Existing .env preserved")
else:
    path.write_text(
        "POSTGRES_PASSWORD=" + secrets.token_hex(24) + "\n"
        "ADMIN_TOKEN=" + secrets.token_hex(32) + "\n",
        encoding="utf-8",
    )
    print("Created ignored .env with local credentials")
