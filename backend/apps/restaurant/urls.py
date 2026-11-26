from rest_framework.routers import SimpleRouter

from .views import MenuItemViewSet, OrderViewSet


router = SimpleRouter()
router.register("menu-items", MenuItemViewSet, basename="menu-item")
router.register("orders", OrderViewSet, basename="order")

urlpatterns = router.urls
