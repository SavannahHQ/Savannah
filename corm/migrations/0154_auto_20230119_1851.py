# Generated by Django 3.1.2 on 2023-01-19 18:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0153_auto_20230107_1811'),
    ]

    operations = [
        migrations.AddField(
            model_name='webhook',
            name='enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='webhook',
            name='send_failed_attempts',
            field=models.SmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='webhook',
            name='send_failed_message',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AddField(
            model_name='webhookevent',
            name='send_failed_attempts',
            field=models.SmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='webhookevent',
            name='send_failed_message',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
    ]
