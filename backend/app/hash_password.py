"""Print a bcrypt hash for BAW_PASSWORD_HASH.

    python -m app.hash_password
"""

from __future__ import annotations

import getpass
import sys

import bcrypt


def main() -> None:
    password = getpass.getpass("App password: ")
    if len(password) < 8:
        sys.exit("Use at least 8 characters.")
    if getpass.getpass("Repeat: ") != password:
        sys.exit("Passwords don't match.")
    print(bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())


if __name__ == "__main__":
    main()
