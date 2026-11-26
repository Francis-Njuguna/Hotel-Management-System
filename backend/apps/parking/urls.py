from rest_framework.routers import SimpleRouter

from .views import AllocationViewSet, ParkingSpaceViewSet, VehicleViewSet


router = SimpleRouter()
router.register("parking-spaces", ParkingSpaceViewSet, basename="parking-space")
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("parking-allocations", AllocationViewSet, basename="parking-allocation")
urlpatterns = router.urls
