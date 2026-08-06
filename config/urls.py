from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from cargo.views import (
    AdminCargoViewSet,
    AdminOverviewAPIView,
    CargoCompanyViewSet,
    CargoDashboardAPIView,
    MyCargoAPIView,
)
from common import invites
from common.views import DeliveryAddressAPIView
from city_delivery.views import (
    CityDeliveryRequestViewSet,
    CityDeliveryTariffViewSet,
    ManagedCityDeliveryRequestViewSet,
    ManagedCityDeliveryTariffViewSet,
)
from integrations.pinduoduo.views import PinduoduoIntegrationViewSet
from notifications.views import (
    DeviceTokenViewSet,
    NotificationPreferenceAPIView,
    NotificationViewSet,
)
from orders.views import OrderViewSet
from parcels.views import OperationHistoryViewSet, ParcelViewSet
from pickup_points.views import ManagedPickupPointViewSet, PickupPointViewSet
from shops.views import ShopViewSet
from users.views import (
    AuthViewSet,
    ClientSearchAPIView,
    ManagedClientViewSet,
    ManagedStaffViewSet,
    ProfileAPIView,
    ProfilePasswordAPIView,
    ProfileQRAPIView,
)

router = DefaultRouter()
router.register("cargo-companies", CargoCompanyViewSet, basename="cargo-companies")
router.register("admin/cargos", AdminCargoViewSet, basename="admin-cargos")
router.register("auth", AuthViewSet, basename="auth")
router.register("pickup-points", PickupPointViewSet, basename="pickup-points")
router.register("shops", ShopViewSet, basename="shops")
router.register("orders", OrderViewSet, basename="orders")
router.register("parcels", ParcelViewSet, basename="parcels")
router.register("history", OperationHistoryViewSet, basename="history")
router.register("city-delivery", CityDeliveryRequestViewSet, basename="city-delivery")
router.register("city-delivery-tariffs", CityDeliveryTariffViewSet, basename="city-delivery-tariffs")
router.register("notifications", NotificationViewSet, basename="notifications")
router.register("device-tokens", DeviceTokenViewSet, basename="device-tokens")
router.register("integrations/pinduoduo", PinduoduoIntegrationViewSet, basename="pinduoduo")
router.register("manage/staff", ManagedStaffViewSet, basename="manage-staff")
router.register("manage/clients", ManagedClientViewSet, basename="manage-clients")
router.register(
    "manage/city-delivery", ManagedCityDeliveryRequestViewSet, basename="manage-city-delivery"
)
router.register(
    "manage/pickup-points", ManagedPickupPointViewSet, basename="manage-pickup-points"
)
router.register(
    "manage/city-delivery-tariffs",
    ManagedCityDeliveryTariffViewSet,
    basename="manage-city-delivery-tariffs",
)

_delete_account_view = TemplateView.as_view(
    template_name="legal/delete_account.html"
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # Верификация домена для App Links / Universal Links. Пути фиксированы
    # операционными системами: ровно 200, application/json, без редиректов.
    path(".well-known/assetlinks.json", invites.assetlinks, name="assetlinks"),
    path(
        ".well-known/apple-app-site-association",
        invites.apple_app_site_association,
        name="apple-app-site-association",
    ),
    # Ссылка-приглашение карго. Канонический вид — без слеша (он в QR и на
    # визитках); вариант со слешем принимаем, чтобы не ловить 404 из-за опечатки.
    path("j/<slug:slug>", invites.cargo_invite, name="cargo-invite"),
    path("j/<slug:slug>/", invites.cargo_invite),
    # Публичная страница удаления аккаунта (требование Google Play).
    path("delete-account", _delete_account_view, name="delete-account"),
    path("delete-account/", _delete_account_view),
    path("account-deletion", _delete_account_view, name="account-deletion"),
    path("account-deletion/", _delete_account_view),
    path("api/profile/", ProfileAPIView.as_view(), name="profile"),
    path("api/profile/password/", ProfilePasswordAPIView.as_view(), name="profile-password"),
    path("api/profile/qr/", ProfileQRAPIView.as_view(), name="profile-qr"),
    path(
        "api/profile/notification-preferences/",
        NotificationPreferenceAPIView.as_view(),
        name="notification-preferences",
    ),
    path("api/manage/cargo/", MyCargoAPIView.as_view(), name="manage-cargo"),
    path(
        "api/manage/dashboard/",
        CargoDashboardAPIView.as_view(),
        name="manage-dashboard",
    ),
    path("api/admin/overview/", AdminOverviewAPIView.as_view(), name="admin-overview"),
    path("api/delivery-address/", DeliveryAddressAPIView.as_view(), name="delivery-address"),
    path("api/clients/search/", ClientSearchAPIView.as_view(), name="clients-search"),
    # DELETE на коллекции роутер не умеет, а мобилка отвязывает токен при
    # выходе именно так. Маршрут объявлен до router.urls и повторяет его
    # list/create, чтобы GET и POST остались прежними.
    path(
        "api/device-tokens/",
        DeviceTokenViewSet.as_view(
            {"get": "list", "post": "create", "delete": "unregister"}
        ),
        name="device-tokens-list",
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
