from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        from django.contrib import admin

        import users.signals  # noqa: F401

        from users.admin_auth import AdminPhoneAuthenticationForm

        admin.site.login_form = AdminPhoneAuthenticationForm
