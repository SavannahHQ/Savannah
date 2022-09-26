# Generated by Django 3.1.2 on 2022-09-26 20:20

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0149_auto_20220926_2019'),
    ]

    operations = [
        migrations.AlterField(
            model_name='activity',
            name='community',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='corm.community'),
        ),
        migrations.AlterField(
            model_name='activity',
            name='source',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='corm.source'),
        ),
        migrations.AlterField(
            model_name='contribution',
            name='source',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='corm.source'),
        ),
        migrations.AlterField(
            model_name='conversation',
            name='community',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='corm.community'),
        ),
        migrations.AlterField(
            model_name='conversation',
            name='source',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='corm.source'),
        ),        
        migrations.AlterField(
            model_name='event',
            name='source',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='corm.source'),
        ),
    ]
