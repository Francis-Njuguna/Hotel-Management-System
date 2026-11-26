from decimal import Decimal, localcontext

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MAX_MONEY = Decimal("9999999999.99")  # numeric(12,2)
# Sums are not limited to a single unit price or tender. This covers even a
# BigAutoField's worth of lines at the maximum integer quantity and unit price.
TOTAL_DIGITS = 42


class ExactMoneyField(models.DecimalField):
    """Do not let a Python float or excess fractional digits become a rounded receipt."""

    def to_python(self, value):
        if isinstance(value, (float, bool)):
            raise ValidationError("Use an exact decimal value for KES.")
        number = super().to_python(value)
        if number is not None and (number.as_tuple().exponent < -self.decimal_places or number.copy_abs() > MAX_MONEY):
            raise ValidationError("KES values allow ten integer digits and at most two decimal places.")
        return number

    def pre_save(self, model_instance, add):
        # A freshly inserted posting must behave the same as one read back from
        # PostgreSQL (Django normally leaves a supplied decimal string on the instance).
        number = self.to_python(super().pre_save(model_instance, add))
        setattr(model_instance, self.attname, number)
        return number


class InvoiceQuerySet(models.QuerySet):
    def with_totals(self):
        """Two independent sums. Joining lines to tenders would multiply both."""
        money = models.DecimalField(max_digits=TOTAL_DIGITS, decimal_places=2)
        lines = (
            InvoiceItem.objects.filter(invoice_id=OuterRef("pk")).order_by()
            .values("invoice_id").annotate(value=Sum(F("quantity") * F("unit_price")))
        )
        tenders = (
            Payment.objects.filter(invoice_id=OuterRef("pk")).order_by()
            .values("invoice_id").annotate(value=Sum("amount"))
        )

        def subtotal(rows):
            return Coalesce(Subquery(rows.values("value"), output_field=money), Value(ZERO), output_field=money)

        return self.annotate(_total=subtotal(lines), _paid=subtotal(tenders))


class Invoice(models.Model):
    reservation = models.OneToOneField(
        "lodging.Reservation", on_delete=models.PROTECT, null=True, blank=True, related_name="invoice",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True, editable=False)
    objects = InvoiceQuerySet.as_manager()

    class Meta:
        ordering = ["-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(closed_at__isnull=True) | Q(closed_at__gte=F("created_at")),
                name="billing_close_after_creation",
            ),
        ]

    def _amounts(self):
        if hasattr(self, "_total") and hasattr(self, "_paid"):
            return self._total, self._paid
        return type(self).objects.with_totals().values_list("_total", "_paid").get(pk=self.pk)

    def refresh_from_db(self, *args, **kwargs):
        super().refresh_from_db(*args, **kwargs)
        # Django refreshes concrete fields, not annotations from an old list snapshot.
        self.__dict__.pop("_total", None)
        self.__dict__.pop("_paid", None)

    @property
    def total(self):
        return self._amounts()[0]

    @property
    def paid(self):
        return self._amounts()[1]

    @property
    def balance(self):
        total, paid = self._amounts()
        with localcontext() as ctx:
            ctx.prec = TOTAL_DIGITS
            return total - paid

    @property
    def status(self):
        return "closed" if self.closed_at is not None else "open"


class PostingQuerySet(models.QuerySet):
    """No ordinary ORM path may rewrite a posted line or tender."""

    def update(self, **kwargs):
        raise ValidationError("Posted entries cannot be updated.")

    def delete(self):
        raise ValidationError("Posted entries cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Posted entries cannot be updated.")

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
                    update_fields=None, unique_fields=None):
        if update_conflicts or ignore_conflicts:
            raise ValidationError("Posted entries must be inserted without overwriting or dropping conflicts.")
        objs = list(objs)
        for obj in objs:
            obj.clean()
        return super().bulk_create(objs, batch_size=batch_size)


class Posting(models.Model):
    objects = PostingQuerySet.as_manager()

    class Meta:
        abstract = True
        # Descendants inherit this manager for reverse-FK .add() as well; a
        # posted child must not be moved to another invoice by a bulk update.
        base_manager_name = "objects"

    def save(self, *, force_insert=False, force_update=False, using=None, update_fields=None):
        if not self._state.adding or force_update or update_fields is not None:
            raise ValidationError("Posted entries cannot be updated.")
        self.clean()
        # Also prevents a new instance with an explicit, existing PK being used to overwrite it.
        return super().save(force_insert=True, using=using)

    def delete(self, *args, **kwargs):
        raise ValidationError("Posted entries cannot be deleted.")


class InvoiceItem(Posting):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="items")
    description = models.TextField()
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = ExactMoneyField(max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)])
    source_key = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="billing_line_positive_qty"),
            # The upper bound also excludes PostgreSQL numeric 'NaN', which compares greater than 0.
            models.CheckConstraint(
                condition=Q(unit_price__gte=ZERO, unit_price__lte=MAX_MONEY), name="billing_line_price_range",
            ),
            models.CheckConstraint(condition=Q(source_key__regex=r"\S"), name="billing_line_has_source"),
            models.CheckConstraint(condition=Q(description__regex=r"\S"), name="billing_line_has_description"),
        ]

    def clean(self):
        # IntegerField normally truncates a fractional Python value before SQL.
        # All service/serializer inputs have already been converted to exact ints.
        if type(self.quantity) is not int:
            raise ValidationError({"quantity": "Use a whole-number quantity, not a rounded value."})

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    BANK = "bank", "Bank"
    MOBILE_MONEY = "mobile_money", "Mobile money"
    CARD = "card", "Card"


class Payment(Posting):
    Method = PaymentMethod
    # The composite owner/time index below also supports invoice-only lookups.
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments", db_index=False)
    amount = ExactMoneyField(max_digits=12, decimal_places=2, validators=[MinValueValidator(CENT)])
    method = models.CharField(max_length=16, choices=PaymentMethod.choices)
    reference = models.CharField(max_length=128, unique=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_tenders")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["invoice", "created_at"], name="billing_pay_inv_time_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=ZERO, amount__lte=MAX_MONEY), name="billing_tender_amount_range",
            ),
            models.CheckConstraint(condition=Q(method__in=PaymentMethod.values), name="billing_tender_method"),
            models.CheckConstraint(condition=Q(reference__regex=r"^\S(.*\S)?$"), name="billing_tender_has_reference"),
        ]

    @property
    def receipt_number(self):
        # One printable identifier per actual tender, not per invoice or per HTTP attempt.
        return f"RCT-{self.pk:08d}" if self.pk is not None else None
