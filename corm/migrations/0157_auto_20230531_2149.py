# Generated by Django 3.1.2 on 2023-05-31 21:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0156_auto_20230518_0127'),
    ]

    operations = [
        migrations.AlterField(
            model_name='source',
            name='auth_secret',
            field=models.CharField(blank=True, max_length=1024, null=True),
        ),
        migrations.AlterField(
            model_name='userauthcredentials',
            name='auth_refresh',
            field=models.CharField(blank=True, max_length=1024, null=True),
        ),
        migrations.AlterField(
            model_name='userauthcredentials',
            name='auth_secret',
            field=models.CharField(blank=True, max_length=1024, null=True),
        ),
    ]