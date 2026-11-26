from rest_framework.routers import SimpleRouter

from .views import GuestViewSet, ReservationViewSet, RoomViewSet


router = SimpleRouter()
router.register("guests", GuestViewSet, basename="guest")
router.register("rooms", RoomViewSet, basename="room")
router.register("reservations", ReservationViewSet, basename="reservation")
urlpatterns = router.urls
