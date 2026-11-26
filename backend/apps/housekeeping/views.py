from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import SecureViewSet

from . import services
from .models import CleaningTask, MaintenanceRequest
from .serializers import (
    CleaningFilters, CleaningTaskSerializer, CreateCleaningTaskSerializer, MaintenanceFilters,
    MaintenanceRequestSerializer, OpenMaintenanceSerializer, ResolveMaintenanceSerializer,
    TransitionCleaningTaskSerializer,
)


class RoomWorkViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, SecureViewSet):
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset.none()
        return self.visible_for(self.request.user).select_related("room", "assignee").order_by("-created_at", "-pk")

    def filter_queryset(self, queryset):
        # Filter *within* the scoped set. Pagination, search, counts and detail lookups
        # therefore cannot expose somebody else's work even with an explicit assignee ID.
        filters = self.filters_class(data=self.request.query_params.dict())
        filters.is_valid(raise_exception=True)
        return super().filter_queryset(queryset.filter(**filters.validated_data))


@extend_schema_view(list=extend_schema(parameters=[CleaningFilters]))
class CleaningTaskViewSet(RoomWorkViewSet):
    queryset = CleaningTask.objects.none()
    serializer_class = CleaningTaskSerializer
    filters_class = CleaningFilters
    visible_for = staticmethod(services.visible_cleaning_tasks)
    search_fields = ["room__number", "notes", "assignee__first_name", "assignee__last_name", "assignee__username"]
    access = {
        "list": "housekeeping.view", "retrieve": "housekeeping.view",
        "create": "housekeeping.manage", "transition": "housekeeping.work",
    }

    @extend_schema(request=CreateCleaningTaskSerializer, responses={201: CleaningTaskSerializer})
    def create(self, request):
        command = CreateCleaningTaskSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        task = services.create_cleaning_task(request.user, **command.validated_data)
        return Response(self.get_serializer(task).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=TransitionCleaningTaskSerializer, responses=CleaningTaskSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        task = self.get_object()
        command = TransitionCleaningTaskSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        task = services.transition_cleaning_task(task, request.user, **command.validated_data)
        return Response(self.get_serializer(task).data)


@extend_schema_view(list=extend_schema(parameters=[MaintenanceFilters]))
class MaintenanceRequestViewSet(RoomWorkViewSet):
    queryset = MaintenanceRequest.objects.none()
    serializer_class = MaintenanceRequestSerializer
    filters_class = MaintenanceFilters
    visible_for = staticmethod(services.visible_maintenance)
    search_fields = ["room__number", "description", "assignee__first_name", "assignee__last_name", "assignee__username"]
    access = {
        "list": "maintenance.view", "retrieve": "maintenance.view",
        "create": "maintenance.manage", "resolve": "maintenance.work",
    }

    @extend_schema(request=OpenMaintenanceSerializer, responses={201: MaintenanceRequestSerializer})
    def create(self, request):
        command = OpenMaintenanceSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        work = services.open_maintenance(request.user, **command.validated_data)
        return Response(self.get_serializer(work).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ResolveMaintenanceSerializer, responses=MaintenanceRequestSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        work = self.get_object()
        command = ResolveMaintenanceSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        work = services.resolve_maintenance(work, request.user)
        return Response(self.get_serializer(work).data)
