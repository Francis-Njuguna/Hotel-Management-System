"""Stable API capabilities mapped to real Django permissions and staff groups."""
CAPS = set('dashboard.view guests.view guests.manage rooms.view rooms.manage reservations.view reservations.manage housekeeping.view housekeeping.work housekeeping.manage maintenance.view maintenance.work maintenance.manage restaurant.view restaurant.work restaurant.manage billing.view billing.manage parking.view parking.manage staff.manage audit.view'.split())
ROLES = {
    'Super Administrator': CAPS,
    'Hotel Manager': CAPS - {'staff.manage'},
    'Receptionist': set('dashboard.view guests.view guests.manage rooms.view reservations.view reservations.manage parking.view parking.manage billing.view'.split()),
    'Housekeeping Staff': {'dashboard.view','housekeeping.view','housekeeping.work'},
    'Restaurant Staff': {'dashboard.view','restaurant.view','restaurant.work','restaurant.manage'},
    'Accountant': {'dashboard.view','billing.view','billing.manage'},
    'Maintenance Staff': {'dashboard.view','maintenance.view','maintenance.work'},
}


def codename(capability):
    return capability.replace('.', '_')


def can(user, capability):
    if not (user and user.is_authenticated and user.is_active and capability in CAPS): return False
    if user.is_superuser: return True
    if not hasattr(user,'_hms_role_ceiling'):
        names = [g.name for g in user.groups.all() if g.name in ROLES]
        user._hms_role_ceiling = ROLES[names[0]] if len(names) == 1 else set()
    return capability in user._hms_role_ceiling and user.has_perm(f'core.{codename(capability)}')


def is_manager(user):
    return bool(user.is_active and (user.is_superuser or user.groups.filter(name__in=['Super Administrator','Hotel Manager']).exists()))


def sync_roles(sender=None, using='default', **kwargs):
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType
    from .models import StaffProfile
    ct = ContentType.objects.db_manager(using).get_for_model(StaffProfile)
    perms = {cap: Permission.objects.using(using).get_or_create(content_type=ct,codename=codename(cap),
             defaults={'name':cap})[0] for cap in sorted(CAPS)}
    for name, caps in ROLES.items():
        group,_ = Group.objects.using(using).get_or_create(name=name)
        group.permissions.set([perms[c] for c in caps])
