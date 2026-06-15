import factory
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory

from cargo.models import CargoCompany
from city_delivery.models import CityDeliveryRequest, CityDeliveryTariff
from notifications.models import DeviceToken, Notification, NotificationPreference
from orders.models import Order
from parcels.models import Parcel
from pickup_points.models import PickupPoint
from shops.models import Shop

User = get_user_model()


class CargoCompanyFactory(DjangoModelFactory):
    class Meta:
        model = CargoCompany

    title = factory.Sequence(lambda n: f"Карго #{n}")
    slug = factory.Sequence(lambda n: f"cargo-{n}")
    is_active = True


class PickupPointFactory(DjangoModelFactory):
    class Meta:
        model = PickupPoint

    cargo = factory.SubFactory(CargoCompanyFactory)
    title = factory.Sequence(lambda n: f"ПВЗ #{n}")
    address = factory.Faker("address", locale="ru_RU")
    phone = "+996700000000"
    is_active = True


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    cargo = factory.SubFactory(CargoCompanyFactory)
    phone = factory.Sequence(lambda n: f"+99670000{n:04d}")
    full_name = factory.Faker("name", locale="ru_RU")
    pickup_point = factory.SubFactory(
        PickupPointFactory,
        cargo=factory.SelfAttribute("..cargo"),
    )

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", None)
        is_staff = kwargs.pop("is_staff", False)
        is_superuser = kwargs.pop("is_superuser", False)
        user = model_class.objects.create_user(password=password, **kwargs)
        if is_staff or is_superuser:
            user.is_staff = is_staff or is_superuser
            user.is_superuser = is_superuser
            user.save(update_fields=("is_staff", "is_superuser"))
        return user


class ShopFactory(DjangoModelFactory):
    class Meta:
        model = Shop

    cargo = factory.SubFactory(CargoCompanyFactory)
    title = factory.Sequence(lambda n: f"Shop {n}")
    slug = factory.Sequence(lambda n: f"shop-{n}")
    url = "https://example.com/"
    open_type = Shop.OpenType.WEBVIEW
    client_code_strategy = Shop.ClientCodeStrategy.QUERY_PARAM
    query_param_name = "client_code"
    is_active = True


class OrderFactory(DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    source = Order.Source.MANUAL
    product_title = factory.Faker("sentence", nb_words=4, locale="ru_RU")
    price = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    quantity = 1
    status = Order.Status.CREATED


class ParcelFactory(DjangoModelFactory):
    class Meta:
        model = Parcel

    user = factory.SubFactory(UserFactory)
    cargo = factory.LazyAttribute(lambda o: o.user.cargo)
    track_number = factory.Sequence(lambda n: f"TRACK{n:08d}")
    client_code = factory.LazyAttribute(lambda o: o.user.client_code or "C0000000")
    status = Parcel.Status.CREATED
    weight = 1.5


class CityDeliveryTariffFactory(DjangoModelFactory):
    class Meta:
        model = CityDeliveryTariff

    title = factory.Sequence(lambda n: f"Тариф {n}")
    base_price = "100.00"
    price_per_kg = "20.00"
    free_weight_kg = "1.0"
    is_active = True
    is_default = True


class CityDeliveryRequestFactory(DjangoModelFactory):
    class Meta:
        model = CityDeliveryRequest

    user = factory.SubFactory(UserFactory)
    parcel = factory.SubFactory(ParcelFactory)
    address = "Бишкек, ул. Тестовая, 1"
    recipient_name = "Иван Иванов"
    recipient_phone = "+996700111222"


class NotificationFactory(DjangoModelFactory):
    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    title = "Test"
    body = "Test body"
    type = "system"


class DeviceTokenFactory(DjangoModelFactory):
    class Meta:
        model = DeviceToken

    user = factory.SubFactory(UserFactory)
    token = factory.Sequence(lambda n: f"token-{n}")
    platform = DeviceToken.Platform.ANDROID


class NotificationPreferenceFactory(DjangoModelFactory):
    class Meta:
        model = NotificationPreference

    user = factory.SubFactory(UserFactory)
