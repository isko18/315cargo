import pytest
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory
from users.models import SMSCode

User = get_user_model()


@pytest.mark.django_db
def test_send_code_creates_sms(api_client, cargo):
    response = api_client.post(
        "/api/auth/send-code/",
        {"phone": "+996700111111", "cargo_id": cargo.id, "purpose": "register"},
        format="json",
    )
    assert response.status_code == 200
    assert SMSCode.objects.filter(phone="+996700111111").exists()


@pytest.mark.django_db
def test_send_code_throttled(api_client, cargo):
    payload = {"phone": "+996700222222", "cargo_id": cargo.id, "purpose": "register"}
    api_client.post("/api/auth/send-code/", payload, format="json")
    response = api_client.post("/api/auth/send-code/", payload, format="json")
    assert response.status_code == 429


@pytest.mark.django_db
def test_register_and_login_with_pickup_point(api_client, pickup_point):
    phone = "+996700333333"
    api_client.post(
        "/api/auth/send-code/",
        {
            "phone": phone,
            "cargo_id": pickup_point.cargo_id,
            "purpose": "register",
        },
        format="json",
    )
    sms = SMSCode.objects.get(phone=phone)

    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": sms.code,
            "cargo_id": pickup_point.cargo_id,
            "pickup_point_id": pickup_point.id,
            "full_name": "Тест Тестов",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    body = response.data
    assert body["is_new_user"] is True
    assert body["user"]["client_code"]
    assert body["user"]["pickup_point"] == pickup_point.id
    assert body["user"]["cargo"] == pickup_point.cargo_id
    assert body["access"]
    assert body["refresh"]


@pytest.mark.django_db
def test_same_phone_single_global_client(api_client):
    cargo_a = CargoCompanyFactory(slug="cargo-a")
    cargo_b = CargoCompanyFactory(slug="cargo-b")
    pp_a = PickupPointFactory(cargo=cargo_a)
    pp_b = PickupPointFactory(cargo=cargo_b)
    phone = "+996700444444"

    api_client.post(
        "/api/auth/send-code/",
        {"phone": phone, "cargo_id": cargo_a.id, "purpose": "register"},
        format="json",
    )
    sms = SMSCode.objects.filter(phone=phone, is_used=False).latest("created_at")
    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": sms.code,
            "cargo_id": cargo_a.id,
            "pickup_point_id": pp_a.id,
            "full_name": "Клиент A",
        },
        format="json",
    )
    assert response.status_code == 200, response.data

    SMSCode.objects.filter(phone=phone).update(
        created_at=timezone.now() - timedelta(seconds=61)
    )
    api_client.post(
        "/api/auth/send-code/",
        {"phone": phone, "cargo_id": cargo_b.id, "purpose": "register"},
        format="json",
    )
    sms = SMSCode.objects.filter(phone=phone, is_used=False).latest("created_at")
    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": sms.code,
            "cargo_id": cargo_b.id,
            "pickup_point_id": pp_b.id,
            "full_name": "Клиент B",
        },
        format="json",
    )
    assert response.status_code == 200, response.data

    # Глобальная уникальность: тот же номер второй раз → вход в существующий
    # аккаунт (не дубль). Аккаунт остаётся в исходном карго A.
    assert response.data["is_new_user"] is False
    assert User.objects.filter(phone=phone, is_staff=False, is_superuser=False).count() == 1
    assert User.objects.get(phone=phone, is_staff=False, is_superuser=False).cargo_id == cargo_a.id


