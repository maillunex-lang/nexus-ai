"""Create the initial owner from a local terminal, never through a public API."""
import getpass
import os
import sys

from .db import connection
from .identity import USERNAME, hash_password


def main():
    if len(sys.argv) != 2 or not USERNAME.fullmatch(sys.argv[1]):
        raise SystemExit("Usage: python -m nexus.bootstrap <lowercase-username>")
    username = sys.argv[1]
    password = os.environ.get("NEXUS_BOOTSTRAP_PASSWORD") or getpass.getpass("New owner password (14+ chars): ")
    hashed = hash_password(password)
    with connection() as conn:
        with conn.transaction():
            count = conn.execute("SELECT count(*) FROM user_roles WHERE role_id='owner'").fetchone()[0]
            if count:
                raise SystemExit("Owner already exists; bootstrap disabled")
            row = conn.execute("INSERT INTO users(username,password_hash) VALUES (%s,%s) RETURNING id", (username,hashed)).fetchone()
            conn.execute("INSERT INTO user_roles(user_id,role_id) VALUES (%s,'owner')", (row[0],))
    print("Owner account created:",username)


if __name__ == "__main__":
    main()
