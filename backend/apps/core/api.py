from rest_framework import status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission
from rest_framework.views import exception_handler
from .access import can


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This operation conflicts with the current record.'
    default_code = 'conflict'


class ActionPermission(BasePermission):
    def has_permission(self, request, view):
        return can(request.user, view.access.get(getattr(view, 'action', None)))


class SecureViewSet(viewsets.GenericViewSet):
    permission_classes = [ActionPermission]
    access = {}


def error_response(exc, context):
    response = exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict) and 'detail' in response.data:
        response.data.setdefault('code', getattr(response.data['detail'],'code','error'))
    return response