@pytest.mark.django_db
def test_code_bound_to_cargo_cannot_verify_other_cargo(api_client):
    """An OTP issued for cargo A must not authenticate the phone under cargo B."""
    cargo_a = CargoCompanyFactory(slug="bind-a")
    cargo_b = CargoCompanyFactory(slug="bind-b")
    pp_b = PickupPointFactory(cargo=cargo_b)
    phone = "+996700555555"

    api_client.post(
        "/api/auth/send-code/",
        {"phone": phone, "cargo_id": cargo_a.id, "purpose": "register"},
        format="json",
    )
    sms = SMSCode.objects.get(phone=phone)

    # Same phone + same code, but a different cargo must be rejected.
    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": sms.code,
            "cargo_id": cargo_b.id,
            "pickup_point_id": pp_b.id,
            "full_name": "Чужой",
        },
        format="json",
    )
    assert response.status_code == 400
    assert User.objects.filter(phone=phone).count() == 0


@pytest.mark.django_db
def test_otp_brute_force_locked_after_max_attempts(api_client, pickup_point):
    from users.constants import MAX_OTP_ATTEMPTS

    phone = "+996700666666"
    api_client.post(
        "/api/auth/send-code/",
        {"phone": phone, "cargo_id": pickup_point.cargo_id, "purpose": "register"},
        format="json",
    )
    sms = SMSCode.objects.get(phone=phone)
    wrong_code = "0000" if sms.code != "0000" else "1111"

    for _ in range(MAX_OTP_ATTEMPTS):
        wrong = api_client.post(
            "/api/auth/verify-code/",
            {"phone": phone, "code": wrong_code, "cargo_id": pickup_point.cargo_id},
            format="json",
        )
        assert wrong.status_code == 400

    # Code is burned: even the correct code no longer works.
    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": sms.code,
            "cargo_id": pickup_point.cargo_id,
            "pickup_point_id": pickup_point.id,
            "full_name": "X",
        },
        format="json",
    )
    assert response.status_code == 400
    assert User.objects.filter(phone=phone).count() == 0


@pytest.mark.django_db
def test_reviewer_test_number_login(api_client, cargo, settings):
    settings.OTP_TEST_NUMBERS = {"+996700123456": "9999"}
    u = User(phone="+996700123456", cargo=cargo, full_name="Ревьюер")
    u.set_unusable_password()
    u.save()

    send = api_client.post(
        "/api/auth/send-code/",
        {"phone": "+996700123456", "cargo_id": cargo.id, "purpose": "login"},
        format="json",
    )
    assert send.status_code == 200  # 200 без реальной SMS

    ver = api_client.post(
        "/api/auth/verify-code/",
        {"phone": "+996700123456", "code": "9999", "cargo_id": cargo.id},
        format="json",
    )
    assert ver.status_code == 200, ver.data
    assert ver.data["is_new_user"] is False
    assert ver.data["access"]

    bad = api_client.post(
        "/api/auth/verify-code/",
        {"phone": "+996700123456", "code": "0000", "cargo_id": cargo.id},
        format="json",
    )
    assert bad.status_code == 400  # неверный фиксированный код


@pytest.mark.django_db
def test_account_deletion(api_client, user, settings):
    from rest_framework_simplejwt.tokens import RefreshToken

    settings.OTP_TEST_NUMBERS = {}  # чтобы фикстура не совпала с тест-номером
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    r = api_client.delete("/api/profile/")
    assert r.status_code == 204

    user.refresh_from_db()
    assert user.is_active is False
    assert user.full_name == ""
    assert user.phone == f"deleted-{user.id}"

    # Токен больше не работает (пользователь деактивирован).
    me = api_client.get("/api/profile/")
    assert me.status_code == 401


