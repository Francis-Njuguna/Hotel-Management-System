"""Exercise a logical backup against a newly created isolated *development* database."""
from contextlib import closing
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import uuid

import psycopg
from psycopg import sql
from dotenv import dotenv_values
import demo_config as demo

ROOT=Path(__file__).resolve().parents[1]
QUERIES={
    'guests':'SELECT count(*) FROM lodging_guest', 'rooms':'SELECT count(*) FROM lodging_room',
    'reservations':'SELECT count(*) FROM lodging_reservation', 'claims':'SELECT count(*) FROM lodging_roomclaim',
    'billed':'SELECT count(*), COALESCE(sum(quantity * unit_price),0) FROM billing_invoiceitem',
    'received':'SELECT count(*), COALESCE(sum(amount),0) FROM billing_payment',
    'tasks':'SELECT count(*) FROM housekeeping_cleaningtask','staff':'SELECT count(*) FROM auth_user',
    'extension':"SELECT extname FROM pg_extension WHERE extname='btree_gist'",
}
# Equal counts and totals can hide a different allocation or receipt. Compare all
# persisted fields in stable id order; do not print or export the rows themselves.
for _key, _table in [('calendar_rows','lodging_roomclaim'), ('receipt_rows','billing_payment')]:
    QUERIES[_key] = ("SELECT sha256(convert_to(COALESCE(jsonb_agg(to_jsonb(r) ORDER BY id)::text,'[]'),'UTF8')) "
                     f"FROM {_table} r")


def existing_demo():
    path=ROOT/'.env'
    if not path.is_file(): raise SystemExit('Start the local demo before running the rehearsal.')
    port=dotenv_values(path,interpolate=False).get('POSTGRES_PORT')
    if port not in (demo.NATIVE_PORT, demo.DOCKER_PORT): raise SystemExit('Not a local Hotel A demo port.')
    return demo.prepare(ROOT, port, os.environ)


def rehearse(cfg, media):
    db=cfg['POSTGRES_DB']
    if (cfg.get('HMS_DEBUG')!='1' or cfg['POSTGRES_HOST']!=demo.HOST or cfg['POSTGRES_USER']!='hotel_a'
            or cfg['POSTGRES_PORT'] not in (demo.NATIVE_PORT, demo.DOCKER_PORT)
            or not (db=='hotel_a' or re.fullmatch(r'hms_e2e_[a-f0-9]{16}',db))):
        raise SystemExit('This rehearsal runs only on the local Hotel A development or generated acceptance database.')
    params=dict(host=demo.HOST,hostaddr=demo.HOST,port=cfg['POSTGRES_PORT'],user=cfg['POSTGRES_USER'],password=cfg['POSTGRES_PASSWORD'],connect_timeout=10)
    env={**demo.system_env(os.environ),'PGHOST':demo.HOST,'PGHOSTADDR':demo.HOST,'PGPORT':params['port'],'PGUSER':params['user'],'PGPASSWORD':params['password'],'PGCONNECT_TIMEOUT':'10'}
    suffix='.exe' if os.name=='nt' else ''
    def tool(name):
        detected=shutil.which(name+suffix)
        return detected or str(Path(os.getenv('PG_BIN',r'C:\Program Files\PostgreSQL\18\bin'))/(name+suffix))
    def read_state(name):
        with psycopg.connect(dbname=name,**params) as c: return {k:c.execute(q).fetchone() for k,q in QUERIES.items()}
    with tempfile.TemporaryDirectory(dir=ROOT/'.local') as tmp:
        tmp=Path(tmp); scratch='hms_restore_'+uuid.uuid4().hex[:16]
        before=read_state(db)
        subprocess.run([tool('pg_dump'),'-Fc','--no-owner','-f',str(tmp/'copy.dump'),db],check=True,env=env)
        def hashes(folder):return {p.relative_to(folder):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
        media_before=hashes(media)
        if media.is_dir(): shutil.copytree(media,tmp/'media')
        with closing(psycopg.connect(dbname='postgres',autocommit=True,**params)) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(scratch)))
            try:
                subprocess.run([tool('pg_restore'),'--exit-on-error','--no-owner','-d',scratch,str(tmp/'copy.dump')],check=True,env=env)
                if read_state(scratch)!=before or media_before!=hashes(tmp/'media'): raise RuntimeError('Restore differs from the recorded baseline.')
                print(f'Restore verified: {len(QUERIES)} database checks, {len(media_before)} media files; billed {before["billed"][1]:.2f}, received {before["received"][1]:.2f} KES.')
            finally: admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(scratch)))


if __name__=='__main__': rehearse(existing_demo(), ROOT/'backend'/'media')
