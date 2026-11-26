"""Read-only source/restore comparison: pipe into `python manage.py shell -v 0`."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db.models import DecimalField, ExpressionWrapper, F, FileField, Sum

models = sorted(
    (m for m in apps.get_models(include_auto_created=True) if m._meta.managed and not m._meta.proxy),
    key=lambda m: m._meta.label,
)
rows = {m._meta.label: m._base_manager.count() for m in models}
line_total = ExpressionWrapper(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=38, decimal_places=2))


def kes(model, expression):
    total = apps.get_model("billing", model).objects.aggregate(n=Sum(expression))["n"]
    return format(total if total is not None else Decimal(0), ".2f")


root = Path(settings.MEDIA_ROOT).resolve(strict=True)
names = set()
inventory = hashlib.sha256()
for path in sorted(root.rglob("*")):
    if path.is_symlink() or not (path.is_file() or path.is_dir()):
        raise SystemExit("Unexpected non-regular media entry; review privately before backup.")
    if path.is_file():
        name = path.relative_to(root).as_posix()
        names.add(name)
        with path.open("rb") as stream:
            inventory.update(name.encode("utf-8") + b"\0" + hashlib.file_digest(stream, "sha256").digest())

for model in models:
    for field in model._meta.fields:
        if isinstance(field, FileField):
            keys = model._base_manager.values_list(field.attname, flat=True).iterator()
            if any(key and key not in names for key in keys):
                raise SystemExit(f"Missing media referenced by {model._meta.label}.{field.name}.")

print(json.dumps({
    "rows": rows,
    "billed_kes": kes("InvoiceItem", line_total),
    "received_kes": kes("Payment", "amount"),
    "media_files": len(names),
    "media_names_and_contents_sha256": inventory.hexdigest(),
}, sort_keys=True))
