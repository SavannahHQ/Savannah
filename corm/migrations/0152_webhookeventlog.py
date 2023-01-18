# Generated by Django 3.1.2 on 2023-01-04 17:35

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0151_auto_20230104_1733'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebHookEventLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('status', models.SmallIntegerField(blank=True, null=True)),
                ('response', models.TextField(blank=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='log', to='corm.webhookevent')),
            ],
        ),
    ]