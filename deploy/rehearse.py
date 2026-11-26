"""Opt-in, disposable LOCAL Compose drill. Run: py -3 deploy/rehearse.py --run

No operator credentials, input archives, existing project names or remote targets.
pg_dump/pg_restore is logical recovery; the separate pg_waldump check is not PITR.
"""

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from http.cookies import SimpleCookie


ROOT = Path(__file__).resolve().parents[1]
DB = "hms_rehearsal"
API = "/api/v1/"
ONEOFF = ("run", "--rm", "--no-deps", "-T", "api")
ADMIN = ("exec", "-T", "--user", "postgres", "db")
UP = ("up", "-d", "--wait", "--wait-timeout", "240")

def synthetic_png():
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    pixel = b"\0" + secrets.token_bytes(3)  # filter byte + one RGB pixel, no source photo
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(pixel)) + chunk(b"IEND", b""))


class Failure(Exception):
    """Only operator-safe messages go here. Never echo docker output or HTTP bodies."""


def require(condition, message):
    if not condition:
        raise Failure(message)


def note(message):
    print(message, flush=True)


def run(args, env, cwd, *, data=None, src=None, dst=None, timeout=300):
    # Do not use text mode, PowerShell redirection, check=True, or inherit stdin.
    try:
        r = subprocess.run(args, cwd=cwd, env=env, input=data,
                           stdin=None if data is not None else (src or subprocess.DEVNULL),
                           stdout=dst or subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Failure(f"Docker command exceeded its {timeout}s timeout.") from None
    if r.returncode:
        err = r.stderr.lower()
        hints = ((b"port is already allocated", "loopback port already in use"),
                 (b"ports are not available", "loopback port unavailable"),
                 (b"no matching distribution", "pinned package/wheel unavailable"),
                 (b"no space left", "Docker storage is full"), (b"unauthorized", "registry authentication failed"),
                 (b"failed to resolve", "image/registry resolution failed"),
                 (b"unhealthy", "service did not pass its health check"),
                 (b"didn't complete", "one-shot migration did not complete"),
                 (b"permission denied", "permission denied"), (b"pg_restore: error", "database restore rejected"),
                 (b"cannot connect", "Docker Engine not reachable"))
        why = next((msg for token, msg in hints if token in err), "see the current stage; raw output withheld")
        raise Failure(f"Docker exit {r.returncode}: {why}.")
    return r.stdout or b""


def high_port(exclude=0):
    for _ in range(100):
        port = 49152 + secrets.randbelow(16384)
        if port != exclude:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    pass
    raise Failure("Cannot allocate a free high loopback port.")


class Project:
    def __init__(self, docker, env, work, name, port):
        self.name, self.port, self.work = name, port, work
        origin = f"http://127.0.0.1:{port}"
        self.cmd = [*docker, "compose", "--env-file", str(work / "empty.env"), "-f", str(ROOT / "compose.yaml"), "-p", name]
        self.env = dict(env, HMS_SECRET_KEY=secrets.token_hex(48), POSTGRES_PASSWORD=secrets.token_hex(32),
                        POSTGRES_DB=DB, POSTGRES_USER="hms_rehearsal_app", POSTGRES_HOST="db", POSTGRES_PORT="5432",
                        HMS_HTTP_PORT=str(port), HMS_PUBLIC_URL=origin, HMS_CSRF_TRUSTED_ORIGINS=origin,
                        HMS_ALLOWED_HOSTS="127.0.0.1", HMS_DEBUG="0", HMS_SECURE_COOKIES="0", HMS_EMAIL_HOST="")

    def compose(self, *args, **kwargs):
        return run([*self.cmd, *args], self.env, self.work, **kwargs)

    def validate(self):
        # Never display this JSON: Compose expands secrets. Refuse shared resources.
        cfg = json.loads(self.compose("config", "--format", "json"))
        require(cfg["name"] == self.name and set(cfg["services"]) == {"api", "db", "web", "migrate"}, "Unexpected stack layout.")
        for kind in ("volumes", "networks"):
            for key, obj in cfg[kind].items():
                require(not obj.get("external") and obj["name"] == f"{self.name}_{key}", "Refusing shared volume/network.")
        for service, spec in cfg["services"].items():
            require(not spec.get("container_name") and (service == "db" or not spec.get("image") or
                    spec["image"] == f"{self.name}-{service}"), "Refusing fixed container or shared build tag.")
            ports = spec.get("ports", [])
            if service == "web":
                require(len(ports) == 1 and ports[0].get("host_ip") == "127.0.0.1" and
                        str(ports[0]["published"]) == str(self.port) and ports[0]["target"] == 8080, "Unsafe web publication.")
            else:
                require(not ports, "Unexpected API/database publication.")
            for mount in spec.get("volumes", []):
                if mount["type"] == "bind":
                    require(service == "db" and mount.get("read_only") and mount["target"] in {
                        "/etc/hms-pg_hba.conf", "/docker-entrypoint-initdb.d/10-bootstrap.sql"}, "Unexpected host bind mount.")

    def sql(self, text):
        return self.compose(*ADMIN, "psql", "-XAtq", "-v", "ON_ERROR_STOP=1", "-d", DB, data=text.encode()).decode().strip()

    def snapshot(self):
        return json.loads(self.compose(*ONEOFF, "python", "manage.py", "shell", "-v", "0",
                                       data=(ROOT / "deploy/snapshot_check.py").read_bytes()))

    def web(self):
        self.compose(*UP, "web")
        require(self.compose("port", "web", "8080").strip() == f"127.0.0.1:{self.port}".encode(), "Wrong web endpoint.")


class Client:
    """One browser identity, fixed loopback origin, no proxies or redirects."""
    def __init__(self, port):
        self.port, self.cookies = port, {}

    def request(self, path, body=None, mime="application/json", expect=(200,)):
        headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items())}
        method = "GET" if body is None else "POST"
        if body is not None:
            headers.update({"Origin": f"http://127.0.0.1:{self.port}", "Content-Type": mime,
                            "X-CSRFToken": self.cookies.get("csrftoken", "")})
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            conn.request(method, path, body=body, headers=headers)
            r = conn.getresponse()
            for name, value in r.getheaders():
                if name.lower() == "set-cookie":
                    self.cookies.update({k: v.value for k, v in SimpleCookie(value).items()})
            content = r.read(4 * 1024 * 1024)
            endpoint = re.sub(r"(?:protected-media|media)/.*", "media/[key]", path)
            require(r.status in expect, f"{method} {endpoint}: HTTP {r.status}, expected {expect}.")
            return content, r.headers.get_content_type()
        finally:
            conn.close()

    def api(self, path, payload=None, expect=(200,)):
        return json.loads(self.request(API + path, payload, expect=expect)[0])

    def login(self, name, passwords):
        require(self.api("auth/me/")["user"] is None and self.cookies.get("csrftoken"), "Missing anonymous CSRF session.")
        user = self.api("auth/login/", {"username": name, "password": passwords[name]})["user"]
        require(user["username"] == name and self.cookies.get("sessionid"), "Staff session was not established.")
        return self


