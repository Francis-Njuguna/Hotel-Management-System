"""Create a private local Compose env file once, without printing its secrets."""

import os
import secrets
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("Usage: python deploy/new_env.py PATH_OUTSIDE_CHECKOUT")
destination = Path(sys.argv[1]).expanduser().resolve()
if Path(__file__).resolve().parents[1] in (destination, *destination.parents):
    raise SystemExit("Choose a private location OUTSIDE the checkout.")
# O_EXCL prevents accidental rotation on an existing deployment. On Windows the
# parent directory must already have a private ACL; POSIX mode is not an NTFS ACL.
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="ascii", newline="\n") as env:
    env.write(f"HMS_SECRET_KEY={secrets.token_hex(48)}\n")
    env.write(f"POSTGRES_PASSWORD={secrets.token_hex(32)}\n")
