import time
from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from .models import StaffProfile


class SessionLifetimeMiddleware:
    """Apply an absolute and idle deadline without relying on the browser clock."""
    def __init__(self,get_response): self.get_response = get_response

    def __call__(self,request):
        if request.user.is_authenticated:
            now = int(time.time())
            started = request.session.get('started_at',now)
            last = request.session.get('last_seen',now)
            version = StaffProfile.objects.filter(user_id=request.user.pk).values_list('session_version',flat=True).first() or 0
            if (version != request.session.get('staff_version',0) or now-started >= settings.SESSION_COOKIE_AGE
                    or now-last >= settings.SESSION_IDLE_SECONDS):
                logout(request)
            else:
                if 'started_at' not in request.session: request.session['started_at'] = now
                if 'last_seen' not in request.session or now-last >= 60: request.session['last_seen'] = now
        expected = request.headers.get('X-Hotel-Operator')
        if (expected and request.path.startswith('/api/v1/') and request.method not in ('GET','HEAD','OPTIONS')
                and expected != str(request.user.pk)):
            response = JsonResponse({'code':'operator_changed','detail':'The signed-in operator changed. Review the screen before submitting again.'},status=409)
        else:
            response = self.get_response(request)
        if request.path.startswith('/api/'):
            response['Cache-Control'] = 'private, no-store'
        return response
