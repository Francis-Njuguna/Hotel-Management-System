"""One-command local demo launcher. Press Ctrl+C to stop the two web processes."""
import os
import shutil
import subprocess
import sys

if __package__:
    from . import demo_config as demo, local_db, native_db
else:
    import demo_config as demo
    import local_db
    import native_db


def main():
    root = demo.ROOT
    inherited = os.environ.copy()
    helper = native_db if native_db.available(inherited) else local_db
    # Both helpers validate before their first subprocess. Use that same snapshot
    # for migrations, seeding and serving; do not reload .env or inherit a different target.
    cfg = helper.ensure_database(root, inherited)
    tools = demo.system_env(inherited)
    backend = {**tools, **cfg, 'PYTHON_DOTENV_DISABLED': '1'}
    frontend = {**tools, 'HMS_API_TARGET': cfg['HMS_API_TARGET']}

    def run(*args, cwd=root, env=tools):
        subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True)

    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    node = shutil.which('node')
    if not npm or not node:
        raise SystemExit('Install a supported Node.js version with npm first.')
    venv = root / '.venv'
    python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        run(sys.executable, '-m', 'venv', venv)
    run(python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'backend/requirements-dev.txt')
    run(python, 'backend/manage.py', 'migrate', '--noinput', env=backend)
    run(python, 'backend/manage.py', 'seed_demo', '--create-login', env=backend)
    front = root / 'frontend'
    if not (front / 'node_modules/.package-lock.json').exists():
        run(npm, 'ci', cwd=front)
    api = subprocess.Popen([str(python), 'backend/manage.py', 'runserver', demo.API_BIND, '--noreload'],
                           cwd=root, env=backend)
    ui = None
    try:
        ui = subprocess.Popen([node, 'node_modules/vite/bin/vite.js', '--host', demo.HOST, '--port', demo.UI_PORT, '--strictPort'],
                              cwd=front, env=frontend)
        print(f'Open {demo.UI_ORIGIN} · local login: .local/demo-credentials.txt', flush=True)
        ui.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in (ui, api):
            if p is not None and p.poll() is None:
                p.terminate()


if __name__ == '__main__':
    main()
