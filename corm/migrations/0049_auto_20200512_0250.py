# Generated by Django 3.0.4 on 2020-05-12 02:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0048_auto_20200505_1518'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='tag',
            options={'ordering': ('name',)},
        ),
        migrations.AlterField(
            model_name='source',
            name='connector',
            field=models.CharField(choices=[('corm.plugins.null', 'Manual Entry'), ('corm.plugins.reddit', 'Reddit'), ('corm.plugins.twitter', 'Twitter'), ('corm.plugins.discourse', 'Discourse'), ('corm.plugins.slack', 'Slack'), ('corm.plugins.github', 'Github'), ('corm.plugins.rss', 'RSS')], max_length=256),
        ),
    ]
