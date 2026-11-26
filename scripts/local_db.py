"""Provision an isolated, loopback-only development DB and ignored local settings."""
import json
import os
import subprocess
from time import monotonic, sleep

if __package__:
    from . import demo_config as demo
else:
    import demo_config as demo

NAME = 'hotel-a-acsc483-dev-postgres'


def require_local_endpoint(endpoint):
    if not endpoint.startswith(('unix:///', 'npipe:////./pipe/')) or endpoint.startswith('unix:////'):
        raise SystemExit('The demo requires a Docker Engine on a local socket or Windows pipe.')


def ensure_database(root, inherited):
    endpoint = inherited.get('DOCKER_HOST')
    if endpoint:
        require_local_endpoint(endpoint)
        if inherited.get('DOCKER_CONTEXT'):
            raise SystemExit('Select only one local Docker target.')
    cfg = demo.prepare(root, demo.DOCKER_PORT, inherited)
    env = demo.system_env(inherited)
    if 'DOCKER_CONFIG' in inherited:
        env['DOCKER_CONFIG'] = inherited['DOCKER_CONFIG']
    if not endpoint:
        # Inspect local CLI metadata, not the daemon. Pin the resulting socket for every command.
        inspect_env = dict(env, DOCKER_CONTEXT=inherited['DOCKER_CONTEXT']) if inherited.get('DOCKER_CONTEXT') else env
        endpoint = subprocess.run(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'],
                                  env=inspect_env, check=True, capture_output=True, text=True).stdout.strip()
        require_local_endpoint(endpoint)

    def docker(*args, env=env, check=True, **kwargs):
        return subprocess.run(['docker', '--host', endpoint, *args], env=env, check=check, **kwargs)

    present = docker('container', 'ls', '-aq', '--filter', f'name=^/{NAME}$', capture_output=True, text=True)
    if present.stdout.strip():
        fmt = '{{index .Config.Labels "org.hotela.dev"}}\n{{.HostConfig.NetworkMode}}\n{{json .HostConfig.PortBindings}}'
        info = docker('container', 'inspect', '--format', fmt, NAME, capture_output=True, text=True).stdout.splitlines()
        bindings = {'5432/tcp': [{'HostIp': demo.HOST, 'HostPort': demo.DOCKER_PORT}]}
        if (len(info) != 3 or info[0] != 'acsc483' or info[1] not in ('default', 'bridge')
                or json.loads(info[2]) != bindings):
            raise SystemExit('Existing container does not match the isolated local demo; it was left alone.')
        docker('start', NAME)
    else:
        database_env = {k: cfg[k] for k in ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD')}
        docker('run', '-d', '--name', NAME, '--label', 'org.hotela.dev=acsc483',
               '-p', f'{demo.HOST}:{demo.DOCKER_PORT}:5432', '-v', f'{NAME}-data:/var/lib/postgresql/data',
               '-e', 'POSTGRES_DB', '-e', 'POSTGRES_USER', '-e', 'POSTGRES_PASSWORD', 'postgres:16-alpine',
               env={**env, **database_env})

    # Check the actual demo DB/user over TCP using psql in this specific container;
    # no global client installation, ambient libpq options or password in argv.
    deadline = monotonic() + 90
    while monotonic() < deadline:
        ready = docker('exec', '-e', 'PGPASSWORD', '-e', f'PGHOSTADDR={demo.HOST}',
                       NAME, 'psql', '-XwAt', '-h', demo.HOST, '-p', '5432',
                       '-U', cfg['POSTGRES_USER'], '-d', cfg['POSTGRES_DB'], '-c', 'SELECT 1',
                       env=dict(env, PGPASSWORD=cfg['POSTGRES_PASSWORD']), check=False, capture_output=True, text=True)
        if ready.returncode == 0 and ready.stdout.strip() == '1':
            print(f'Project database is ready on {demo.HOST}:{demo.DOCKER_PORT}.')
            return cfg
        sleep(.5)
    raise SystemExit('The local container did not accept a demo database connection. Check its Docker logs privately.')


def main():
    ensure_database(demo.ROOT, os.environ)


if __name__ == '__main__':
    main()
