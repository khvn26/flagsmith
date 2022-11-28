# Generated by Django 3.2.16 on 2022-11-28 15:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api_keys', '0002_soft_delete_api_keys'),
        ('workflows_core', '0003_historicalchangerequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalchangerequest',
            name='master_api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='api_keys.masterapikey'),
        ),
    ]