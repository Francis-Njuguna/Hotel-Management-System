from decimal import Decimal
from django.db.models import DecimalField, F, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import can, is_manager
from .feeds import NotificationSerializer
from .models import Notification
from .schema import DashboardSchema


class DashboardView(APIView):
    """Never leak a department's work through an unscoped dashboard projection."""
    @extend_schema(responses=DashboardSchema)
    def get(self,request):
        from apps.billing.models import InvoiceItem, Payment
        from apps.housekeeping.models import CleaningTask
        from apps.lodging.models import Guest, Reservation, Room, RoomClaim
        from apps.restaurant.models import Order
        u, today = request.user, timezone.localdate()
        if not can(u,'dashboard.view'): raise PermissionDenied()
        metrics = {}
        data = {'date':today,'metrics':metrics,'notifications':NotificationSerializer(
            Notification.objects.filter(recipient=u,read_at__isnull=True).order_by('-id')[:8],many=True).data}
        if can(u,'reservations.view'):
            reservations = Reservation.objects.exclude(status__in=['pending','cancelled'])
            metrics.update(check_ins=reservations.filter(arrival=today).count(),check_outs=reservations.filter(departure=today).count())
            data['reservations'] = list(Reservation.objects.select_related('guest').order_by('-created_at','-id').values(
                'id','arrival','departure','status',guest_name=F('guest__full_name'))[:8])
        if can(u,'rooms.view'):
            claims = RoomClaim.objects.all()
            occupied = claims.filter(reservation__status='checked_in').values('room_id')
            tonight = claims.filter(blocking=True,start__lte=today,end__gt=today)
            metrics.update(available_rooms=Room.objects.filter(is_active=True).exclude(pk__in=tonight.values('room_id')).exclude(pk__in=occupied).count(),
                           occupied_rooms=occupied.distinct().count(),reserved_rooms=tonight.filter(reservation__status='confirmed').values('room_id').distinct().count(),
                           cleaning_rooms=Room.objects.filter(cleanliness='dirty').count())
        if can(u,'guests.view'): metrics['total_guests'] = Guest.objects.count()
        if can(u,'billing.manage'):
            decimal = DecimalField(max_digits=24,decimal_places=2)
            billed = InvoiceItem.objects.filter(created_at__date=today).aggregate(v=Sum(F('quantity')*F('unit_price'),output_field=decimal))['v']
            collected = Payment.objects.filter(created_at__date=today).aggregate(v=Sum('amount'))['v']
            metrics.update(billed=format(billed or Decimal(0),'.2f'),collected=format(collected or Decimal(0),'.2f'))
        if can(u,'restaurant.view'):
            data['orders'] = list(Order.objects.order_by('-id').values('id','status')[:8])
        if can(u,'housekeeping.view'):
            tasks = CleaningTask.objects.exclude(status='inspected')
            if not is_manager(u): tasks = tasks.filter(assignee=u)
            data['tasks'] = list(tasks.order_by('-id').values('id','status',room_number=F('room__number'))[:8])
        return Response(data)
