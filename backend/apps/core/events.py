from .models import AuditEvent, Notification


def record(user, verb, instance, summary):
    actor = user if user and getattr(user,'is_authenticated',False) else None
    event = AuditEvent.objects.create(actor=actor,verb=verb,entity=instance._meta.label_lower,
                                      object_id=str(instance.pk),summary=str(summary)[:200])
    assignee_id = getattr(instance,'assignee_id',None)
    if assignee_id and assignee_id != getattr(actor,'pk',None):
        Notification.objects.create(recipient_id=assignee_id,title='Assigned work updated',message=f'{instance._meta.verbose_name.capitalize()} #{instance.pk}: {getattr(instance,"status", "updated")}')
    return event
