# Generated by Django 5.1.5 on 2025-01-23 10:45

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0006_alter_order_status'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Reminder',
        ),
    ]
