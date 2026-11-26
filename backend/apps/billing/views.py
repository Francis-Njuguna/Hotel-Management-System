from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.access import can
from apps.core.api import SecureViewSet

from . import services
from .access import has_finance_scope, require_finance
from .models import Invoice, Payment
from .serializers import (
    ChargeCommand, InvoiceDetailSerializer, InvoiceFilters, InvoiceItemSerializer, InvoiceSerializer,
    PaymentCommand, PaymentFilters, PaymentSerializer,
)


def _filters(schema, params):
    validator = schema(data=params)
    validator.is_valid(raise_exception=True)
    return validator.validated_data


def _filter_payments(rows, params):
    filters = _filters(PaymentFilters, params)
    if "reservation" in filters:
        rows = rows.filter(invoice__reservation_id=filters["reservation"])
    if "status" in filters:
        rows = rows.filter(invoice__closed_at__isnull=filters["status"] == "open")
    if "invoice" in filters:
        rows = rows.filter(invoice_id=filters["invoice"])
    if "method" in filters:
        rows = rows.filter(method=filters["method"])
    return rows


class FinanceViewSet(SecureViewSet):
    finance_actions = frozenset()
    lookup_value_regex = r"[0-9]+"

    def check_permissions(self, request):
        super().check_permissions(request)
        if self.action in self.finance_actions:
            require_finance(request.user)


@extend_schema_view(list=extend_schema(parameters=[InvoiceFilters]))
class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, FinanceViewSet):
    serializer_class = InvoiceSerializer
    search_fields = ["=id", "=reservation__id"]
    access = {
        "list": "billing.view", "retrieve": "billing.view", "payments": "billing.view",
        "charges": "billing.manage", "receive_payment": "billing.manage",
    }
    finance_actions = {"charges", "receive_payment"}

    def get_serializer_class(self):
        return InvoiceDetailSerializer if self.action == "retrieve" else InvoiceSerializer

    def get_queryset(self):
        rows = Invoice.objects.all()
        if getattr(self, "swagger_fake_view", False) or not can(self.request.user, "billing.view"):
            return rows.none()
        finance = has_finance_scope(self.request.user)
        if not finance:
            # Applied to detail, nested lookups, counts and search, not just the list UI.
            rows = rows.filter(reservation__isnull=False)
        if self.action == "list":
            filters = _filters(InvoiceFilters, self.request.query_params)
            if not finance and "reservation" not in filters:
                # A status/search/page parameter is not a folio lookup. Return an
                # empty page, never the count or balances of unrelated stays.
                return rows.none()
            if "reservation" in filters:
                rows = rows.filter(reservation_id=filters["reservation"])
            if "status" in filters:
                rows = rows.filter(closed_at__isnull=filters["status"] == "open")
            return rows.with_totals()
        if self.action == "retrieve":
            return rows.select_for_update(of=("self",))
        return rows

    @transaction.atomic
    def retrieve(self, request, *args, **kwargs):
        # Under READ COMMITTED separate prefetch queries could otherwise disagree
        # with the summary during a posting. Lock only this invoice, then read all
        # figures/children after that lock. No reservation/order lock follows it.
        invoice = self.get_object()
        detail = Invoice.objects.with_totals().prefetch_related("items", "payments").get(pk=invoice.pk)
        return Response(self.get_serializer(detail).data)

    @extend_schema(request=ChargeCommand, responses={200: InvoiceItemSerializer, 201: InvoiceItemSerializer})
    @action(detail=True, methods=["post"])
    def charges(self, request, pk=None):
        item, created = services.post_charge(self.get_object(), request.user, request.data)
        return Response(InvoiceItemSerializer(item).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(parameters=[PaymentFilters], responses=PaymentSerializer(many=True))
    @action(detail=True, methods=["get"])
    def payments(self, request, pk=None):
        invoice = self.get_object()
        rows = _filter_payments(Payment.objects.filter(invoice=invoice), request.query_params)
        page = self.paginate_queryset(rows)
        return self.get_paginated_response(PaymentSerializer(page, many=True).data)

    @extend_schema(request=PaymentCommand, responses={200: PaymentSerializer, 201: PaymentSerializer})
    @payments.mapping.post
    def receive_payment(self, request, pk=None):
        payment, created = services.record_payment(self.get_object(), request.user, request.data)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema_view(list=extend_schema(parameters=[PaymentFilters]))
class PaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, FinanceViewSet):
    serializer_class = PaymentSerializer
    search_fields = ["reference", "=id", "=invoice__id"]
    access = {"list": "billing.manage", "retrieve": "billing.view"}
    finance_actions = {"list"}  # hotel-wide tender register, not a reception folio lookup

    def get_queryset(self):
        rows = Payment.objects.all()
        if getattr(self, "swagger_fake_view", False) or not can(self.request.user, "billing.view"):
            return rows.none()
        if not has_finance_scope(self.request.user):
            rows = rows.filter(invoice__reservation__isnull=False)
        if self.action == "list":
            rows = _filter_payments(rows, self.request.query_params)
        return rows
