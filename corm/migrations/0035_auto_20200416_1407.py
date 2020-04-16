# Generated by Django 3.0.4 on 2020-04-16 14:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0034_auto_20200416_1403'),
    ]

    operations = [
        migrations.AlterField(
            model_name='member',
            name='date_added',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='member',
            name='name',
            field=models.CharField(db_index=True, max_length=256),
        ),
        migrations.AlterField(
            model_name='memberconnection',
            name='first_connected',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AlterField(
            model_name='memberconnection',
            name='last_connected',
            field=models.DateTimeField(db_index=True),
        ),
    ]
