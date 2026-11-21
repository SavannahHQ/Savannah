import pytest

from django.urls import reverse

from frontendv2.urls import urlpatterns

# Every URL that is addressed by a community id alone.
COMMUNITY_URLS = sorted(
    pattern.name
    for pattern in urlpatterns
    if set(pattern.pattern.converters) == {"community_id"}
)
# Form targets: they only act on POST and have no page of their own.
ACTIONS = {
    "manager_gift_received",
    "manager_opportunity_update",
    "manager_task_done",
    "opportunity_update",
    "resend_invite",
    "revoke_invite",
    "toggle_insight_read_state",
}
# The landing page of a manager invitation, which the invited person opens before signing in.
INVITATION = {"manager_accept"}
COMMUNITY_PAGES = [name for name in COMMUNITY_URLS if name not in ACTIONS | INVITATION]
CSV_EXPORTS = ["members_csv", "contributors_csv", "companies_csv", "events_csv"]

# Pages of one object, as (URL name, {URL argument: seeded object}).
OBJECT_PAGES = [
    ("member_profile", {"member_id": "member"}),
    ("member_activity", {"member_id": "member"}),
    ("member_edit", {"member_id": "member"}),
    ("member_settings", {"member_id": "member"}),
    ("member_merge", {"member_id": "member"}),
    ("merge_history", {"member_id": "member"}),
    ("add_contribution", {"member_id": "member"}),
    ("gift_add", {"member_id": "member"}),
    ("task_add", {"member_id": "member"}),
    ("company_profile", {"company_id": "company"}),
    ("company_edit", {"company_id": "company"}),
    ("company_merge", {"company_id": "company"}),
    ("event", {"event_id": "event"}),
    ("event_edit", {"event_id": "event"}),
    ("attendee_add", {"event_id": "event"}),
    ("attendee_quickadd", {"event_id": "event"}),
    ("attendee_csv", {"event_id": "event"}),
    ("tag_edit", {"tag_id": "tag"}),
]
# Pages of an object that the URL places inside a community or member, which comes first.
NESTED_PAGES = [
    ("channels", {"community_id": "community", "source_id": "source"}),
    ("project_overview", {"community_id": "community", "project_id": "project"}),
    ("project_edit", {"community_id": "community", "project_id": "project"}),
    ("project_threshold_edit", {"community_id": "community", "project_id": "project"}),
    ("project_delete", {"community_id": "community", "project_id": "project"}),
    ("project_task_add", {"community_id": "community", "project_id": "project"}),
    (
        "project_task_edit",
        {"community_id": "community", "project_id": "project", "task_id": "task"},
    ),
    ("manager_task_edit", {"community_id": "community", "task_id": "task"}),
    ("report_view", {"community_id": "community", "report_id": "report"}),
    ("publish_report", {"community_id": "community", "report_id": "report"}),
    ("import_info", {"community_id": "community", "upload_id": "upload"}),
    ("import_map", {"community_id": "community", "upload_id": "upload"}),
    ("opportunity_edit", {"community_id": "community", "opp_id": "opportunity"}),
    ("gift_type_edit", {"community_id": "community", "type_id": "gift_type"}),
    ("webhook_edit", {"community_id": "community", "hook_id": "webhook"}),
    ("task_edit", {"member_id": "contributor", "task_id": "task"}),
    ("gift_edit", {"member_id": "contributor", "gift_id": "gift"}),
]

pytestmark = pytest.mark.django_db


def page_url(name, arguments, tenant):
    kwargs = {
        argument: getattr(tenant, seeded).pk for argument, seeded in arguments.items()
    }
    return reverse(name, kwargs=kwargs)


class TestOwner:
    @pytest.mark.parametrize("name", COMMUNITY_PAGES)
    def test_community_page_loads(self, owner_client, acme, name):
        """Every page of a community renders for its owner."""
        response = owner_client.get(
            reverse(name, kwargs={"community_id": acme.community.pk})
        )

        assert response.status_code == 200

    @pytest.mark.parametrize("name,arguments", OBJECT_PAGES + NESTED_PAGES)
    def test_object_page_loads(self, owner_client, acme, name, arguments):
        """The pages of everything inside a community render for its owner."""
        response = owner_client.get(page_url(name, arguments, acme))

        assert response.status_code == 200

    @pytest.mark.parametrize("name", CSV_EXPORTS)
    def test_csv_export_downloads(self, owner_client, acme, name):
        """Community exports are served as CSV attachments."""
        response = owner_client.get(
            reverse(name, kwargs={"community_id": acme.community.pk})
        )

        assert response["Content-Type"] == "text/csv"
        assert response["Content-Disposition"].startswith("attachment")

    def test_members_export_lists_members(self, owner_client, acme):
        """The members export has a row for each member of the community."""
        response = owner_client.get(
            reverse("members_csv", kwargs={"community_id": acme.community.pk})
        )

        assert "Ada of Acme" in response.content.decode()

    def test_attendee_export_lists_attendees(self, owner_client, acme):
        """The attendee export of an event has a row for each attendee."""
        response = owner_client.get(
            reverse("attendee_csv", kwargs={"event_id": acme.event.pk})
        )

        assert response["Content-Type"] == "text/csv"
        assert "Grace of Acme" in response.content.decode()
