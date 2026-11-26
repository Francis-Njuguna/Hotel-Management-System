from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.api import SecureViewSet
from apps.core.events import record
from apps.lodging.models import Reservation, RoomClaim

from . import services
from .models import MenuItem, Order, OrderItem, OrderStatus
from .serializers import (
    AssignmentInput, MenuItemSerializer, OrderCreateInput, OrderSerializer, OrderStaySerializer, TransitionInput,
)


class MenuItemViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      mixins.UpdateModelMixin, SecureViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    parser_classes = [JSONParser, MultiPartParser]
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_value_regex = "[0-9]{1,19}"
    search_fields = ["name", "category", "description"]
    access = {
        "list": "restaurant.view", "retrieve": "restaurant.view",
        "create": "restaurant.manage", "partial_update": "restaurant.manage",
    }

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            available = self.request.query_params.get("available", "").strip().lower()
            if available:
                if available not in ("true", "false", "1", "0"):
                    raise ValidationError({"available": "Use true or false."})
                qs = qs.filter(available=available in ("true", "1"))
            category = self.request.query_params.get("category", "").strip()
            if category:
                qs = qs.filter(category__iexact=category)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        item = serializer.save()
        record(self.request.user, "menu.created", item, "Menu item created")

    @transaction.atomic
    def perform_update(self, serializer):
        # Decode/validate the upload before taking a catalog lock. Re-read under
        # that lock so an unrelated PATCH cannot silently undo a withdrawal.
        serializer.instance = get_object_or_404(MenuItem.objects.select_for_update(), pk=serializer.instance.pk)
        old_image = serializer.instance.image.name
        item = serializer.save()
        record(self.request.user, "menu.updated", item, "Menu item updated")
        if old_image and old_image != item.image.name:
            storage = MenuItem._meta.get_field("image").storage
            transaction.on_commit(lambda: storage.delete(old_image), robust=True)


def orders_for_display():
    lines = (OrderItem.objects.select_related("menu_item").order_by("pk")
             .only("id", "order_id", "menu_item_id", "menu_item__name", "quantity", "unit_price"))
    return (Order.objects.select_related("reservation", "room", "assignee")
            .only("id", "reservation_id", "reservation__guest_id", "room_id", "room__number", "assignee_id",
                  "assignee__first_name", "assignee__last_name", "assignee__username", "status", "created_at")
            .prefetch_related(Prefetch("items", queryset=lines)))


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, SecureViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    parser_classes = [JSONParser]
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_value_regex = "[0-9]{1,19}"
    search_fields = ["=id", "room__number", "items__menu_item__name"]
    access = {
        "list": "restaurant.view", "retrieve": "restaurant.view", "create": "restaurant.work",
        "partial_update": "restaurant.work", "transition": "restaurant.work", "stays": "restaurant.work",
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not services.has_order_scope(self.request.user):
            return Order.objects.none()
        if self.action in ("transition", "partial_update"):
            # Only an immutable routing hint. The command re-reads mutable state
            # under the parent/order locks without joining nullable foreign keys.
            return Order.objects.only("id", "reservation_id", "room_id", "status")
        qs = orders_for_display()
        if self.action == "list":
            state = self.request.query_params.get("status", "").strip()
            if state:
                if state not in OrderStatus.values:
                    raise ValidationError({"status": "Choose a valid order status."})
                qs = qs.filter(status=state)
        return qs

    def _order_response(self, order, code=status.HTTP_200_OK):
        saved = orders_for_display().get(pk=order.pk)
        return Response(OrderSerializer(saved, context=self.get_serializer_context()).data, status=code)

    @extend_schema(request=OrderCreateInput, responses={201: OrderSerializer})
    def create(self, request):
        command = OrderCreateInput(data=request.data)
        command.is_valid(raise_exception=True)
        order = services.create_order(user=request.user, **command.validated_data)
        return self._order_response(order, status.HTTP_201_CREATED)

    @extend_schema(request=AssignmentInput, responses=OrderSerializer)
    def partial_update(self, request, pk=None):
        order = self.get_object()
        command = AssignmentInput(data=request.data)
        command.is_valid(raise_exception=True)
        return self._order_response(services.change_order(order, request.user, **command.validated_data))

    @extend_schema(request=TransitionInput, responses=OrderSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        order = self.get_object()
        command = TransitionInput(data=request.data)
        command.is_valid(raise_exception=True)
        return self._order_response(services.change_order(order, request.user, **command.validated_data))

    @extend_schema(responses=OrderStaySerializer(many=True))
    @action(detail=False, methods=["get"], serializer_class=OrderStaySerializer, filter_backends=[])
    def stays(self, request):
        if not services.has_order_scope(request.user):
            raise PermissionDenied()
        # Not the reservation directory. Fetch only active IDs, then only room
        # IDs/numbers on this page; no guest/contact, rate or account fields.
        qs = Reservation.objects.filter(status=Reservation.Status.CHECKED_IN).order_by("pk")
        term = request.query_params.get("search", "").strip()
        if term:
            match = Q(claims__room__number__icontains=term)
            if len(term) <= 19 and term.isascii() and term.isdecimal():
                match |= Q(pk=int(term))
            qs = qs.filter(match).distinct()
        ids = self.paginate_queryset(qs.values_list("pk", flat=True))
        rooms = {stay_id: [] for stay_id in ids}
        claims = (RoomClaim.objects.filter(reservation_id__in=ids).order_by("reservation_id", "room__number", "room_id")
                  .values_list("reservation_id", "room_id", "room__number"))
        for stay_id, room_id, number in claims:
            rooms[stay_id].append({"id": room_id, "number": number})
        rows = [{"id": stay_id, "rooms": rooms[stay_id]} for stay_id in ids]
        return self.get_paginated_response(self.get_serializer(rows, many=True).data)
