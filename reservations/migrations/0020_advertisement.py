# Generated by Django 5.1.5 on 2025-01-24 17:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reservations', '0019_alter_order_start_date'),
    ]

    operations = [
        migrations.CreateModel(
            name='Advertisement',
            fields=[
                ('promo_id', models.AutoField(primary_key=True, serialize=False)),
                ('promo_name', models.CharField(max_length=200, verbose_name='')),
            ],
        ),
    ]
