from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import SecureViewSet

from . import selectors, services
from .models import Guest, Reservation, Room
from .serializers import (
    AvailabilityInterval, GuestHistorySerializer, GuestSerializer, ReservationDetailSerializer,
    ReservationFilters, ReservationInput, ReservationSerializer, RoomFilters, RoomSerializer, StayCommand,
)


class CatalogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, SecureViewSet):
    """Create and PATCH catalog data; a missing DELETE is intentional."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_value_regex = r"[0-9]+"

    def _save(self, request, instance=None):
        serializer = self.get_serializer(instance=instance, data=request.data, partial=instance is not None)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            saved = self.save_profile(request.user, serializer.validated_data, pk=instance.pk if instance else None)
            result = self.get_queryset().get(pk=saved.pk)  # include server-derived room flags on writes, too
            return Response(self.get_serializer(result).data, status=status.HTTP_201_CREATED if instance is None else status.HTTP_200_OK)

    def create(self, request):
        return self._save(request)

    def partial_update(self, request, pk=None):
        return self._save(request, self.get_object())


class GuestViewSet(CatalogViewSet):
    serializer_class = GuestSerializer
    queryset = Guest.objects.all()
    search_fields = ["full_name", "reference", "email", "phone"]
    save_profile = staticmethod(services.save_guest)
    access = {"list": "guests.view", "retrieve": "guests.view", "history": "guests.view",
              "create": "guests.manage", "partial_update": "guests.manage"}

    @extend_schema(responses=GuestHistorySerializer)
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        guest = self.get_object()
        data = {"reservations": selectors.guest_visits(guest)}
        payments = selectors.guest_payments(guest, request.user)
        if payments is not None:
            data["payments"] = payments
        # Do not expose even counts or a financial key to a user without the grant.
        result = GuestHistorySerializer(data).data
        return Response(result)


@extend_schema_view(list=extend_schema(parameters=[RoomFilters]))
class RoomViewSet(CatalogViewSet):
    serializer_class = RoomSerializer
    queryset = Room.objects.all()
    search_fields = ["number", "category", "description"]
    save_profile = staticmethod(services.save_room)
    access = {"list": "rooms.view", "retrieve": "rooms.view", "availability": "rooms.view",
              "create": "rooms.manage", "partial_update": "rooms.manage"}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Room.objects.none()
        if self.action == "availability":
            interval = AvailabilityInterval(data=self.request.query_params)
            interval.is_valid(raise_exception=True)
            qs = selectors.available_rooms(**interval.validated_data)
        else:
            qs = selectors.rooms()
        if self.action in ("availability", "list"):
            # Use a plain dictionary so absent BooleanField filters stay absent
            # (DRF treats missing HTML checkboxes on a QueryDict as false).
            filters = RoomFilters(data=self.request.query_params.dict())
            filters.is_valid(raise_exception=True)
            qs = qs.filter(**filters.validated_data)
        return qs

    @extend_schema(parameters=[AvailabilityInterval, RoomFilters], responses=RoomSerializer(many=True))
    @action(detail=False, methods=["get"])
    def availability(self, request):
        return self.list(request)


@extend_schema_view(
    list=extend_schema(parameters=[ReservationFilters]),
    create=extend_schema(request=ReservationInput, responses={201: ReservationDetailSerializer}),
    partial_update=extend_schema(request=ReservationInput, responses=ReservationDetailSerializer),
)
class ReservationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, SecureViewSet):
    serializer_class = ReservationSerializer
    queryset = Reservation.objects.all()
    lookup_value_regex = r"[0-9]+"
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ["=id", "guest__full_name", "guest__reference", "claims__room__number"]
    access = {"list": "reservations.view", "retrieve": "reservations.view", "create": "reservations.manage",
              "partial_update": "reservations.manage", "confirm": "reservations.manage", "cancel": "reservations.manage",
              "check_in": "reservations.manage", "check_out": "reservations.manage"}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Reservation.objects.none()
        qs = selectors.reservations(with_events=self.action == "retrieve")
        if self.action == "list":
            filters = ReservationFilters(data=self.request.query_params)
            filters.is_valid(raise_exception=True)
            values = dict(filters.validated_data)
            if "room" in values:
                values["claims__room_id"] = values.pop("room")
            qs = qs.filter(**values)
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ReservationDetailSerializer
        return super().get_serializer_class()

    @transaction.atomic
    def _apply_and_respond(self, operation, *args, code=status.HTTP_200_OK, **kwargs):
        # Keep the command's locks through response projection. A racing second
        # transition must not replace this command's status, room list or timeline.
        reservation = operation(*args, **kwargs)
        result = selectors.reservations(with_events=True).get(pk=reservation.pk)
        return Response(ReservationDetailSerializer(result, context=self.get_serializer_context()).data, status=code)

    def create(self, request):
        serializer = ReservationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._apply_and_respond(services.create_reservation, request.user, code=status.HTTP_201_CREATED, **serializer.validated_data)

    def partial_update(self, request, pk=None):
        reservation = self.get_object()
        serializer = ReservationInput(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return self._apply_and_respond(services.amend_reservation, reservation.pk, request.user, **serializer.validated_data)

    def _command(self, request, operation):
        reservation = self.get_object()
        StayCommand(data=request.data).is_valid(raise_exception=True)
        return self._apply_and_respond(operation, reservation.pk, request.user)

    @extend_schema(request=StayCommand, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self._command(request, services.confirm)

    @extend_schema(request=StayCommand, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._command(request, services.cancel)

    @extend_schema(request=StayCommand, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"])
    def check_in(self, request, pk=None):
        return self._command(request, services.check_in)

    @extend_schema(request=StayCommand, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"])
    def check_out(self, request, pk=None):
        return self._command(request, services.check_out)
