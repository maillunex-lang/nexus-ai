"""Register a reviewed OAuth public client from a trusted local shell."""
import sys
from .db import connection
from .oauth_pkce import validate_redirect_uri


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python -m nexus.register_oauth_client <client_id> <display_name> <exact_redirect_uri>")
    client_id, name, uri = sys.argv[1:]
    if not (3 <= len(client_id) <= 255 and 3 <= len(name) <= 200 and validate_redirect_uri(uri)):
        raise SystemExit("Invalid client parameters")
    with connection() as conn:
        conn.execute(
            "INSERT INTO oauth_clients(client_id,client_name,redirect_uris) VALUES (%s,%s,%s)",
            (client_id,name,[uri]),
        )
    print("Registered client:", client_id)


if __name__ == "__main__":
    main()
