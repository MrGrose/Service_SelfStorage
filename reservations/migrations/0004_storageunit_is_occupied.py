# Generated by Django 5.1.5 on 2025-01-23 09:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0003_remove_storageunit_is_occupied'),
    ]

    operations = [
        migrations.AddField(
            model_name='storageunit',
            name='is_occupied',
            field=models.BooleanField(default=False, verbose_name='Занятость'),
        ),
    ]
