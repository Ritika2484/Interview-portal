from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_schema_is_valid_and_contains_foundation_and_account_endpoints():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    assert set(schema["paths"]) == {
        "/health/live/",
        "/health/ready/",
        "/api/v1/auth/csrf/",
        "/api/v1/auth/register/",
        "/api/v1/auth/login/",
        "/api/v1/auth/verify-email/",
        "/api/v1/auth/resend-verification/",
        "/api/v1/auth/password-reset/",
        "/api/v1/auth/password-reset/confirm/",
        "/api/v1/auth/logout/",
        "/api/v1/auth/logout-all/",
        "/api/v1/auth/reauthenticate/",
        "/api/v1/me/",
        "/api/v1/me/personal-data/",
        "/api/v1/privacy-requests/{id}/",
        "/api/v1/admin/account-stats/",
    }
    assert "503" in schema["paths"]["/health/ready/"]["get"]["responses"]
    assert "401" in schema["paths"]["/api/v1/auth/login/"]["post"]["responses"]
    assert (
        schema["components"]["schemas"]["ProfileOutput"]["properties"]["technical_skills"]["type"]
        == "array"
    )


def test_swagger_uses_local_sidecar_assets(client):
    response = client.get("/api/v1/docs/")
    assert response.status_code == 200
    assert b"drf_spectacular_sidecar" in response.content
    assert b"cdn.jsdelivr.net" not in response.content
