# Generated by Django 3.0.4 on 2020-07-19 21:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('corm', '0065_merge_20200719_2155'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='threshold_contributor',
            field=models.SmallIntegerField(default=1, help_text='Contributions to become a Contributor'),
        ),
        migrations.AddField(
            model_name='project',
            name='threshold_core',
            field=models.SmallIntegerField(default=5, help_text='Contributions to become a Core Contributor'),
        ),
        migrations.AddField(
            model_name='project',
            name='threshold_participant',
            field=models.SmallIntegerField(default=5, help_text='Conversations to become a Participant'),
        ),
        migrations.AddField(
            model_name='project',
            name='threshold_user',
            field=models.SmallIntegerField(default=1, help_text='Conversations to become a User'),
        ),
        migrations.AlterField(
            model_name='event',
            name='promotions',
            field=models.ManyToManyField(blank=True, to='corm.Promotion'),
        ),
        migrations.AlterField(
            model_name='memberlevel',
            name='level',
            field=models.SmallIntegerField(blank=True, choices=[(0, 'User'), (1, 'Participant'), (2, 'Contributor'), (3, 'Core')], default=0, null=True),
        ),
        migrations.AlterField(
            model_name='source',
            name='connector',
            field=models.CharField(choices=[('corm.plugins.null', 'Manual Entry'), ('corm.plugins.reddit', 'Reddit'), ('corm.plugins.twitter', 'Twitter'), ('corm.plugins.discourse', 'Discourse'), ('corm.plugins.slack', 'Slack'), ('corm.plugins.github', 'Github'), ('corm.plugins.rss', 'RSS')], max_length=256),
        ),
        migrations.AlterField(
            model_name='userauthcredentials',
            name='connector',
            field=models.CharField(choices=[('corm.plugins.null', 'Manual Entry'), ('corm.plugins.reddit', 'Reddit'), ('corm.plugins.twitter', 'Twitter'), ('corm.plugins.discourse', 'Discourse'), ('corm.plugins.slack', 'Slack'), ('corm.plugins.github', 'Github'), ('corm.plugins.rss', 'RSS')], max_length=256),
        ),
    ]
