from django.db import migrations

import corm.fields


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0157_auto_20230531_2149'),
    ]

    operations = [
        # Only the field class and its choices differ, the columns stay as they are.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='managerprofile',
                    name='tz',
                    field=corm.fields.DeploymentChoicesCharField(default='UTC', max_length=32, verbose_name='Timezone'),
                ),
                migrations.AlterField(
                    model_name='source',
                    name='connector',
                    field=corm.fields.DeploymentChoicesCharField(max_length=256),
                ),
                migrations.AlterField(
                    model_name='tag',
                    name='connector',
                    field=corm.fields.DeploymentChoicesCharField(blank=True, max_length=256, null=True),
                ),
                migrations.AlterField(
                    model_name='userauthcredentials',
                    name='connector',
                    field=corm.fields.DeploymentChoicesCharField(max_length=256),
                ),
            ],
        ),
    ]
