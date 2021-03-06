# Generated by Django 3.0.4 on 2020-07-07 21:57

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('corm', '0059_auto_20200611_1539'),
        ('frontendv2', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmailRecord',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('when', models.DateTimeField(auto_now_add=True)),
                ('email', models.EmailField(max_length=254)),
                ('category', models.CharField(max_length=128)),
                ('subject', models.CharField(max_length=128)),
                ('body', models.TextField(max_length=1024)),
                ('ok', models.BooleanField(default=True)),
                ('member', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recv_messages', to='corm.Member')),
                ('sender', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_messages', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
