from rest_framework.exceptions import PermissionDenied

from apps.core.access import can, is_manager


def has_finance_scope(user):
    """A folio lookup grant alone never opens the property-wide registers."""
    return can(user, "billing.manage") and (is_manager(user) or user.groups.filter(name="Accountant").exists())


def require_finance(user):
    if not has_finance_scope(user):
        raise PermissionDenied("Hotel-wide finance access is required.")
