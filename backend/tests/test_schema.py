from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema


def test_schema_is_valid_and_contains_only_foundation_endpoints():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    validate_schema(schema)
    assert set(schema["paths"]) == {"/health/live/", "/health/ready/"}
    assert "503" in schema["paths"]["/health/ready/"]["get"]["responses"]


def test_swagger_uses_local_sidecar_assets(client):
    response = client.get("/api/v1/docs/")
    assert response.status_code == 200
    assert b"drf_spectacular_sidecar" in response.content
    assert b"cdn.jsdelivr.net" not in response.content