def seed(project, passwords):
    # Password to stdin only, not in argv, shell interpolation, image or console.
    project.compose("exec", "-T", "api", "python", "-c",
                    "import os,sys; os.environ['DJANGO_SUPERUSER_PASSWORD']=sys.stdin.read(); "
                    "os.execv(sys.executable,[sys.executable,'manage.py','createsuperuser','--noinput',"
                    "'--username','drill-admin','--email','admin@synthetic.invalid'])", data=passwords["drill-admin"].encode())
    admin = Client(project.port).login("drill-admin", passwords)
    for name, role in (("drill-kitchen", "Restaurant Staff"), ("drill-finance", "Accountant")):
        admin.api("staff/", {"username": name, "role": role, "email": name + "@synthetic.invalid",
                            "password": passwords[name]}, expect=(201,))
    kitchen = Client(project.port).login("drill-kitchen", passwords)
    finance = Client(project.port).login("drill-finance", passwords)
    boundary = secrets.token_hex(20)
    parts = [f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}'.encode() for k, v in {
        "name": "SYNTHETIC restore meal", "category": "Drill only", "price": "12.35", "available": "true"}.items()]
    parts.append(b'Content-Disposition: form-data; name="image"; filename="synthetic.png"\r\nContent-Type: image/png\r\n\r\n' + synthetic_png())
    marker = b"--" + boundary.encode()
    body = b"".join(marker + b"\r\n" + part + b"\r\n" for part in parts) + marker + b"--\r\n"
    item = json.loads(kitchen.request(API + "menu-items/", body, f"multipart/form-data; boundary={boundary}", (201,))[0])
    match = re.fullmatch(r"/api/v1/media/(menu/[A-Za-z0-9_-]+\.jpg)", item["image"])
    require(match, "Upload did not produce the expected private menu-image URL.")
    order = kitchen.api("orders/", {"items": [{"menu_item": item["id"], "quantity": 2}]}, (201,))
    for state in ("confirmed", "preparing", "ready", "served"):
        kitchen.api(f"orders/{order['id']}/transition/", {"status": state})
    invoices = finance.api("invoices/")
    require(invoices["count"] == 1 and invoices["results"][0]["total"] == "24.70", "Fixture serve-and-post mismatch.")
    receipt = finance.api(f"invoices/{invoices['results'][0]['id']}/payments/",
                          {"method": "cash", "reference": "SYNTHETIC-DRILL-NO-FUNDS", "amount": "10.00"}, (201,))
    require(bool(receipt["receipt_number"]), "Synthetic tender did not produce a receipt.")
    return match[1], receipt["id"], kitchen, finance