@pytest.mark.django_db
def test_existing_user_login(api_client, user):
    api_client.post(
        "/api/auth/send-code/",
        {"phone": user.phone, "cargo_id": user.cargo_id, "purpose": "login"},
        format="json",
    )
    sms = SMSCode.objects.get(phone=user.phone)
    response = api_client.post(
        "/api/auth/verify-code/",
        {"phone": user.phone, "code": sms.code, "cargo_id": user.cargo_id},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["is_new_user"] is False
    assert response.data["user"]["id"] == user.id


@pytest.mark.django_db
def test_password_login_for_staff(api_client, cargo):
    staff = UserFactory(
        cargo=cargo, phone="+996700999999", password="secret123", is_staff=True
    )
    r = api_client.post(
        "/api/auth/token/",
        {"login": staff.phone, "password": "secret123"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["access"]
    assert r.data["user"]["id"] == staff.id

    # неверный пароль
    bad = api_client.post(
        "/api/auth/token/",
        {"login": staff.phone, "password": "nope"},
        format="json",
    )
    assert bad.status_code == 400

    # обычный клиент (не staff) не может войти по паролю
    UserFactory(cargo=cargo, phone="+996700888888", password="pw12345", is_staff=False)
    client_login = api_client.post(
        "/api/auth/token/",
        {"login": "+996700888888", "password": "pw12345"},
        format="json",
    )
    assert client_login.status_code == 400


@pytest.mark.django_db
def test_cargo_admin_creates_staff(api_client, cargo):
    admin = UserFactory(
        cargo=cargo, phone="+996700111000", password="adminpw1", is_cargo_admin=True
    )
    tok = api_client.post(
        "/api/auth/token/", {"login": admin.phone, "password": "adminpw1"}, format="json"
    ).data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")

    r = api_client.post(
        "/api/manage/staff/",
        {"phone": "+996700222000", "full_name": "Оператор", "password": "operpw1"},
        format="json",
    )
    assert r.status_code == 201, r.data

    op = User.objects.get(phone="+996700222000")
    assert op.is_staff and op.cargo_id == cargo.id and op.check_password("operpw1")

    # созданный оператор входит по паролю
    login = api_client.post(
        "/api/auth/token/",
        {"login": "+996700222000", "password": "operpw1"},
        format="json",
    )
    assert login.status_code == 200

    # оператор виден в списке своего карго
    lst = api_client.get("/api/manage/staff/")
    assert lst.status_code == 200
    items = lst.data["results"] if isinstance(lst.data, dict) else lst.data
    assert "+996700222000" in [u["phone"] for u in items]


@pytest.mark.django_db
def test_cargo_admin_assigns_pickup_point_to_staff(api_client, cargo):
    from pickup_points.models import PickupPoint
    from tests.factories import CargoCompanyFactory, PickupPointFactory

    admin = UserFactory(
        cargo=cargo, phone="+996700111001", password="adminpw1", is_cargo_admin=True
    )
    tok = api_client.post(
        "/api/auth/token/", {"login": admin.phone, "password": "adminpw1"}, format="json"
    ).data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")

    pp = PickupPointFactory(cargo=cargo, title="ПВЗ Центр")

    # Назначение своего ПВЗ — успех.
    r = api_client.post(
        "/api/manage/staff/",
        {
            "phone": "+996700222001",
            "full_name": "Оператор ПВЗ",
            "password": "operpw1",
            "pickup_point": pp.id,
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["pickup_point"] == pp.id
    assert r.data["pickup_point_title"] == "ПВЗ Центр"
    assert User.objects.get(phone="+996700222001").pickup_point_id == pp.id

    # ПВЗ чужого карго — отклонить.
    other_pp = PickupPointFactory(cargo=CargoCompanyFactory())
    bad = api_client.post(
        "/api/manage/staff/",
        {
            "phone": "+996700222002",
            "full_name": "Плохой",
            "password": "operpw1",
            "pickup_point": other_pp.id,
        },
        format="json",
    )
    assert bad.status_code == 400
    assert "pickup_point" in bad.data


@pytest.mark.django_db
def test_operator_tab_access_enforced(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    # Оператор с доступом только к «warehouse» — без staff/tariff/analytics.
    op = UserFactory(cargo=cargo, is_staff=True, allowed_tabs=["warehouse"])
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(op).access_token}"
    )

    # Роль-payload отдаёт эффективные вкладки.
    me = api_client.get("/api/profile/")
    assert me.data["allowed_tabs"] == ["warehouse"]

    # Управляющие вкладки запрещены (403).
    assert api_client.get("/api/manage/staff/").status_code == 403
    assert api_client.get("/api/manage/pickup-points/").status_code == 403
    assert api_client.get("/api/manage/cargo/").status_code == 403
    assert api_client.get("/api/manage/dashboard/").status_code == 403

    # Разрешённый раздел (склад — чтение посылок) доступен.
    assert api_client.get("/api/parcels/").status_code == 200


@pytest.mark.django_db
def test_cargo_admin_creates_operator_with_tabs(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    admin = UserFactory(cargo=cargo, phone="+996700111010", password="adminpw1", is_cargo_admin=True)
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(admin).access_token}"
    )

    r = api_client.post(
        "/api/manage/staff/",
        {
            "phone": "+996700222010",
            "full_name": "Оператор Тариф",
            "password": "operpw1",
            "allowed_tabs": ["scan", "tariff", "overview"],  # overview невыдаваем — отфильтруется
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["allowed_tabs"] == ["scan", "tariff"]

    op = User.objects.get(phone="+996700222010")
    op_tok = RefreshToken.for_user(op).access_token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {op_tok}")
    # tariff выдан → доступ есть; staff не выдан → 403.
    assert api_client.get("/api/manage/cargo/").status_code == 200
    assert api_client.get("/api/manage/staff/").status_code == 403


@pytest.mark.django_db
def test_cargo_admin_cannot_create_china_operator(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    admin = UserFactory(cargo=cargo, phone="+996700111030", password="adminpw1", is_cargo_admin=True)
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(admin).access_token}"
    )
    r = api_client.post(
        "/api/manage/staff/",
        {
            "phone": "+996700222030",
            "full_name": "China",
            "password": "operpw1",
            "is_china_staff": True,
        },
        format="json",
    )
    assert r.status_code == 400
    assert "is_china_staff" in r.data


@pytest.mark.django_db
def test_cargo_admin_does_not_see_china_operators(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    admin = UserFactory(cargo=cargo, phone="+996700111031", password="adminpw1", is_cargo_admin=True)
    china = UserFactory(cargo=cargo, is_staff=True, is_china_staff=True)
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(admin).access_token}"
    )
    lst = api_client.get("/api/manage/staff/")
    items = lst.data["results"] if isinstance(lst.data, dict) else lst.data
    assert china.id not in [u["id"] for u in items]
    # У админа карго нет вкладки склада Китая.
    me = api_client.get("/api/profile/")
    assert "china" not in me.data["allowed_tabs"]


@pytest.mark.django_db
def test_cargo_admin_edits_operator_tabs(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    admin = UserFactory(cargo=cargo, phone="+996700111020", password="adminpw1", is_cargo_admin=True)
    operator = UserFactory(cargo=cargo, is_staff=True, allowed_tabs=["scan"])
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(admin).access_token}"
    )

    # Выдаём оператору доступ к тарифу и аналитике (без смены пароля).
    r = api_client.patch(
        f"/api/manage/staff/{operator.id}/",
        {"allowed_tabs": ["scan", "tariff", "analytics"]},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["allowed_tabs"] == ["scan", "tariff", "analytics"]

    operator.refresh_from_db()
    assert operator.allowed_tabs == ["scan", "tariff", "analytics"]

    # Пароль не тронут — старый вход работает.
    op_tok = RefreshToken.for_user(operator).access_token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {op_tok}")
    assert api_client.get("/api/manage/cargo/").status_code == 200  # tariff выдан
    assert api_client.get("/api/manage/staff/").status_code == 403  # staff не выдан


@pytest.mark.django_db
def test_profile_password_change(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    op = UserFactory(cargo=cargo, phone="+996700111099", password="oldpw12", is_staff=True)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(op).access_token}")

    # Неверный текущий пароль — 400.
    bad = api_client.post(
        "/api/profile/password/",
        {"current_password": "wrong", "new_password": "newpw123"},
        format="json",
    )
    assert bad.status_code == 400

    ok = api_client.post(
        "/api/profile/password/",
        {"current_password": "oldpw12", "new_password": "newpw123"},
        format="json",
    )
    assert ok.status_code == 200

    # Старый пароль больше не работает, новый — работает.
    assert api_client.post(
        "/api/auth/token/", {"login": op.phone, "password": "oldpw12"}, format="json"
    ).status_code == 400
    assert api_client.post(
        "/api/auth/token/", {"login": op.phone, "password": "newpw123"}, format="json"
    ).status_code == 200


@pytest.mark.django_db
def test_refresh_token(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    response = api_client.post(
        "/api/auth/refresh/", {"refresh": str(refresh)}, format="json"
    )
    assert response.status_code == 200
    assert "access" in response.data


@pytest.mark.django_db
def test_refresh_rotates_and_blacklists_old_token(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    old_refresh = str(refresh)

    response = api_client.post(
        "/api/auth/refresh/", {"refresh": old_refresh}, format="json"
    )
    assert response.status_code == 200
    new_refresh = response.data["refresh"]
    assert new_refresh != old_refresh  # rotation happened

    # The old refresh token must be blacklisted after rotation.
    reuse = api_client.post(
        "/api/auth/refresh/", {"refresh": old_refresh}, format="json"
    )
    assert reuse.status_code == 401


@pytest.mark.django_db
def test_logout_blacklists_refresh(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    response = api_client.post(
        "/api/auth/logout/", {"refresh": str(refresh)}, format="json"
    )
    assert response.status_code == 204

    response = api_client.post(
        "/api/auth/refresh/", {"refresh": str(refresh)}, format="json"
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_cargo_companies_list(api_client, cargo):
    response = api_client.get("/api/cargo-companies/")
    assert response.status_code == 200
    assert any(item["id"] == cargo.id for item in response.data)


@pytest.mark.django_db
def test_pickup_points_public_list(api_client, pickup_point):
    response = api_client.get(f"/api/pickup-points/?cargo={pickup_point.cargo_id}")
    assert response.status_code == 200
    assert any(item["id"] == pickup_point.id for item in response.data)


@pytest.mark.django_db
@override_settings(OTP_MASTER_CODE="9999")
def test_master_code_registers_without_sms(api_client, cargo, pickup_point):
    """Мастер-код проходит верификацию без реальной SMS (устойчивость к сбою)."""
    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": "+996700987654",
            "code": "9999",
            "cargo_id": cargo.id,
            "pickup_point_id": pickup_point.id,
            "full_name": "Через мастер-код",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["is_new_user"] is True
    assert get_user_model().objects.filter(phone="+996700987654").exists()


@pytest.mark.django_db
def test_phone_format_normalized_no_duplicate(api_client, cargo, pickup_point):
    """«+996…» и «996…» — один номер: второй раз это вход, не дубль."""
    def reg(phone, full_name):
        SMSCode.objects.all().update(created_at=timezone.now() - timedelta(seconds=61))
        api_client.post(
            "/api/auth/send-code/",
            {"phone": phone, "cargo_id": cargo.id, "purpose": "register"},
            format="json",
        )
        sms = SMSCode.objects.filter(is_used=False).latest("created_at")
        return api_client.post(
            "/api/auth/verify-code/",
            {
                "phone": phone,
                "code": sms.code,
                "cargo_id": cargo.id,
                "pickup_point_id": pickup_point.id,
                "full_name": full_name,
            },
            format="json",
        )

    r1 = reg("+996700112233", "Формат плюс")
    assert r1.status_code == 200, r1.data
    r2 = reg("996700112233", "Формат без плюса")
    assert r2.status_code == 200, r2.data
    assert r2.data["is_new_user"] is False
    assert get_user_model().objects.filter(phone="+996700112233").count() == 1
