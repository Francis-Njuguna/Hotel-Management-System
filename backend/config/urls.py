from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.routers import SimpleRouter
from apps.core import auth_views as auth
from apps.core.dashboard import DashboardView
from apps.core.feeds import AuditViewSet, MediaView, NotificationViewSet
from apps.core.staff import StaffViewSet

router = SimpleRouter()
router.register('staff',StaffViewSet,basename='staff')
router.register('notifications',NotificationViewSet,basename='notifications')
router.register('audit',AuditViewSet,basename='audit')
api = [path('auth/me/',auth.MeView.as_view()),path('auth/login/',auth.LoginView.as_view()),
       path('auth/logout/',auth.LogoutView.as_view()),path('auth/reset/',auth.ResetView.as_view()),
       path('auth/recovery-email/',auth.VerifyAddressView.as_view()),path('auth/recovery-email/confirm/',auth.ConfirmAddressView.as_view()),
       path('auth/reset/confirm/',auth.ConfirmResetView.as_view()),path('media/<path:key>',MediaView.as_view()),
       path('dashboard/',DashboardView.as_view()),path('schema/',SpectacularAPIView.as_view(),name='schema'),path('',include(router.urls))]
for domain in ('lodging','housekeeping','restaurant','billing','parking'):
    api.append(path('',include(f'apps.{domain}.urls')))
urlpatterns = [path('api/v1/',include(api))]
