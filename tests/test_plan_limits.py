import pytest

from django.core.management import call_command
from django.urls import reverse

from corm.models import Community, Project, Report, Source, Tag

pytestmark = pytest.mark.django_db


@pytest.fixture
def unmanaged(globex):
    """Globex has no billing Management record, so the built-in limits of "No Plan" apply."""
    return globex.community


def fill(community, *, tags=0, projects=0, sources=0):
    for number in range(tags):
        Tag.objects.create(community=community, name=f"tag-{number}", color="cccccc")
    for number in range(projects):
        Project.objects.create(community=community, name=f"segment-{number}")
    for number in range(sources):
        Source.objects.create(
            community=community, connector="corm.plugins.rss", name=f"feed-{number}"
        )


class TestCommunityWithoutPlan:
    def test_allows_three_tags(self, unmanaged):
        """The third tag can be added, a fourth cannot."""
        Tag.objects.filter(community=unmanaged).delete()

        fill(unmanaged, tags=2)
        assert unmanaged.management.can_add_tag()

        fill(unmanaged, tags=1)
        assert not unmanaged.management.can_add_tag()

    def test_allows_three_segments_besides_the_default(self, unmanaged):
        """The third segment can be added, a fourth cannot."""
        Project.objects.filter(community=unmanaged, default_project=False).delete()

        fill(unmanaged, projects=2)
        assert unmanaged.management.can_add_project()

        fill(unmanaged, projects=1)
        assert not unmanaged.management.can_add_project()

    def test_allows_three_enabled_sources(self, unmanaged):
        """The third source can be added, a fourth cannot."""
        fill(unmanaged, sources=1)
        assert unmanaged.management.can_add_source()

        fill(unmanaged, sources=1)
        assert not unmanaged.management.can_add_source()

    def test_allows_no_manager_besides_the_owner(self, unmanaged):
        """The owner fills the only manager seat."""
        assert not unmanaged.management.can_add_manager()

    def test_tag_form_refuses_a_tag_over_the_limit(self, globex_client, unmanaged):
        """Posting the tag form at the limit creates nothing and returns to the tag list."""
        tags_before = unmanaged.tag_set.count()

        response = globex_client.post(
            reverse("tag_add", kwargs={"community_id": unmanaged.pk}),
            {"name": "one-too-many", "color": "cccccc"},
        )

        assert response.status_code == 302
        assert response.url == reverse("tags", kwargs={"community_id": unmanaged.pk})
        assert unmanaged.tag_set.count() == tags_before

    def test_invite_form_is_closed(self, globex_client, unmanaged):
        """The invitation page sends the owner back to the manager list."""
        response = globex_client.get(
            reverse("manager_invite", kwargs={"community_id": unmanaged.pk})
        )

        assert response.status_code == 302
        assert response.url == reverse(
            "managers", kwargs={"community_id": unmanaged.pk}
        )


class TestCommunityWithoutLimits:
    def test_has_no_limits(self, acme):
        """Tags, segments, sources and managers can all be added well past the default limits."""
        fill(acme.community, tags=5, projects=5, sources=5)

        assert acme.community.management.can_add_tag()
        assert acme.community.management.can_add_project()
        assert acme.community.management.can_add_source()
        assert acme.community.management.can_add_manager()

    def test_tag_form_adds_a_tag_past_the_default_limit(self, owner_client, acme):
        """Posting the tag form creates the tag however many there already are."""
        fill(acme.community, tags=5)

        owner_client.post(
            reverse("tag_add", kwargs={"community_id": acme.community.pk}),
            {"name": "one-more", "color": "cccccc"},
        )

        assert acme.community.tag_set.filter(name="one-more").exists()


def test_scheduled_commands_skip_communities_that_are_not_active(acme, globex):
    """A command run for all communities only processes the active ones."""
    Report.objects.all().delete()
    acme.community.status = Community.SETUP
    acme.community.save(update_fields=("status",))

    call_command("make_reports")

    assert Report.objects.filter(community=globex.community).exists()
    assert not Report.objects.filter(community=acme.community).exists()
