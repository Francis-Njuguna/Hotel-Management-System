from rest_framework.routers import SimpleRouter

from .views import CleaningTaskViewSet, MaintenanceRequestViewSet


router = SimpleRouter()
router.register("cleaning-tasks", CleaningTaskViewSet, basename="cleaning-task")
router.register("maintenance", MaintenanceRequestViewSet, basename="maintenance")
urlpatterns = router.urls
