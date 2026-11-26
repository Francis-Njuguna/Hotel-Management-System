# Hotel A: local deployment and recovery

Use this Compose stack on a **trusted, single workstation** with synthetic data. Its only published listener is `http://127.0.0.1:8080`. It is not a TLS deployment or a claim of production readiness. Commands below are operator instructions, not results of a deployment or restore drill.

For a one-command **synthetic Compose rehearsal**, run `python deploy/rehearse.py --run` from the repository root with a local Docker daemon. It generates two disposable projects and their secrets, builds the stack, backs up and restores the source database and private media into separate volumes, and verifies a receipt and protected image over HTTP before and after recovery. For the independently exercised native Windows route, see the [browser and recovery runner](../../frontend/e2e/README.md). Results for each route are in [the evidence table](../../PROJECT_STATUS.md#software-delivery-and-verification--2026-11-26).

## First launch

Use a supported Docker Engine with Linux containers, BuildKit and a current Compose v2 plugin (`docker compose`, not `docker-compose` or Swarm). On Windows, Docker Desktop with WSL2 integration supports the POSIX examples below. Run from the repository root, in a clean shell without exported `HMS_*`, `POSTGRES_*` or Compose overrides: shell variables take precedence over `--env-file`. Allow disk space for the build cache, **two copies** of the data for a drill, and a separate backup. The first build needs access to the official image registries, PyPI and npm.

Use the integrated release: `backend/requirements.txt`, `manage.py`, application code **and committed migrations**, `config.wsgi:application`; `frontend/package.json`, **matching `package-lock.json`** and the Vite source. No host PostgreSQL, Node or Django install is needed. The container bases and PostgreSQL 17 image are pinned by multi-architecture digest. Pip applies the deployment's [version constraints](../../deploy/python.constraints.txt) to the application's requirements; `npm ci` consumes the lockfile, then `npm run build` produces `dist/`. Missing inputs or conflicting constraints must fail the build; do not substitute `npm install` or generate migrations on the host during release. Retain the approved built images for exact rollback rather than relying on future package availability.

Create two **independent random secrets**, once, in an encrypted, operator-only location outside Git. With Python 3 and a private POSIX home:

```sh
umask 077
S="$HOME/.local/state/hotel-a"
mkdir -p "$S"
python3 deploy/new_env.py "$S/local.env"    # first launch only; refuses to overwrite
live() { docker compose -f compose.yaml -p hotel-a --env-file "$S/local.env" "$@"; }
live config --quiet                         # validate without printing secrets
live up -d --build --wait web
live ps -a
live exec api python manage.py createsuperuser
```

Supply the **Django** administrator name, reachable administrative email and strong unique password interactively. No seeded credentials, password arguments or sample guest/payment data are needed. Open `http://127.0.0.1:8080` and sign in with that account. Create named, role-scoped staff accounts for routine work; the Django superuser is not the database administrator. `live stop` pauses the stack; `live up -d --wait web` resumes it. `live down` removes containers and networks but retains the named volumes. **Never add `-v` to a live `down`, or prune live volumes.**

On native PowerShell, use a directory with a private NTFS ACL, `py -3 deploy/new_env.py <private-path>` and `docker compose -f compose.yaml -p hotel-a --env-file <private-path> ...` for the same launch commands. Alternatively use a password manager to populate the two required keys below; host Python is only a convenience. Use the WSL/Linux shell for the binary backup/restore redirections below, **not** Windows PowerShell text pipelines.

### Configuration

| Variable | Local value / meaning |
| --- | --- |
| `HMS_SECRET_KEY`, `POSTGRES_PASSWORD` | Required, no defaults. Use at least 32 random bytes for each. The DB password belongs to the application's **runtime** login after bootstrap. |
| `POSTGRES_DB`, `POSTGRES_USER` | `hotel_a`, `hms_app`. Choose simple lowercase identifiers on **first initialization**. Do not use `postgres`, `template0`, `template1`, `www-data` or a `pg_` name. |
| `POSTGRES_HOST`, `POSTGRES_PORT` | `db`, `5432` **inside Compose**. Do not copy a native-run `127.0.0.1` DB host or a host database port here. Keep `POSTGRES_HOST=db` for this stack. |
| `HMS_HTTP_PORT`, `HMS_PUBLIC_URL` | `8080` (host loopback port), `http://127.0.0.1:<port>` (absolute base for reset links). |
| `HMS_ALLOWED_HOSTS` | `127.0.0.1,localhost`; explicit hostnames, no scheme, port or wildcard. First hostname is used by the API health probe. |
| `HMS_CSRF_TRUSTED_ORIGINS` | Comma-separated **origins**, including scheme and non-default port. Defaults to HTTP loopback and localhost at `HMS_HTTP_PORT`. |
| `HMS_DEBUG`, `HMS_SECURE_COOKIES` | Both `0` for this **loopback HTTP** setup. Debug is not needed to serve images. Secure cookies must be `1` for HTTPS. Flags take `0` / `1`. |

### What starts, and who has access

1. **`db`** has no published port. The first start on empty `pgdata` runs [bootstrap SQL](../../deploy/db/10-bootstrap.sql) in `POSTGRES_DB`. It installs `btree_gist`, needed by the room overlap constraint, and provisions grants. PostgreSQL `postgres` can administer over the local socket using OS peer authentication; its password is cleared and TCP login is rejected by [pg_hba.conf](../../deploy/db/pg_hba.conf). The readiness check uses a real SCRAM login and `SELECT 1` over TCP, not a sleep or the temporary initialization server.
2. **`migrate`** waits for DB health, checks for models without committed migrations (dry run; writes no files), then runs `python manage.py migrate --noinput` as one job, not per Gunicorn worker. Its Debian `www-data` OS identity matches its schema-writer DB role over a shared Unix socket; neither its role nor `postgres` accepts TCP login. It has no network. Only `db` and `migrate` mount that socket. Do not change the base distro/UID without retesting peer auth.
3. **`api`** waits for a successful migration exit. It runs non-root Gunicorn from `/app`, with one threaded worker for this workstation; before adding workers/replicas, review the API's process-local throttle cache. Its TCP role has connect, schema usage, migration-created table DML and sequence usage/read grants, **no** schema create, database ownership or cluster-admin privileges. Operator migrations therefore use `migrate`, not `api`. Only `api` mounts `private_media` at `/app/media`.
4. **`web`** waits for `/api/v1/auth/me/` to answer and serves built Vite files, including SPA deep links. Nginx forwards `/api` to Django without stripping `/api/v1`; it preserves browser `Host` including port and replaces forwarding headers. `/protected-media/<key>` is internally routed to Django's `/api/v1/media/<key>` (the URL also emitted by the API). **Both require the Django session and capability for the referenced image.** Nginx has no upload volume or file alias. `/media` and `/media/…` return 404, never the SPA. The proxy limits the *whole request* to 8 MiB; Django's upload/type limits are separate.

For a managed/existing DB, **file availability is not proof an extension is installed or creatable**. PostgreSQL 17 treats `btree_gist` as trusted, but installation still requires `CREATE` on the database; a provider can also restrict allowed extensions. Neither Django role gets that database-level privilege here. In the actual target DB the DBA should preinstall `CREATE EXTENSION IF NOT EXISTS btree_gist;`, provision equivalent schema-writer/runtime grants, and use a separate migration-only connection. Run the exclusion migration on an isolated target. Do not make the web role a superuser or weaken the constraint. Pointing `POSTGRES_HOST` at another server alone does **not** adapt this local socket/bootstrap design.

## Check the installation

```sh
live exec api python manage.py check
live exec api python manage.py migrate --check
live exec web nginx -t
curl -fsS http://127.0.0.1:8080/api/v1/auth/me/       # anonymous JSON, user:null
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/media/anything  # 404
live exec -T --user postgres db sh -ec 'exec psql -X -v ON_ERROR_STOP=1 -d "$POSTGRES_DB"' <<'SQL'
\getenv app_role HMS_APP_USER
SELECT extname, extversion FROM pg_extension WHERE extname = 'btree_gist';
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole,
       has_schema_privilege(rolname, 'public', 'CREATE') AS can_create
FROM pg_roles WHERE rolname IN (:'app_role', 'www-data');
SQL
```

Expect the extension row, both roles non-admin, only `www-data` with `can_create`. In a browser, refresh a deep link; check login with CSRF and logout. Upload an approved **synthetic** room/menu image. Compare a permitted account, an out-of-role account and a signed-out browser on the *same existing key* via both protected URLs. Only the permitted user should receive image bytes; `/media/<key>` must still be 404. Check that no other service port is published. A 404 for an invented filename is not an authorization test.

For failures: `live ps -a` should show `migrate` **exited 0**, not restarting; inspect `live logs --tail 50 db migrate api web` privately. A DB auth failure on a retained volume often means the env was changed without changing the role password. Init scripts are **not** rerun by container recreation. A partial bootstrap, missing migrations, broken lockfile or a failed DB constraint is a stop condition: identify the error and repair/restore in isolation; do not discard volumes to make startup look successful. Health probes cover startup, not continued data integrity or automatic failover.

## TLS, secrets, mail and operations before any live use

- Terminate TLS for the **same UI/API origin** at a maintained edge; automate certificate renewal, redirect HTTP, keep API/DB inaccessible from clients. Either terminate TLS in Nginx (its `$scheme` then equals `https`) or, on a listener reachable **only by the authenticated/trusted TLS terminator**, set upstream scheme to `https` after the edge enforces HTTPS. Do **not** pass a client-supplied `X-Forwarded-Proto`: the shipped HTTP proxy overwrites it. Set exact HTTPS `HMS_PUBLIC_URL`, `HMS_ALLOWED_HOSTS`, `HMS_CSRF_TRUSTED_ORIGINS`, `HMS_DEBUG=0`, `HMS_SECURE_COOKIES=1`. Enable `HMS_TRUST_PROXY=1` only once the header trust boundary is verified; enable `HMS_HTTPS=1` (redirect + HSTS) after confirming certificates and avoiding redirect loops. Run `python manage.py check --deploy` in that configuration; retest CSRF, cookies, reset links and protected downloads over HTTPS. Do not expose this HTTP demo on `0.0.0.0`.
- No secrets in git, Docker build args, browser `VITE_*` variables, logs, screenshots or tickets. An env file is an operator convenience, **not** a vault: Docker administrators can inspect container environments. Limit daemon access, encrypt host storage and backups, keep recovery keys/secret versions separately in a secret manager. For DB password rotation, quiesce writers, use the DB admin's interactive `psql` `\password hms_app` (substitute actual runtime role) and update the private env/secret version, then recreate `db` and `api` in a maintenance window and recheck health. Editing the env file alone does not update PostgreSQL. Plan Django signing-key rotation/invalidation of sessions and reset links; never overwrite a running deployment's keys casually.
- **Recovery mail:** in native debug mode with no relay, test messages go to the ignored private `.local/outbox/`. In the non-debug Compose stack, configure `HMS_EMAIL_HOST`, `HMS_EMAIL_PORT` (normally 587), `HMS_EMAIL_TLS=1` (STARTTLS), `HMS_EMAIL_USER`, secret `HMS_EMAIL_PASSWORD`, and a verified `HMS_EMAIL_FROM` for external delivery. Without a working relay, no reset is delivered. A signed-in staff member must verify mailbox ownership before reset is enabled. For live service set `HMS_ENV=production`, which rejects insecure HTTPS/cookie/recovery settings. Test a controlled mailbox and used/expired links without logging tokens. Keep outbound mail disabled on restore drills.
- Monitor service health/restarts, 5xx rate/latency, DB connectivity/connections, disk/inodes (DB, uploads **and** host Docker storage), certificate expiry, SMTP failures, backup age and most recent successful restore. Docker rotates the local container logs. Nginx access logs omit URLs, query strings, identities and bodies; **error logs may still contain sensitive context**. Restrict/review/redact before sharing, set retention and alerts to a named operator. No hosted monitoring, scheduler, HA or off-host backup service is provisioned here. Hosting, domain, TLS operations, SMTP, backup storage/egress, retention, recovery time (RTO) and acceptable data loss (RPO) need owner decisions and costing.
- The default account-recovery and login throttles use a process-local cache. Set shared limits across workers at the trusted edge or in a shared application cache, and verify the proxy/client-IP boundary before live use. The reset form gives a uniform message but delivery is synchronous after commit; use a bounded asynchronous mail worker if preventing mailbox-based timing differences is required on an exposed service.

## Backup: keep database and private files at the same point

Use an approved maintenance window and an operator-only **encrypted** directory outside the checkout; the examples use `$S`. Use the `live` function above. Check that the source runs the recorded clean commit and that sufficient space exists. Stop **all** mutators, including any external jobs or admin sessions; keep `db` running. `pg_dump` alone is transaction-consistent for PostgreSQL but does not include `/app/media`, roles, SMTP settings or keys. Do not copy a running `PGDATA` directory.

```sh
set -eu
umask 077
mkdir -p "$S/backups"
B=$(mktemp -d "$S/backups/set-XXXXXXXX")
(
  set -eu
  live stop web api
  trap 'live start api web >&2' 0   # omit for a release window that must stay frozen
  date -u +%Y-%m-%dT%H:%M:%SZ > "$B/freeze-utc.txt"
  git rev-parse HEAD > "$B/revision.txt"
  live images > "$B/images.txt"
  live exec -T --user postgres db sh -ec 'printf "POSTGRES_DB=%s\nPOSTGRES_USER=%s\n" "$POSTGRES_DB" "$HMS_APP_USER"' > "$B/identifiers.env"
  live run --rm --no-deps -T api python manage.py shell -v 0 < deploy/snapshot_check.py > "$B/snapshot.json"
  live exec -T --user postgres db sh -ec 'exec pg_dump --format=custom --dbname="$POSTGRES_DB"' > "$B/database.dump"
  live run --rm --no-deps -T api tar -C /app/media -czf - . > "$B/media.tar.gz"
  live exec -T --user postgres db pg_restore --list < "$B/database.dump" > /dev/null
  gzip -t "$B/media.tar.gz"
  (cd "$B" && sha256sum database.dump media.tar.gz snapshot.json identifiers.env revision.txt images.txt freeze-utc.txt > SHA256SUMS)
)
```

On failure, **reject the partial set** and check whether writers were restarted. Record the UTC freeze time, operator, app image IDs, DB major, backup ID and recovery-key version privately. The [comparison helper](../../deploy/snapshot_check.py) reads model row counts, billed/received KES and a deterministic hash of media names/bytes; it rejects missing DB-referenced uploads. This is a reconciliation aid, not an audit of every row. Encrypt **and authenticate** the whole set and manifest; transfer it to access-controlled, separately recoverable off-host storage. A colocated checksum detects corruption, not malicious replacement. Keep the release/images, schema bootstrap and secrets recoverable separately. Schedule and monitor this procedure against the agreed RPO; only a restore establishes recoverability.

## Restore drill: a new DB **and** a new media volume

Use only a trusted authenticated backup: SQL restores run as the local admin and archives contain private media. On a restricted recovery host, decrypt it to `$B`, use the exact recorded release, and restore with PostgreSQL 17 tools. Keep the source untouched. The following uses **fresh project-scoped resources**, a different loopback port, fresh drill credentials and no mail. Keep `POSTGRES_DB` and the runtime role **names** the same as the source so PostgreSQL owners/grants resolve; the init SQL recreates roles, `pg_dump` does not. Verify you are on the intended Docker context.

```sh
# S is the private state directory above. Set B to the authenticated, decrypted set.
set -eu
: "${S:?Set private state path}" "${B:?Set backup directory}"
(cd "$B" && sha256sum -c SHA256SUMS)
test "$(git rev-parse HEAD)" = "$(cat "$B/revision.txt")"
W=$(mktemp -d "$S/drill-XXXXXXXX")
DRILL="hotel-a-drill-$(date -u +%Y%m%d%H%M%S)"
vols=$(docker volume ls -q --filter "label=com.docker.compose.project=$DRILL")
ctrs=$(docker ps -aq --filter "label=com.docker.compose.project=$DRILL")
test -z "$vols$ctrs" || { echo 'Choose a NEW drill project; refusing to overwrite.' >&2; exit 1; }
python3 deploy/new_env.py "$W/drill.env"
cat "$B/identifiers.env" >> "$W/drill.env"
drill() { HMS_HTTP_PORT=18080 HMS_EMAIL_HOST='' POSTGRES_HOST=db docker compose -f compose.yaml -p "$DRILL" --env-file "$W/drill.env" "$@"; }
drill config --quiet
drill build api migrate web
drill up -d --wait db                   # do NOT start migrate, api or web yet
tables=$(drill exec -T --user postgres db sh -ec 'exec psql -XAtq -v ON_ERROR_STOP=1 -d "$POSTGRES_DB"' <<'SQL'
SELECT count(*) FROM pg_tables WHERE schemaname = 'public';
SQL
)
test "$tables" = 0 || { echo 'Target is not a fresh database; abort.' >&2; exit 1; }
drill exec -T --user postgres db sh -ec 'exec pg_restore --clean --if-exists --single-transaction --exit-on-error --dbname="$POSTGRES_DB"' < "$B/database.dump"
drill run --rm --no-deps -T api sh -ec 'test -z "$(ls -A /app/media)"; umask 077; exec tar -xzf - --no-same-owner --no-same-permissions -C /app/media' < "$B/media.tar.gz"
drill run --rm --no-deps -T api python manage.py migrate --check
drill run --rm --no-deps -T api python manage.py shell -v 0 < deploy/snapshot_check.py > "$W/restored.json"
cmp "$B/snapshot.json" "$W/restored.json"  # stop on any difference, before any login/write
drill up -d --wait web
drill ps -a
```

Before accepting the drill, repeat the extension/role checks above using `drill`. In a **separate browser profile** at `http://127.0.0.1:18080` (cookies are not isolated by port), verify sign-in, authorized/denied reads of a restored image and representative reservations, invoice lines, tender totals and receipt identifiers against the private baseline. Do not invent payments. Record backup timestamp/age, elapsed restore time, discrepancies and sign-off against RPO/RTO; a successful `pg_restore` exit is insufficient. Stop the drill with `drill down`; arrange secure removal of **only** its named volumes and decrypted workspace per retention policy. Do not publish the dump, manifest, screenshots or identifiers.

## Release, rollback and live recovery

Before applying any release: keep the last known-good images/revision, take and test a DB **plus media** backup, and freeze writers. Build the new images; `live run --rm --no-deps migrate python manage.py migrate --plan` previews the plan against the running DB. Run `live up -d --build --wait web` during the window; check migration exit, schema, role boundaries and reconciled figures before reopening. A digest/requirements change is a release: review patches, rebuild from cold cache and run the same tests. Never change the PostgreSQL major tag under an existing volume as an upgrade plan.

If no incompatible migrations/data changes occurred, redeploy the known-good images and check compatibility before resuming. Otherwise **do not** blindly reverse a migration, delete the old volumes or point the old code at a new schema. Keep writers paused and preserve the failed state. Restore the matched pre-release DB and media into **new** resources with the old release as in the drill. For real recovery apply the authorized live secret versions, TLS/host and SMTP configuration (or intentionally rotate/invalidate sessions and reset links). Reconcile, obtain owner approval for any post-snapshot data loss or controlled replay against actual records, then switch the trusted edge to the verified stack. Retain the prior stack offline until acceptance. No rollback time, live readiness or restored dataset is asserted by this guide.
