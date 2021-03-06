# Generated by Django 3.0.4 on 2020-03-19 18:32

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0012_auto_20200319_1813'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256)),
                ('feed', models.URLField()),
                ('community', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='corm.Community')),
            ],
        ),
        migrations.CreateModel(
            name='Activity',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=256)),
                ('timestamp', models.DateTimeField()),
                ('location', models.URLField()),
                ('activity_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='corm.ActivityType')),
                ('author', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='corm.Member')),
                ('community', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='corm.Community')),
            ],
        ),
    ]
