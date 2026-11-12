"""Check that a running installation works end to end: web page, health, login, case list, search, details.

Run it after installing, updating or restoring. The password is read from standard input and is
never printed; neither is the login token.

    # the Docker stack over HTTPS, trusting Caddy's own certificate authority (Step 14.2)
    uv run python -m scripts.smoke_test --url https://localhost:8443 --ca-file caddy-root.crt --username analyst --password-stdin

    # the backend directly, from inside Docker (nothing installed on the host but Docker)
    docker compose --profile app run --rm -T backend python -m scripts.smoke_test --url http://backend:8000 --api-only --username analyst --password-stdin

Exit code 0 when every check passes, 1 otherwise.
"""

import argparse
import getpass
import ssl
import sys

import httpx

SEARCH = "murder conviction based only on circumstantial evidence"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="address of the web server (or of the backend, with --api-only)")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    parser.add_argument("--api-only", action="store_true", help="the URL is the backend: skip the web page check")
    parser.add_argument("--ca-file", help="trust this certificate authority as well, e.g. Caddy's own (Step 14.2)")
    parser.add_argument("--search", default=SEARCH, help="a search that should find at least one case (default: %(default)r)")
    args = parser.parse_args()
    # Certificates are always checked; --ca-file only adds an authority to trust.
    verify = ssl.create_default_context(cafile=args.ca_file) if args.ca_file else True
    password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass()

    failures = 0

    def check(name: str, ok: bool, detail: str = "") -> bool:
        nonlocal failures
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))
        return ok

    with httpx.Client(base_url=args.url.rstrip("/"), timeout=60, verify=verify) as client:
        if not args.api_only:
            page = client.get("/")
            check("web page", page.status_code == 200 and '<div id="root">' in page.text, f"HTTP {page.status_code}")

        health = client.get("/api/health")
        body = health.json() if health.status_code == 200 else {}
        check("health", body.get("status") == "ok" and body.get("database") == "ok", str(body or health.status_code))

        login = client.post("/api/auth/token", data={"username": args.username, "password": password})
        if not check("login", login.status_code == 200, f"HTTP {login.status_code}"):
            return 1
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

        me = client.get("/api/auth/me").json()
        check("who am I", me.get("username") == args.username, f"role {me.get('role')}, clearance {me.get('clearance')}")

        cases = client.get("/api/cases", params={"limit": 1}).json()
        if not check("case list", cases.get("total", 0) > 0, f"{cases.get('total')} cases visible"):
            return 1
        first = cases["items"][0]["display_id"]

        search = client.post("/api/search", json={"query": args.search, "limit": 5})
        result = search.json() if search.status_code == 200 else {}
        check("search", search.status_code == 200 and result.get("total_cases", 0) > 0,
              f"{result.get('total_cases')} cases, mode {result.get('mode')}")
        if result.get("mode") != "hybrid":
            print("      note: meaning-based search is off (embedding model missing?); keyword search only")

        detail = client.get(f"/api/cases/{first}")
        check("case details", detail.status_code == 200 and detail.json().get("display_id") == first, first)

        unauthorised = httpx.get(f"{args.url.rstrip('/')}/api/cases", timeout=30, verify=verify)
        check("login required", unauthorised.status_code == 401, f"HTTP {unauthorised.status_code} without a login")

    print("all checks passed" if failures == 0 else f"{failures} check(s) failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
