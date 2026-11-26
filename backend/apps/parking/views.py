from django.db.models import Exists, OuterRef, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import SecureViewSet

from . import services
from .models import Allocation, ParkingSpace, Vehicle, normalize_plate
from .serializers import (
    AllocationQuery, AllocationSerializer, ParkingSpaceSerializer, ReleaseRequest,
    SpaceQuery, VehicleQuery, VehicleSerializer,
)


class ParkingCollection(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, SecureViewSet):
    access = {"list": "parking.view", "retrieve": "parking.view", "create": "parking.manage"}
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = []  # Plate searches use the registration normalizer, not tokenized search.

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        # Use a plain mapping: an absent BooleanField in HTML checkbox data
        # otherwise becomes False, accidentally hiding records on unfiltered lists.
        query = self.query_serializer(data=self.request.query_params.dict())
        query.is_valid(raise_exception=True)
        return self.filter_list(queryset, query.validated_data)


_active = Allocation.objects.filter(ended_at__isnull=True)


@extend_schema_view(list=extend_schema(parameters=[SpaceQuery]))
class ParkingSpaceViewSet(mixins.UpdateModelMixin, ParkingCollection):
    access = {**ParkingCollection.access, "partial_update": "parking.manage"}
    http_method_names = [*ParkingCollection.http_method_names, "patch"]
    serializer_class = ParkingSpaceSerializer
    query_serializer = SpaceQuery
    queryset = ParkingSpace.objects.annotate(occupied=Exists(_active.filter(space_id=OuterRef("pk"))))

    def filter_list(self, qs, params):
        if term := params.get("search"):
            qs = qs.filter(code__icontains=term)
        if "available" in params:
            available = Q(is_active=True, occupied=False)
            qs = qs.filter(available) if params["available"] else qs.exclude(available)
        return qs


@extend_schema_view(list=extend_schema(parameters=[VehicleQuery]))
class VehicleViewSet(ParkingCollection):
    serializer_class = VehicleSerializer
    query_serializer = VehicleQuery
    queryset = (
        Vehicle.objects.select_related("guest").only("plate", "guest__full_name")
        .annotate(allocated=Exists(_active.filter(vehicle_id=OuterRef("pk"))))
    )

    def filter_list(self, qs, params):
        if term := params.get("search"):
            qs = qs.filter(
                Q(plate__contains=normalize_plate(term))
                | Q(guest__full_name__icontains=term) | Q(guest__reference__icontains=term)
            )
        if "guest" in params:
            qs = qs.filter(guest_id=params["guest"])
        if "allocated" in params:
            qs = qs.filter(allocated=params["allocated"])
        return qs


@extend_schema_view(list=extend_schema(parameters=[AllocationQuery]))
class AllocationViewSet(ParkingCollection):
    access = {**ParkingCollection.access, "release": "parking.manage"}
    serializer_class = AllocationSerializer
    query_serializer = AllocationQuery
    queryset = (
        Allocation.objects.select_related("space", "vehicle__guest")
        .only("started_at", "ended_at", "space__code", "vehicle__plate", "vehicle__guest__full_name")
    )

    def filter_list(self, qs, params):
        if status := params.get("status"):
            qs = qs.filter(ended_at__isnull=status == "active")
        if term := params.get("search"):
            qs = qs.filter(
                Q(space__code__icontains=term) | Q(vehicle__plate__contains=normalize_plate(term))
                | Q(vehicle__guest__full_name__icontains=term) | Q(vehicle__guest__reference__icontains=term)
            )
        for param, fk in (("space", "space_id"), ("vehicle", "vehicle_id"), ("guest", "vehicle__guest_id")):
            if param in params:
                qs = qs.filter(**{fk: params[param]})
        return qs

    @extend_schema(request=ReleaseRequest, responses=AllocationSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        body = ReleaseRequest(data=request.data)
        body.is_valid(raise_exception=True)
        allocation = services.release(request.user, self.get_object())
        return Response(self.get_serializer(allocation).data)
