# -*- coding: utf-8 -*-


from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('viewhistory', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='client_id',
            field=models.CharField(max_length=255),
        ),
    ]
