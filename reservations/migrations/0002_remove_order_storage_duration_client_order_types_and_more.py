# Generated by Django 5.1.5 on 2025-01-22 09:47

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='storage_duration',
        ),
        migrations.AddField(
            model_name='client',
            name='order_types',
            field=models.ManyToManyField(blank=True, to='reservations.ordertype', verbose_name='Типы заказов'),
        ),
        migrations.AddField(
            model_name='client',
            name='storage_duration',
            field=models.PositiveIntegerField(blank=True, choices=[(15, '15 дней'), (30, '30 дней'), (45, '45 дней'), (60, '60 дней'), (75, '75 дней'), (90, '90 дней'), (115, '115 дней'), (130, '130 дней'), (150, '150 дней')], null=True, verbose_name='Срок хранения'),
        ),
        migrations.AlterField(
            model_name='order',
            name='client',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='reservations.client', verbose_name='Клиент'),
        ),
    ]
