"""Make the admin page's password hash (argon2) for MOJAWID_ADMIN_PASSWORD_HASH:

.venv/bin/python -m app.reports.hash_password
"""

import getpass

from argon2 import PasswordHasher


def main() -> None:
    password = getpass.getpass("Admin password: ")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters.")
    if getpass.getpass("Again: ") != password:
        raise SystemExit("They don't match.")
    print(PasswordHasher().hash(password))


if __name__ == "__main__":
    main()
