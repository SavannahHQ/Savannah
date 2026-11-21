import datetime
import types

import pytest

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management import call_command

from corm.models import (
    Channel,
    Community,
    Company,
    Contact,
    Contribution,
    ContributionType,
    Conversation,
    Event,
    EventAttendee,
    Gift,
    GiftType,
    Member,
    Note,
    Opportunity,
    Participant,
    Project,
    Report,
    Source,
    Tag,
    Task,
    UploadedFile,
    WebHook,
)

PASSWORD = "correct-horse-battery-staple"  # nosec B105


def create_community(*, owner, name, api_key):
    """A community that has been imported into for a month, the way a tenant's data looks."""
    now = datetime.datetime.utcnow()
    last_month = now - datetime.timedelta(days=30)

    community = Community.objects.create(
        owner=owner, name=name, status=Community.ACTIVE
    )
    community.bootstrap()
    tag = Tag.objects.create(community=community, name="ambassador", color="1f77b4")
    company = Company.objects.create(
        community=community, name=f"{name} Ltd", website="https://example.com"
    )
    source = Source.objects.create(
        community=community,
        connector="corm.plugins.api",
        name=f"{name} forum",
        icon_name="fas fa-cogs",
        api_key=api_key,
        first_import=last_month,
        last_import=now,
    )
    channel = Channel.objects.create(
        source=source,
        name="general",
        origin_id="general",
        first_import=last_month,
        last_import=now,
    )

    members = []
    for handle in ("ada", "grace", "linus"):
        member = Member.objects.create(
            community=community,
            name=f"{handle.title()} of {name}",
            email_address=f"{handle}@example.com",
            company=company,
            first_seen=last_month,
            last_seen=now,
        )
        member.tags.add(tag)
        Contact.objects.create(
            member=member,
            source=source,
            origin_id=f"{handle}-of-{name.lower()}",
            detail=handle,
            email_address=f"{handle}@example.com",
        )
        members.append(member)
    ada, grace, linus = members

    conversation = Conversation.objects.create(
        community=community,
        source=source,
        channel=channel,
        origin_id="thread-1",
        speaker=ada,
        content=f"How do I get started with {name}?",
        timestamp=now - datetime.timedelta(days=3),
        location="https://example.com/thread-1",
    )
    conversation.tags.add(tag)
    reply = Conversation.objects.create(
        community=community,
        source=source,
        channel=channel,
        origin_id="thread-1-reply",
        speaker=grace,
        content="Welcome! Start with the documentation.",
        timestamp=now - datetime.timedelta(days=2),
        thread_start=conversation,
    )
    for spoken in (conversation, reply):
        for listener in (ada, grace):
            Participant.objects.create(
                community=community,
                conversation=spoken,
                initiator=spoken.speaker,
                member=listener,
                timestamp=spoken.timestamp,
            )
        spoken.update_activity()

    contribution_type = ContributionType.objects.create(
        community=community, source=source, name="Pull Request"
    )
    contribution = Contribution.objects.create(
        community=community,
        source=source,
        channel=channel,
        contribution_type=contribution_type,
        origin_id="pr-1",
        title=f"Fix the {name} installer",
        author=linus,
        timestamp=now - datetime.timedelta(days=1),
    )
    contribution.update_activity()

    event = Event.objects.create(
        community=community,
        source=source,
        channel=channel,
        origin_id="meetup-1",
        title=f"{name} meetup",
        start_timestamp=now - datetime.timedelta(days=7),
        end_timestamp=now - datetime.timedelta(days=7) + datetime.timedelta(hours=2),
    )
    attendance = EventAttendee.objects.create(
        community=community, event=event, member=grace, timestamp=event.start_timestamp
    )
    attendance.update_activity()

    project = Project.objects.create(community=community, name=f"{name} docs", tag=tag)
    project.channels.add(channel)
    task = Task.objects.create(
        community=community,
        project=project,
        owner=owner,
        name=f"Thank Linus for the {name} fix",
        due=now + datetime.timedelta(days=7),
    )
    task.stakeholders.add(linus)
    Note.objects.create(
        member=ada, author=owner, content=f"Met Ada at the {name} meetup."
    )
    gift_type = GiftType.objects.create(
        community=community, name="Sticker pack", contents="Stickers"
    )
    gift = Gift.objects.create(
        community=community,
        member=linus,
        gift_type=gift_type,
        sent_date=now,
        reason="First fix",
    )
    opportunity = Opportunity.objects.create(
        community=community,
        member=grace,
        name=f"{name} conference talk",
        description="Speak about onboarding.",
        contribution_type=contribution_type,
        deadline=now + datetime.timedelta(days=30),
        created_by=owner,
    )
    webhook = WebHook.objects.create(
        community=community,
        user=owner,
        event="Member",
        target="https://example.com/hook",
    )
    upload = UploadedFile.objects.create(
        community=community,
        source=source,
        name="attendees.csv",
        uploaded_by=owner,
        uploaded_to=ContentFile(
            f"Name,Email\nAda of {name},ada@example.com\n".encode(), "attendees.csv"
        ),
    )

    call_command("level_check", community_id=community.id)
    call_command("make_reports", community_id=community.id)
    report = Report.objects.get(community=community, report_type=Report.GROWTH)

    return types.SimpleNamespace(
        community=community,
        owner=owner,
        password=PASSWORD,
        tag=tag,
        company=company,
        source=source,
        channel=channel,
        member=ada,
        contributor=linus,
        event=event,
        project=project,
        task=task,
        gift_type=gift_type,
        gift=gift,
        opportunity=opportunity,
        webhook=webhook,
        upload=upload,
        report=report,
    )


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def acme(db):
    """A tenant with no plan limits, because it is a demonstration community."""
    owner = User.objects.create_user("olivia", "olivia@example.com", PASSWORD)
    tenant = create_community(owner=owner, name="Acme", api_key="acme-api-token")
    tenant.community.status = Community.DEMO
    tenant.community.save(update_fields=("status",))
    return tenant


@pytest.fixture
def globex(db):
    """A second tenant, whose owner has no rights over Acme."""
    owner = User.objects.create_user("gordon", "gordon@example.com", PASSWORD)
    return create_community(owner=owner, name="Globex", api_key="globex-api-token")


@pytest.fixture
def owner_client(client, acme):
    client.force_login(acme.owner)
    return client


@pytest.fixture
def globex_client(client, globex):
    client.force_login(globex.owner)
    return client
