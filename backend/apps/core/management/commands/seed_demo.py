"""Explicit synthetic catalog and staff accounts for a local demonstration only."""
import os
from pathlib import Path
import secrets
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import StaffProfile


class Command(BaseCommand):
    help = 'Seed a labeled synthetic catalog in a development database. Never creates payments.'

    def add_arguments(self,parser):
        parser.add_argument('--create-login',action='store_true',help='Create a local demo administrator with a random password, saved to an ignored local file.')

    @transaction.atomic
    def handle(self,*args,**opts):
        from apps.lodging.models import Room, Guest
        from apps.parking.models import ParkingSpace
        from apps.restaurant.models import MenuItem
        if not settings.DEBUG:
            raise CommandError('Demo setup is supported only with HMS_DEBUG=1 in a disposable development database.')
        for number,cat,rate,capacity,desc in [
            ('D101','Single','3600.00',1,'A quiet courtyard-facing single room.'),
            ('D102','Double','4800.00',2,'An airy double with a writing desk.'),
            ('D103','Twin','5000.00',2,'Two individual beds and a shared sitting area.'),
            ('D201','Deluxe','7200.00',2,'A bright upper-floor room with a reading corner.'),
            ('D202','Suite','11800.00',2,'A separate lounge and a spacious bedroom.'),
            ('D203','Family','8900.00',4,'Space for a family with adjoining sleeping areas.')]:
            Room.objects.get_or_create(number=number,defaults={'category':cat,'nightly_rate':rate,'capacity':capacity,
                 'description':'Demo catalog · '+desc,'facilities':['Wi-Fi','Desk'],'cleanliness':'inspected','is_active':True})
        for name,category,price in [('Demo · Kenyan breakfast','Breakfast','650.00'),('Demo · Vegetable pilau','Kitchen','780.00'),('Demo · Masala chai','Drinks','180.00')]:
            MenuItem.objects.get_or_create(name=name,defaults={'category':category,'price':price,'available':True,'description':'Synthetic demonstration menu.'})
        for key in ['D-A01','D-A02','D-B01']: ParkingSpace.objects.get_or_create(code=key,defaults={'is_active':True})
        Guest.objects.get_or_create(reference='DEMO-GUEST',defaults={'full_name':'Demo Guest','email':'demo.guest@example.invalid','phone':''})
        U = get_user_model()
        for username,role,department in [('demo.housekeeping','Housekeeping Staff','Housekeeping'),('demo.maintenance','Maintenance Staff','Engineering'),('demo.restaurant','Restaurant Staff','Restaurant')]:
            if not U.objects.filter(username=username).exists():
                staff=U.objects.create_user(username=username,first_name='Demo',last_name=department,password=None)
                staff.groups.add(Group.objects.get(name=role)); StaffProfile.objects.create(user=staff,department=department)
        if opts['create_login'] and not U.objects.filter(username='demo.administrator').exists():
            folder=Path(settings.BASE_DIR).parent/'.local'; folder.mkdir(exist_ok=True)
            path=folder/'demo-credentials.txt'
            if path.exists(): raise CommandError('Credential file already exists. Move it privately before provisioning a new local demo database.')
            password=secrets.token_urlsafe(20)
            u=U.objects.create_user(username='demo.administrator',password=password,first_name='Demo',last_name='Administrator',email='demo.admin@example.invalid')
            u.groups.add(Group.objects.get(name='Super Administrator')); StaffProfile.objects.create(user=u,department='Administration')
            with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf8') as f:
                f.write(f'Local Hotel A demonstration only\nUsername: {u.username}\nPassword: {password}\n')
            self.stdout.write('Local login saved to .local/demo-credentials.txt (private; not in Git).')
        self.stdout.write(self.style.SUCCESS('Synthetic catalog ready. No payment or completed transaction has been fabricated.'))
