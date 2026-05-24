"""OpenAPI / Swagger extensions for drf-spectacular."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SimpleJWTScheme(OpenApiAuthenticationExtension):
    target_class = "rest_framework_simplejwt.authentication.JWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT access-токен из `/api/auth/verify-code/` или `/api/auth/refresh/`",
        }
