# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-08 13:06
from __future__ import unicode_literals

from django.db import migrations

from ..models import Organisation

class Migration(migrations.Migration):

    dependencies = [
        ('organisations', '0008_auto_20181108_1259'),
    ]

    operations = [
        migrations.RunSQL(
            [("Update " + Organisation._meta.db_table + " SET free_to_use_subscription = true;")],
        )
    ]