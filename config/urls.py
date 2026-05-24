from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from cargo.views import CargoCompanyViewSet
from city_delivery.views import CityDeliveryRequestViewSet, CityDeliveryTariffViewSet
from integrations.pinduoduo.views import PinduoduoIntegrationViewSet
from notifications.views import (
    DeviceTokenViewSet,
    NotificationPreferenceAPIView,
    NotificationViewSet,
)
from orders.views import OrderViewSet
from parcels.views import ParcelViewSet
from pickup_points.views import PickupPointViewSet
from shops.views import ShopViewSet
from users.views import AuthViewSet, ProfileAPIView, ProfileQRAPIView

router = DefaultRouter()
router.register("cargo-companies", CargoCompanyViewSet, basename="cargo-companies")
router.register("auth", AuthViewSet, basename="auth")
router.register("pickup-points", PickupPointViewSet, basename="pickup-points")
router.register("shops", ShopViewSet, basename="shops")
router.register("orders", OrderViewSet, basename="orders")
router.register("parcels", ParcelViewSet, basename="parcels")
router.register("city-delivery", CityDeliveryRequestViewSet, basename="city-delivery")
router.register("city-delivery-tariffs", CityDeliveryTariffViewSet, basename="city-delivery-tariffs")
router.register("notifications", NotificationViewSet, basename="notifications")
router.register("device-tokens", DeviceTokenViewSet, basename="device-tokens")
router.register("integrations/pinduoduo", PinduoduoIntegrationViewSet, basename="pinduoduo")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/profile/", ProfileAPIView.as_view(), name="profile"),
    path("api/profile/qr/", ProfileQRAPIView.as_view(), name="profile-qr"),
    path(
        "api/profile/notification-preferences/",
        NotificationPreferenceAPIView.as_view(),
        name="notification-preferences",
    ),
    path("api/", include(router.urls)),
]

if settings.ENABLE_API_DOCS:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "swagger/",
            RedirectView.as_view(url="/api/docs/", permanent=False),
            name="swagger-redirect",
        ),
        path(
            "api/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
        path(
            "redoc/",
            RedirectView.as_view(url="/api/redoc/", permanent=False),
            name="redoc-redirect",
        ),
    ]
    if settings.DEBUG:
        urlpatterns.insert(
            0,
            path(
                "",
                RedirectView.as_view(url="/api/docs/", permanent=False),
                name="home",
            ),
        )

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
