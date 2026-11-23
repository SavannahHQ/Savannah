from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('demo', '0003_auto_20220217_2259'),
    ]

    operations = [
        # blank only affects form validation, the column and its constraint stay as they are.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='demonstration',
                    name='log',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='demo.demolog'),
                ),
            ],
        ),
    ]
