# Generated by Django 3.0.4 on 2021-01-22 18:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0097_auto_20210121_2020'),
    ]

    operations = [
        migrations.AlterField(
            model_name='company',
            name='is_staff',
            field=models.BooleanField(default=False, help_text='Treat members as staff'),
        ),
        migrations.AlterField(
            model_name='managerprofile',
            name='last_seen',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]