"""Set up a separate Windows PostgreSQL development cluster; never touch system services."""
import os
from pathlib import Path
import subprocess
import tempfile

if __package__:
    from . import demo_config as demo
else:
    import demo_config as demo


def bin_directory(inherited):
    directory = inherited.get('PG_BIN', r'C:\Program Files\PostgreSQL\18\bin')
    if directory.replace('\\', '/').startswith('//'):
        raise SystemExit('PG_BIN must point to a local PostgreSQL installation.')
    return Path(directory)


def available(inherited):
    return os.name == 'nt' and (bin_directory(inherited) / 'pg_ctl.exe').is_file()


def ensure_database(root, inherited):
    binary = bin_directory(inherited)
    if not (binary / 'initdb.exe').is_file():
        raise SystemExit('Set PG_BIN to the installed PostgreSQL bin directory.')
    cfg = demo.prepare(root, demo.NATIVE_PORT, inherited)
    env = demo.system_env(inherited)
    state = root / '.local'
    data = state / 'pgdata'
    state.mkdir(exist_ok=True)

    def pg(command, *args, env=env, check=True, **kwargs):
        return subprocess.run([str(binary / (command + '.exe')), *map(str, args)], env=env, check=check, **kwargs)

    if not (data / 'PG_VERSION').exists():
        with tempfile.NamedTemporaryFile(mode='w', dir=state, delete=False, encoding='utf-8') as pw:
            pw.write(cfg['POSTGRES_PASSWORD'] + '\n')
        try:
            pg('initdb', '-D', data, '-U', cfg['POSTGRES_USER'], '--auth=scram-sha-256', '--encoding=UTF8',
               '--locale=C', '--pwfile', pw.name)
        finally:
            Path(pw.name).unlink(missing_ok=True)
    status = pg('pg_ctl', 'status', '-D', data, check=False, capture_output=True)
    if status.returncode == 3:  # pg_ctl: the server is not running
        pg('pg_ctl', 'start', '-w', '-t', '360', '-D', data, '-l', state / 'postgres.log',
           '-o', f'-p {cfg["POSTGRES_PORT"]} -h {cfg["POSTGRES_HOST"]}')
    elif status.returncode:
        raise SystemExit('Could not verify the status of the local demo cluster.')

    client = dict(env, PGHOST=cfg['POSTGRES_HOST'], PGHOSTADDR=cfg['POSTGRES_HOST'], PGPORT=cfg['POSTGRES_PORT'],
                  PGUSER=cfg['POSTGRES_USER'], PGPASSWORD=cfg['POSTGRES_PASSWORD'], PGDATABASE='postgres',
                  PGCLIENTENCODING='UTF8')
    # A running cluster in this directory and a listener on the port must be the SAME server.
    probe = pg('psql', '-XwAt', '-F', '\t', '-c', "SELECT current_setting('data_directory'), "
               "current_setting('listen_addresses'), EXISTS(SELECT 1 FROM pg_database WHERE datname='hotel_a')",
               env=client, capture_output=True, encoding='utf-8').stdout.rstrip('\r\n').split('\t')
    if len(probe) != 3 or Path(probe[0]) != data or probe[1] != demo.HOST or probe[2] not in ('t', 'f'):
        raise SystemExit('The listener is not the expected loopback-only project cluster.')
    if probe[2] == 'f':
        pg('createdb', '-w', '--maintenance-db=postgres', cfg['POSTGRES_DB'], env=client)
    print(f'Project database is ready on {demo.HOST}:{demo.NATIVE_PORT}.')
    return cfg


def main():
    ensure_database(demo.ROOT, os.environ)


if __name__ == '__main__':
    main()
