from django.conf import settings
from django.db import models
from .access import CAPS, codename


class StaffProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='staff_profile')
    department = models.CharField(max_length=80,blank=True)
    session_version = models.PositiveBigIntegerField(default=0,editable=False)
    verified_email = models.EmailField(blank=True,editable=False)

    class Meta:
        permissions = [(codename(cap),cap) for cap in sorted(CAPS)]


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    verb = models.CharField(max_length=64)
    entity = models.CharField(max_length=100)
    object_id = models.BigIntegerField()
    summary = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['entity','object_id','created_at'])]


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    title = models.CharField(max_length=160)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True,blank=True)

    class Meta:
        indexes = [models.Index(fields=['recipient','created_at'],name='notice_unread_idx',condition=models.Q(read_at__isnull=True))]
        constraints = [models.CheckConstraint(condition=models.Q(read_at__isnull=True)|models.Q(read_at__gte=models.F('created_at')),name='notice_read_after_create')]
