"""Exercise browser writes, then recover their DB/media, without modifying the demo.

Run with the project's virtualenv after npm ci / Playwright browser installation.
Set PLAYWRIGHT_CHANNEL=msedge to use installed Edge instead of bundled Chromium.
"""
from contextlib import closing, ExitStack
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler
from uuid import uuid4

import psycopg
from psycopg import sql
import demo_config as demo
from verify_restore import existing_demo, rehearse

ROOT=Path(__file__).resolve().parents[1]
local_http=build_opener(ProxyHandler({}))


def wait_ready(proc, url):
    deadline=monotonic()+60
    while monotonic()<deadline:
        if proc.poll() is not None: raise RuntimeError('Acceptance server stopped on startup.')
        try:
            with local_http.open(url, timeout=2) as result:
                if result.status==200: return
        except (OSError,URLError): pass
        sleep(.25)
    raise RuntimeError('Acceptance server did not become ready.')


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keyboard-only',action='store_true',help='Run the narrow keyboard walkthrough on its own fresh fixture.')
    options=parser.parse_args()
    cfg=existing_demo()
    for port in (8019,5189):
        with socket.socket() as sock: sock.bind(('127.0.0.1',port))
    name='hms_e2e_'+uuid4().hex[:16]
    params=dict(dbname='postgres',host=demo.HOST,hostaddr=demo.HOST,port=cfg['POSTGRES_PORT'],user=cfg['POSTGRES_USER'],password=cfg['POSTGRES_PASSWORD'],connect_timeout=12)
    api='http://127.0.0.1:8019'; ui='http://127.0.0.1:5189'
    with closing(psycopg.connect(autocommit=True, **params)) as admin, tempfile.TemporaryDirectory(dir=ROOT/'.local') as temp:
        temp=Path(temp); media=temp/'media'; media.mkdir()
        tools=demo.system_env(os.environ)
        env={**tools,**cfg,'PYTHON_DOTENV_DISABLED':'1','POSTGRES_DB':name,'HMS_ENV':'local','HMS_DEBUG':'1','HMS_MEDIA_ROOT':str(media),
             'HMS_API_TARGET':api,'HMS_PUBLIC_URL':ui,'HMS_CSRF_TRUSTED_ORIGINS':ui,'HMS_SECRET_KEY':secrets.token_urlsafe(50),
             'HMS_DEMO_USER':'qa.browser','HMS_DEMO_PASSWORD':secrets.token_urlsafe(32),'E2E_BASE_URL':ui,'HMS_E2E_DISPOSABLE':'1'}
        # Do not expose DB secrets to the browser through VITE_* or send real mail.
        env['HMS_EMAIL_HOST']=''; env['HMS_SECURE_COOKIES']='0'
        args=[sys.executable,'manage.py']; back=ROOT/'backend'; front=ROOT/'frontend'
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            def manage(*cmd): subprocess.run([*args,*cmd],cwd=back,env=env,check=True)
            manage('migrate','--noinput','--verbosity','0'); manage('seed_demo')
            # A generated image exercises storage recovery. It lives only in this private fixture.
            manage('shell','-v','0','-c','''
import os
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from apps.lodging.models import Room
user=get_user_model().objects.create_user(username=os.environ['HMS_DEMO_USER'],password=os.environ['HMS_DEMO_PASSWORD'],first_name='Browser',last_name='Fixture')
user.groups.add(Group.objects.get(name='Super Administrator'))
buf=BytesIO(); Image.new('RGB',(4,4),'navy').save(buf,format='JPEG')
Room.objects.get(number='D101').image.save('test-catalog.jpg',ContentFile(buf.getvalue()))
''')
            node=shutil.which('node');
            if not node: sys.exit('Node.js is required.')
            with ExitStack() as resources:
                def start(cmd,cwd,process_env):
                    log=resources.enter_context(open(temp/(cwd.name+'.log'),'wb'))
                    process=subprocess.Popen(cmd,cwd=cwd,env=process_env,stdout=log,stderr=subprocess.STDOUT)
                    resources.callback(stop,process);return process
                backend=start([*args,'runserver','127.0.0.1:8019','--noreload'],back,env)
                wait_ready(backend,api+'/api/v1/auth/me/')
                vite=start([node,'node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5189','--strictPort'],front,{**tools,'HMS_API_TARGET':api})
                wait_ready(vite,ui+'/')
                with local_http.open(ui+'/api/v1/auth/me/',timeout=5) as response:
                    if json.load(response)!={'user':None}: raise RuntimeError('Anonymous bootstrap failed.')
                runner={**tools, **{k:env[k] for k in ('HMS_DEMO_USER','HMS_DEMO_PASSWORD','E2E_BASE_URL','HMS_E2E_DISPOSABLE')},
                        'PLAYWRIGHT_CHANNEL':os.getenv('PLAYWRIGHT_CHANNEL','')}
                selected=[]
                if options.keyboard_only:
                    runner['HMS_E2E_KEYBOARD']='1'; selected=['keyboard.spec.ts']
                subprocess.run([node,'node_modules/@playwright/test/cli.js','test','--config=e2e/playwright.config.ts',*selected],cwd=front,env=runner,check=True)
            rehearse(env, media)
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


if __name__=='__main__': main()
