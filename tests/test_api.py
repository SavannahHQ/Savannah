import pytest

pytestmark = pytest.mark.django_db

# List endpoints, with the text that marks a seeded record of each kind.
LISTS = [
    ("/api/v1/identity/", "ada-of-{tenant}"),
    ("/api/v1/conversation/", "How do I get started with {tenant}?"),
    ("/api/v1/contribution/", "Fix the {tenant} installer"),
    ("/api/v1/event/", "{tenant} meetup"),
]


@pytest.mark.parametrize("path", ["/api/v1/"] + [path for path, _ in LISTS])
def test_request_without_token_is_rejected(client, acme, path):
    """The API answers 401 when no source token is sent."""
    response = client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/api/v1/"] + [path for path, _ in LISTS])
def test_request_with_unknown_token_is_rejected(client, acme, path):
    """The API answers 401 for a token that belongs to no source."""
    response = client.get(path, HTTP_AUTHORIZATION="Token not-a-source-token")

    assert response.status_code == 401


def test_token_of_disabled_source_is_rejected(client, acme):
    """Disabling a source revokes its token."""
    acme.source.enabled = False
    acme.source.save(update_fields=("enabled",))

    response = client.get("/api/v1/", HTTP_AUTHORIZATION=f"Token {acme.source.api_key}")

    assert response.status_code == 401


def test_token_identifies_its_source(client, acme, globex):
    """A token describes the source it was issued for."""
    response = client.get("/api/v1/", HTTP_AUTHORIZATION=f"Token {acme.source.api_key}")

    assert response.status_code == 200
    assert response.json()["name"] == acme.source.name


@pytest.mark.parametrize("path,marker", LISTS)
def test_list_only_returns_records_of_the_token_source(
    client, acme, globex, path, marker
):
    """A source token lists that source's records and none of another tenant's."""
    response = client.get(path, HTTP_AUTHORIZATION=f"Token {acme.source.api_key}")

    assert response.status_code == 200
    assert marker.format(tenant="Acme").lower() in response.content.decode().lower()
    assert "globex" not in response.content.decode().lower()


def test_identity_of_another_source_is_not_found(client, acme, globex):
    """An identity is only addressable with the token of its own source."""
    path = f"/api/v1/identity/{globex.member.contact_set.get().origin_id}/"

    # Sanity check
    assert (
        client.get(
            path, HTTP_AUTHORIZATION=f"Token {globex.source.api_key}"
        ).status_code
        == 200
    )

    response = client.get(path, HTTP_AUTHORIZATION=f"Token {acme.source.api_key}")

    assert response.status_code == 404
