from django.http import FileResponse, Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework import mixins, serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import can
from .api import SecureViewSet
from .models import AuditEvent, Notification


class AuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.username',read_only=True,allow_null=True)
    class Meta:
        model = AuditEvent
        fields = ['id','actor','actor_name','verb','entity','object_id','summary','created_at']


class AuditViewSet(mixins.ListModelMixin,SecureViewSet):
    serializer_class = AuditSerializer
    queryset = AuditEvent.objects.select_related('actor').order_by('-id')
    search_fields = ['verb','entity','actor__username']
    access = {'list':'audit.view'}


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id','title','message','read_at','created_at']


class NotificationViewSet(mixins.ListModelMixin,SecureViewSet):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.none()
    access = {'list':'dashboard.view','read':'dashboard.view'}
    def get_queryset(self): return Notification.objects.filter(recipient=self.request.user).order_by('-id')

    @extend_schema(request=None,responses=NotificationSerializer)
    @action(detail=True,methods=['post'])
    def read(self,request,pk=None):
        n=self.get_object()
        if not n.read_at:
            n.read_at=timezone.now(); n.save(update_fields=['read_at'])
        return Response(self.get_serializer(n).data)


class MediaView(APIView):
    permission_classes = [IsAuthenticated]
    @extend_schema(responses={(200,'image/jpeg'):OpenApiTypes.BINARY})
    def get(self,request,key):
        from apps.lodging.models import Room
        from apps.restaurant.models import MenuItem
        if '..' in key or '\\' in key or len(key)>255: raise Http404
        for cap,model in [('rooms.view',Room),('restaurant.view',MenuItem)]:
            if can(request.user,cap):
                row = model.objects.filter(image=key).only('image').first()
                if row and row.image:
                    try: return FileResponse(row.image.open('rb'),content_type='image/jpeg')
                    except FileNotFoundError: raise Http404
        raise Http404
