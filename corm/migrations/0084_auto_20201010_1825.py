# Generated by Django 3.0.4 on 2020-10-10 18:25

from django.db import migrations, models

def noop(apps, schema_editor):
    pass

def set_soure_first(apps, schema_editor):
    Source = apps.get_model('corm', 'Source')
    for s in Source.objects.all():
        s.first_import = s.community.created
        s.save()

def set_channel_first(apps, schema_editor):
    Channel = apps.get_model('corm', 'Channel')
    for c in Channel.objects.all():
        c.first_import = c.source.first_import
        c.save()

def set_tag_changed(apps, schema_editor):
    Tag = apps.get_model('corm', 'Tag')
    for t in Tag.objects.all():
        t.last_changed = t.community.created
        t.save()

class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0083_auto_20201001_1857'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='first_import',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(set_soure_first, noop),
        migrations.AddField(
            model_name='channel',
            name='first_import',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(set_channel_first, noop),
        migrations.AddField(
            model_name='tag',
            name='last_changed',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.RunPython(set_tag_changed, noop),
    ]