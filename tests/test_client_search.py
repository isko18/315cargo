import pytest


@pytest.mark.django_db
def test_client_search_by_name_phone_code(cargo_admin_client):
    from tests.factories import UserFactory

    cargo = cargo_admin_client.user.cargo
    c1 = UserFactory(cargo=cargo, full_name="Иван Петров", phone="+996700111222")
    UserFactory(cargo=cargo, full_name="Другой Клиент", phone="+996700999888")

    # по имени
    r = cargo_admin_client.get("/api/clients/search/?q=Иван")
    assert r.status_code == 200
    codes = {row["client_code"] for row in r.data}
    assert c1.client_code in codes
    # по телефону
    r = cargo_admin_client.get("/api/clients/search/?q=111222")
    assert {row["client_code"] for row in r.data} == {c1.client_code}
    # по коду
    r = cargo_admin_client.get(f"/api/clients/search/?q={c1.client_code}")
    assert {row["client_code"] for row in r.data} == {c1.client_code}
    # пустой запрос -> пусто
    assert cargo_admin_client.get("/api/clients/search/?q=").data == []


@pytest.mark.django_db
def test_client_search_available_to_operator_and_pickup_scoped(api_client):
    from rest_framework_simplejwt.tokens import RefreshToken
    from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory

    cargo = CargoCompanyFactory()
    pp1 = PickupPointFactory(cargo=cargo)
    pp2 = PickupPointFactory(cargo=cargo)
    mine = UserFactory(cargo=cargo, pickup_point=pp1, full_name="Мой Клиент")
    UserFactory(cargo=cargo, pickup_point=pp2, full_name="Чужой Клиент")

    # Оператор без вкладки 'clients', привязан к pp1.
    op = UserFactory(cargo=cargo, is_staff=True, pickup_point=pp1, allowed_tabs=["scan"])
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(op).access_token}")

    r = api_client.get("/api/clients/search/?q=Клиент")
    assert r.status_code == 200
    codes = {row["client_code"] for row in r.data}
    assert mine.client_code in codes  # свой ПВЗ виден
    assert len(codes) == 1  # чужой ПВЗ не виден
