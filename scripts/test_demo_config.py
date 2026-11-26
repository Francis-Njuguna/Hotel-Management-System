"""Local launcher guards. No real database, Docker Engine, network or application subprocesses."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

if __package__:
    from . import demo_config as demo, local_db, native_db, run_local
else:
    import demo_config as demo
    import local_db
    import native_db
    import run_local


def legacy_settings(port):
    """Shape of .env from the original helpers, with synthetic test credentials."""
    return dict(HMS_SECRET_KEY='synthetic_test_signing_key_' * 2, HMS_DEBUG='1', HMS_SECURE_COOKIES='0',
                HMS_ALLOWED_HOSTS='localhost,127.0.0.1', HMS_PUBLIC_URL='http://127.0.0.1:5187',
                HMS_CSRF_TRUSTED_ORIGINS='http://127.0.0.1:5187,http://localhost:5187',
                POSTGRES_DB='hotel_a', POSTGRES_USER='hotel_a', POSTGRES_PASSWORD='synthetic_test_db_password_' * 2,
                POSTGRES_HOST='127.0.0.1', POSTGRES_PORT=port, HMS_EMAIL_HOST='', HMS_EMAIL_PORT='587',
                HMS_EMAIL_USER='', HMS_EMAIL_PASSWORD='', HMS_EMAIL_FROM='', HMS_EMAIL_TLS='1')


class LauncherGuards(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix='hotel-a-guard-')))
        self.enterContext(patch.object(demo, 'ROOT', self.root))
        self.bin = self.root / 'fake-pg-bin'
        self.bin.mkdir()
        for name in ('initdb.exe', 'pg_ctl.exe'):
            (self.bin / name).touch()
        self.enterContext(patch.dict(os.environ, {'PG_BIN': str(self.bin)}, clear=True))
        self.file = self.root / '.env'
        self.run = self.enterContext(patch('subprocess.run', side_effect=AssertionError('unexpected subprocess')))
        self.popen = self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('unexpected server')))
        self.socket = self.enterContext(patch('socket.socket', side_effect=AssertionError('unexpected socket')))
        self.dns = self.enterContext(patch('socket.getaddrinfo', side_effect=AssertionError('unexpected DNS')))
        self.enterContext(redirect_stdout(io.StringIO()))

    def write_file(self, values, extra=''):
        self.file.write_text('# Synthetic fixture\n' + ''.join(f'{k}={v}\n' for k, v in values.items()) + extra,
                             encoding='utf-8')
        return self.file.read_bytes()

    def assert_blocked(self, entry):
        with self.assertRaises(SystemExit) as failure:
            entry()
        self.run.assert_not_called()
        self.popen.assert_not_called()
        self.socket.assert_not_called()
        self.dns.assert_not_called()
        self.assertFalse((self.root / '.local').exists())
        self.assertFalse((self.root / '.venv').exists())
        return str(failure.exception)

    def test_conflicting_first_run_does_not_persist_or_launch_anything(self):
        for native in (False, True):
            for entry in (run_local.main, (native_db if native else local_db).main):
                for key, value in (('POSTGRES_HOST', 'db.example.invalid'), ('POSTGRES_PASSWORD', 'private-test-value'),
                                   ('HMS_API_TARGET', 'http://outside.invalid:8017'), ('HMS_EMAIL_HOST', 'mail.invalid')):
                    with self.subTest(native=native, entry=entry, key=key), \
                            patch.object(native_db, 'available', return_value=native), patch.dict(os.environ, {key: value}):
                        message = self.assert_blocked(entry)
                        self.assertIn(key, message)
                        self.assertNotIn(value, message)
                        self.assertFalse(self.file.exists())

    def test_existing_file_does_not_hide_conflicting_invocation(self):
        original = self.write_file(legacy_settings('55487'))
        overrides = {'POSTGRES_DB': 'other_database', 'POSTGRES_USER': 'other_user', 'POSTGRES_PORT': '55488',
                     'POSTGRES_PASSWORD': 'different-test-password', 'POSTGRES_EXTRA': '', 'HMS_SECRET_KEY': 'other-key',
                     'HMS_PUBLIC_URL': 'https://outside.invalid', 'HMS_ALLOWED_HOSTS': '*', 'HMS_DEBUG': '0',
                     'HMS_CSRF_TRUSTED_ORIGINS': 'http://outside.invalid:5187', 'HMS_API_TARGET': 'http://127.0.0.1:8019',
                     'HMS_ENV': 'production', 'HMS_EMAIL_HOST': 'mail.example.invalid', 'HMS_EMAIL_USER': 'relay-user',
                     'HMS_EMAIL_PASSWORD': 'relay-test-value', 'HMS_MEDIA_ROOT': 'other-media', 'HMS_E2E_DISPOSABLE': '1',
                     'DJANGO_SETTINGS_MODULE': 'unrelated.settings'}
        with patch.object(native_db, 'available', return_value=False):
            for key, value in overrides.items():
                with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                    self.assertIn(key, self.assert_blocked(run_local.main))
                    self.assertEqual(original, self.file.read_bytes())

    def test_file_must_name_this_helpers_database_user_and_port(self):
        for helper, port, wrong_port in ((native_db, '55488', '55487'), (local_db, '55487', '55488')):
            for key, value in (('POSTGRES_DB', 'unrelated'), ('POSTGRES_USER', 'postgres'), ('POSTGRES_HOST', 'localhost'),
                               ('POSTGRES_HOST', 'db.example.invalid'), ('POSTGRES_PORT', wrong_port), ('POSTGRES_PORT', '5432')):
                with self.subTest(helper=helper.__name__, key=key, value=value):
                    expected = legacy_settings(port)
                    original = self.write_file({**expected, key: value})
                    with patch.dict(os.environ, {key: expected[key]}):  # ambient cannot "fix" an unsafe file either
                        self.assertIn(key, self.assert_blocked(helper.main))
                    self.assertEqual(original, self.file.read_bytes())

    def test_file_restricts_recovery_proxy_and_django_configuration(self):
        bad = {'HMS_DEBUG': '0', 'HMS_ENV': 'production', 'HMS_SECURE_COOKIES': '1', 'HMS_TRUST_PROXY': '1',
               'HMS_HTTPS': '1', 'HMS_NUM_PROXIES': '3', 'HMS_ALLOWED_HOSTS': 'localhost,*',
               'HMS_CSRF_TRUSTED_ORIGINS': 'http://127.0.0.1:5187,https://outside.invalid',
               'HMS_PUBLIC_URL': 'http://outside.invalid:5187', 'HMS_API_TARGET': 'http://outside.invalid:8017',
               'HMS_EMAIL_HOST': '127.0.0.1', 'HMS_EMAIL_FROM': 'sender@example.invalid', 'HMS_EMAIL_USER': 'relay',
               'HMS_EMAIL_PASSWORD': 'synthetic-mail-secret', 'HMS_MEDIA_ROOT': 'foreign-media',
               'HMS_SECRET_KEY': '${IMPORTED_KEY}', 'POSTGRES_PASSWORD': '', 'DJANGO_SETTINGS_MODULE': 'other.settings'}
        for key, value in bad.items():
            with self.subTest(key=key):
                original = self.write_file({**legacy_settings('55487'), key: value})
                self.assertIn(key, self.assert_blocked(local_db.main))
                self.assertEqual(original, self.file.read_bytes())

    def test_ambiguous_missing_and_unrecognized_file_values_are_rejected(self):
        for extra in ('HMS_DEBUG=1\n', 'export POSTGRES_DB=hotel_a\n', 'PGHOSTADDR=192.0.2.1\n',
                      'HMS_ANOTHER_SETTING=1\n', 'unknown line\n'):
            with self.subTest(extra=extra):
                self.write_file(legacy_settings('55488'), extra)
                self.assert_blocked(native_db.main)
        for key in ('POSTGRES_HOST', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PORT', 'POSTGRES_PASSWORD', 'HMS_SECRET_KEY'):
            with self.subTest(missing=key):
                values = legacy_settings('55488')
                del values[key]
                self.write_file(values)
                self.assertIn(key, self.assert_blocked(native_db.main))

    def test_fresh_settings_are_private_unique_and_reusable(self):
        previous = {}
        for port in ('55487', '55488'):
            root = self.root / port
            root.mkdir()
            cfg = demo.prepare(root, port, {'HMS_DEBUG': '1', 'POSTGRES_PORT': port})
            path = root / '.env'
            original = path.read_bytes()
            matched = demo.prepare(root, port, cfg.copy())
            self.assertEqual(matched, cfg)
            self.assertEqual(original, path.read_bytes())
            self.assertEqual(cfg['POSTGRES_PORT'], port)
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            for key in ('HMS_SECRET_KEY', 'POSTGRES_PASSWORD'):
                self.assertGreaterEqual(len(cfg[key]), 32)
                self.assertNotEqual(previous.get(key), cfg[key])
            previous = cfg

    def check_launch(self, native):
        port = '55488' if native else '55487'
        fixture = legacy_settings(port)
        original = self.write_file(fixture)
        data = self.root / '.local' / 'pgdata'
        socket_path = 'unix:///mock-docker.sock'

        def complete(args, **kwargs):
            self.assertIn('env', kwargs, 'every child must get an explicit environment')
            output, status = '', 0
            if 'context' in args:
                output = socket_path
            if 'exec' in args:
                output = '1\n'
            if 'status' in args:
                status = 3
            if args[0].endswith('psql.exe'):
                output = f'{data}\t127.0.0.1\tf\n'
            return subprocess.CompletedProcess(args, status, output, '')

        self.run.side_effect = complete
        self.popen.side_effect = lambda *args, **kwargs: Mock()
        stale = dict(PGHOSTADDR='192.0.2.1', PGSERVICE='other-service', VITE_TEST_ONLY='unrelated',
                     HMS_DEBUG='1', POSTGRES_DB='hotel_a', HMS_API_TARGET='http://127.0.0.1:8017')
        with patch.object(native_db, 'available', return_value=native), patch.dict(os.environ, stale), \
                patch('shutil.which', side_effect=lambda name: name):
            run_local.main()
        self.assertEqual(original, self.file.read_bytes())  # legacy .env works, without a rewrite
        api, ui = self.popen.call_args_list
        backend = api.kwargs['env']
        self.assertIn('127.0.0.1:8017', api.args[0])
        manage = [c for c in self.run.call_args_list if 'backend/manage.py' in c.args[0]]
        self.assertEqual([c.args[0][2] for c in manage], ['migrate', 'seed_demo'])
        for call in manage:
            self.assertEqual(call.kwargs['env'], backend)
        for key, value in fixture.items():
            self.assertEqual(backend[key], value)
        self.assertEqual(backend['DJANGO_SETTINGS_MODULE'], 'config.settings')
        self.assertEqual(backend['HMS_MEDIA_ROOT'], str(self.root / 'backend' / 'media'))
        self.assertEqual(backend['HMS_API_TARGET'], 'http://127.0.0.1:8017')
        self.assertEqual(backend['HMS_ENV'], 'local')
        self.assertEqual(backend['PYTHON_DOTENV_DISABLED'], '1')
        self.assertNotIn('PGHOSTADDR', backend)
        self.assertNotIn('PGSERVICE', backend)
        self.assertIn('127.0.0.1', ui.args[0])
        self.assertIn('5187', ui.args[0])
        self.assertEqual(ui.kwargs['env']['HMS_API_TARGET'], backend['HMS_API_TARGET'])
        for env in [ui.kwargs['env'], *(c.kwargs['env'] for c in self.run.call_args_list
                                        if 'pip' in c.args[0] or 'ci' in c.args[0] or 'venv' in c.args[0])]:
            self.assertTrue({'POSTGRES_PASSWORD', 'HMS_SECRET_KEY', 'VITE_TEST_ONLY', 'PGSERVICE'}.isdisjoint(env))
        if native:
            created, = [c for c in self.run.call_args_list if c.args[0][0].endswith('createdb.exe')]
            self.assertEqual(created.args[0][-1], 'hotel_a')
            client = created.kwargs['env']
            self.assertEqual((client['PGHOSTADDR'], client['PGHOST'], client['PGPORT'], client['PGUSER']),
                             ('127.0.0.1', '127.0.0.1', '55488', 'hotel_a'))
            self.assertEqual(client['PGPASSWORD'], backend['POSTGRES_PASSWORD'])
            self.assertNotIn('PGSERVICE', client)
        else:
            provision, = [c for c in self.run.call_args_list if 'run' in c.args[0]]
            self.assertEqual(provision.args[0][:3], ['docker', '--host', socket_path])
            self.assertIn('127.0.0.1:55487:5432', provision.args[0])
            for key in ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD'):
                self.assertEqual(provision.kwargs['env'][key], backend[key])
            self.assertNotIn(backend['POSTGRES_PASSWORD'], provision.args[0])

    def test_native_children_share_one_checked_target(self):
        self.check_launch(native=True)

    def test_docker_children_share_one_checked_target(self):
        self.check_launch(native=False)

    def test_remote_docker_context_is_only_inspected_locally(self):
        self.write_file(legacy_settings('55487'))
        with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://other.invalid:2376'}):
            self.assert_blocked(local_db.main)
        self.run.side_effect = None
        self.run.return_value.stdout = 'ssh://other.invalid\n'
        with self.assertRaisesRegex(SystemExit, 'local socket'):
            local_db.main()
        self.run.assert_called_once()
        self.assertEqual(self.run.call_args.args[0][:3], ['docker', 'context', 'inspect'])

    def test_reused_docker_container_requires_correct_port_binding_before_start(self):
        self.write_file(legacy_settings('55487'))
        self.run.side_effect = [Mock(stdout='fake-id\n'), Mock(stdout='acsc483\nbridge\n'
                                '{"5432/tcp":[{"HostIp":"0.0.0.0","HostPort":"55487"}]}\n')]
        with patch.dict(os.environ, {'DOCKER_HOST': 'unix:///mock-docker.sock'}), \
                self.assertRaisesRegex(SystemExit, 'container'):
            local_db.main()
        self.assertEqual([c.args[0][3:5] for c in self.run.call_args_list], [['container', 'ls'], ['container', 'inspect']])

    def test_matching_legacy_container_can_be_reused(self):
        self.write_file(legacy_settings('55487'))
        self.run.side_effect = [Mock(stdout='fake-id\n'), Mock(stdout='acsc483\nbridge\n'
                                '{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"55487"}]}\n'),
                                Mock(returncode=0), Mock(returncode=0, stdout='1\n')]
        with patch.dict(os.environ, {'DOCKER_HOST': 'unix:///mock-docker.sock'}):
            local_db.main()
        start, probe = self.run.call_args_list[2:]
        self.assertEqual(start.args[0][3:], ['start', local_db.NAME])
        self.assertIn('PGHOSTADDR=127.0.0.1', probe.args[0])
        self.assertIn('hotel_a', probe.args[0])

    def test_unexpected_native_listener_blocks_createdb_and_migrations(self):
        self.write_file(legacy_settings('55488'))
        data = self.root / '.local' / 'pgdata'
        data.mkdir(parents=True)
        (data / 'PG_VERSION').touch()
        self.run.side_effect = [Mock(returncode=0), Mock(stdout=f'{self.root / "other-cluster"}\t127.0.0.1\tf\n')]
        with patch.object(native_db, 'available', return_value=True), self.assertRaisesRegex(SystemExit, 'listener'):
            run_local.main()
        self.assertEqual([Path(c.args[0][0]).name for c in self.run.call_args_list], ['pg_ctl.exe', 'psql.exe'])
        self.popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
