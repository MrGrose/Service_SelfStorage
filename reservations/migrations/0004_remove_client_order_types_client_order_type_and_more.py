# Generated by Django 5.1.5 on 2025-01-22 10:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0003_remove_order_order_type_alter_ordertype_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='client',
            name='order_types',
        ),
        migrations.AddField(
            model_name='client',
            name='order_type',
            field=models.CharField(blank=True, choices=[('storage_rates', 'Тарифы хранения'), ('courier_pickup', 'Забор курьером'), ('self_delivery', 'Самому привезти'), ('my_orders', 'Мои заказы')], max_length=50, null=True, verbose_name='Тип заказа'),
        ),
        migrations.DeleteModel(
            name='Order',
        ),
    ]