def check_http(project, key, receipt_id, kitchen, finance):
    anon = Client(project.port)
    html, mime = anon.request("/")
    asset = re.search(rb'<script\b[^>]*\bsrc="(/assets/[A-Za-z0-9_.-]+\.js)"', html)
    require(mime == "text/html" and b'id="root"' in html and asset, "Built Vite shell or entry point is missing.")
    script, mime = anon.request(asset[1].decode("ascii"))
    require(script and "javascript" in mime, "Vite entry point is missing or returned HTML.")
    require(anon.api("auth/me/")["user"] is None, "Anonymous browser was not anonymous.")
    images = []
    for prefix in (API + "media/", "/protected-media/"):
        data, mime = kitchen.request(prefix + key)
        require(mime == "image/jpeg" and data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"), "Authorized image is not JPEG.")
        images.append(hashlib.sha256(data).hexdigest())
        for client, codes in ((finance, (403, 404)), (anon, (401, 403))):
            denied, mime = client.request(prefix + key, expect=codes)
            require(not mime.startswith("image/") and data not in denied, "Denied response contained an image.")
    require(images[0] == images[1], "Protected URLs returned different image bytes.")
    kitchen.request("/media/" + key, expect=(404,))
    receipt = finance.api(f"payments/{receipt_id}/")
    require(receipt["amount"] == "10.00" and receipt["reference"] == "SYNTHETIC-DRILL-NO-FUNDS", "Fixture receipt mismatch.")
    return images[0], receipt["receipt_number"]


def rehearse(src, dst, work):
    passwords = {name: secrets.token_urlsafe(32) for name in ("drill-admin", "drill-kitchen", "drill-finance")}
    note("1/6 Build and cold-start source (image download/build can take several minutes).")
    src.compose("build", "api", "migrate", "web", timeout=1800)
    src.web()
    note("2/6 Create synthetic staff, private image, meal posting and partial test tender through the API.")
    start_lsn = src.sql("SELECT pg_current_wal_lsn();")
    key, receipt, kitchen, finance = seed(src, passwords)
    expected_http = check_http(src, key, receipt, kitchen, finance)
    note("3/6 Freeze source writers; capture DB, private media and WAL record statistics.")
    src.compose("stop", "web", "api")
    before = src.snapshot()
    require((before["billed_kes"], before["received_kes"], before["media_files"]) == ("24.70", "10.00", 1), "Unexpected source totals/media count.")
    dbfile, mediafile = work / "fixture.dump", work / "media.tar.gz"
    src.sql("CHECKPOINT;")
    end_lsn = src.sql("SELECT pg_current_wal_flush_lsn();")
    require(all(re.fullmatch(r"[0-9A-F]+/[0-9A-F]+", x) for x in (start_lsn, end_lsn)) and start_lsn != end_lsn, "No fixture WAL interval.")
    wal = src.compose(*ADMIN, "pg_waldump", "--path=/var/lib/postgresql/data/pg_wal", "--stats", "--start", start_lsn, "--end", end_lsn)
    require(b"Transaction" in wal and b"Total" in wal, "Expected WAL record statistics not found.")
    with dbfile.open("xb") as f:
        src.compose(*ADMIN, "pg_dump", "-Fc", "-d", DB, dst=f)
    with mediafile.open("xb") as f:
        src.compose(*ONEOFF, "tar", "-C", "/app/media", "-czf", "-", ".", dst=f)
    note("4/6 Build the restore project; initialize only its fresh PostgreSQL volume.")
    dst.compose("build", "api", "migrate", "web", timeout=1800)
    started = time.monotonic()
    dst.compose(*UP, "db")
    require(dst.sql("SELECT count(*) FROM pg_tables WHERE schemaname='public';") == "0", "Refusing non-empty restore database.")
    note("5/6 Restore both artifacts before starting writers; compare the complete snapshot.")
    with dbfile.open("rb") as f:
        dst.compose(*ADMIN, "pg_restore", "--clean", "--if-exists", "--single-transaction", "--exit-on-error", "-d", DB, src=f)
    with mediafile.open("rb") as f:
        dst.compose(*ONEOFF, "sh", "-ec", 'test -z "$(ls -A /app/media)"; umask 077; exec tar -xzf - '
                    '--no-same-owner --no-same-permissions -C /app/media', src=f)
    dst.compose(*ONEOFF, "python", "manage.py", "migrate", "--check")
    after = dst.snapshot()
    require(before == after, "Restore differs in row counts, KES or media inventory/hash.")
    note("6/6 Reopen restored web; verify the shell, receipt and both protected URLs using new sessions.")
    dst.web()
    actual = check_http(dst, key, receipt, Client(dst.port).login("drill-kitchen", passwords),
                        Client(dst.port).login("drill-finance", passwords))
    require(expected_http == actual, "Restored served image bytes or receipt identifier changed.")
    return (f"{len(before['rows'])} model row counts matched; billed KES 24.70, received KES 10.00 (synthetic); "
            f"1 private image, inventory SHA-256 {before['media_names_and_contents_sha256']}; "
            f"recovery + verification {time.monotonic() - started:.1f}s (excludes build).")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true", help="build, run and remove two generated rehearsal projects")
    if not p.parse_args().run:
        p.print_help()
        return
    # No native .env, DB/login settings, proxy overrides, compose overrides or remote builder variables.
    allow = set("PATH PATHEXT SYSTEMROOT WINDIR COMSPEC TEMP TMP TMPDIR HOME HOMEDRIVE HOMEPATH USERPROFILE APPDATA LOCALAPPDATA PROGRAMDATA PROGRAMFILES PROGRAMFILES(X86) XDG_CONFIG_HOME XDG_RUNTIME_DIR DOCKER_CONFIG DOCKER_CONTEXT".split())
    env = {k: v for k, v in os.environ.items() if k.upper() in allow}
    env["COMPOSE_DISABLE_ENV_FILE"] = "1"
    base = Path(tempfile.gettempdir()).resolve()
    require(ROOT not in (base, *base.parents), "System temporary directory is inside the checkout; select a private external TEMP.")
    exe = shutil.which("docker.exe" if os.name == "nt" else "docker")
    require(exe, "Docker CLI not found on PATH.")
    with tempfile.TemporaryDirectory(prefix="hms-synthetic-", dir=base) as directory:
        work = Path(directory)
        (work / "empty.env").touch(mode=0o600)
        ctx = run([exe, "context", "show"], env, work).decode().strip()
        require(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", ctx), "Invalid Docker context.")
        endpoint = run([exe, "context", "inspect", ctx, "--format", "{{.Endpoints.docker.Host}}"], env, work).decode().strip()
        require(endpoint.startswith(("unix:///", "npipe:////./pipe/")), "Only a local Unix socket or Windows Docker pipe is supported.")
        docker = [exe, "--context", ctx]
        prefix = "hms-rh-" + secrets.token_hex(12)
        for args in (("ps", "-aq", "--filter", "name=" + prefix), ("volume", "ls", "-q", "--filter", "name=" + prefix),
                     ("network", "ls", "-q", "--filter", "name=" + prefix), ("image", "ls", "-q", "--filter", "reference=" + prefix + "*")):
            require(not run([*docker, *args], env, work).strip(), "Generated resource prefix collision; aborting without changes.")
        src = Project(docker, env, work, prefix + "-src", high_port())
        dst = Project(docker, env, work, prefix + "-dst", high_port(src.port))
        for project in (src, dst):
            project.validate()
        note(f"Disposable LOCAL projects only: {src.name}, {dst.name}.")
        try:
            result = rehearse(src, dst, work)
        finally:
            failed = []
            for project in (dst, src):
                try:
                    # --rmi local removes the project build tags, not pinned shared base images.
                    project.compose("down", "--volumes", "--remove-orphans", "--rmi", "local", timeout=120)
                except (Failure, OSError):
                    failed.append(project.name)
            if failed:
                raise Failure("Cleanup incomplete; inspect ONLY the printed generated project(s): " + ", ".join(failed))
    note("PASS: " + result + " Generated stacks and temporary archives removed. No pruning.")


if __name__ == "__main__":
    try:
        main()
    except Failure as error:
        sys.exit("FAIL: " + str(error))
    except KeyboardInterrupt:
        sys.exit("Interrupted. Inspect only the printed generated projects if cleanup was interrupted.")
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError, IndexError) as error:
        sys.exit(f"FAIL: {type(error).__name__} during the current stage; check local Docker, disk, port and API contract. Raw details withheld.")
