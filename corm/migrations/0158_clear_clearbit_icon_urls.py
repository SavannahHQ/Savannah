# Clearbit's free logo API (logo.clearbit.com) was shut down on 2025-12-01.
# Company.logo_url used to store a Clearbit URL in icon_url the first time a
# logo was requested; clear those so logos are derived from the configured
# COMPANY_LOGO_URL provider instead. Explicitly set icon_urls are untouched.

from django.db import migrations


def clear_clearbit_urls(apps, schema_editor):
    Company = apps.get_model('corm', 'Company')
    Company.objects.filter(icon_url__startswith='https://logo.clearbit.com/').update(icon_url=None)


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0157_auto_20230531_2149'),
    ]

    operations = [
        migrations.RunPython(clear_clearbit_urls, migrations.RunPython.noop),
    ]
