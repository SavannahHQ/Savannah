import pytest

from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_login_form_signs_owner_in(client, acme):
    """Submitting the login form with the right password opens the owner's dashboard."""
    response = client.post(
        reverse("login"),
        {"action": "login", "username": acme.owner.username, "password": acme.password},
        follow=True,
    )

    assert response.wsgi_request.user == acme.owner
    assert response.redirect_chain[-1][0] == reverse(
        "dashboard", kwargs={"community_id": acme.community.pk}
    )
    assert response.status_code == 200


def test_login_form_rejects_wrong_password(client, acme):
    """A wrong password shows the form again and leaves the visitor signed out."""
    response = client.post(
        reverse("login"),
        {
            "action": "login",
            "username": acme.owner.username,
            "password": "not-the-password",
        },
    )

    assert response.status_code == 200
    assert not response.wsgi_request.user.is_authenticated
    assert response.context["login_form"].errors


def test_login_form_rejects_unknown_user(client, acme):
    """An unknown username leaves the visitor signed out."""
    response = client.post(
        reverse("login"),
        {"action": "login", "username": "nobody", "password": acme.password},
    )

    assert not response.wsgi_request.user.is_authenticated
