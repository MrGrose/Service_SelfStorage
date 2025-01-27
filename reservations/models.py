from django.db import models
from django.utils import timezone
from datetime import timedelta, datetime
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from reservations.link_statistics import shorten_link, count_clikcs
from typing import List, Optional, Any


class User(models.Model):
    """Модель пользователя.

    Атрибуты:
        user_id (int): Уникальный идентификатор пользователя.
        name (str): Имя пользователя.
        phone_number (str): Телефон пользователя.
        user_address (str, optional): Адрес пользователя.

    Методы:
        __str__(): Возвращает строковое представление имени пользователя.
        get_orders(): Возвращает все заказы пользователя.
    """
    user_id = models.AutoField('id пользователя', primary_key=True)
    name = models.CharField(verbose_name='Имя пользователя', max_length=200)
    phone_number = models.CharField(verbose_name='Телефон', max_length=20)
    user_address = models.CharField(verbose_name='Адрес клиента', max_length=200, null=True, blank=True)

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self) -> str:
        """Возвращает строковое представление имени пользователя."""
        return self.name

    def get_orders(self) -> List['Order']:
        """Возвращает все заказы пользователя.

        Returns:
            List[Order]: Список заказов пользователя.
        """
        return Order.objects.filter(user=self)


class Warehouse(models.Model):
    """Модель склада.

    Атрибуты:
        warehouse_id (int): Уникальный идентификатор склада.
        name (str): Название склада.
        warehouse_address (str, optional): Адрес склада.

    Методы:
        __str__(): Возвращает строковое представление названия склада.
        save(): Сохраняет склад и создает ячейки хранения.
        get_free_storage_units_count(): Возвращает количество свободных ячеек на складе.
    """
    warehouse_id = models.AutoField(verbose_name='ID склада', primary_key=True)
    name = models.CharField(verbose_name='Название склада', max_length=255)
    warehouse_address = models.CharField(verbose_name='Адрес склада', max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Склад'
        verbose_name_plural = 'Склады'

    def __str__(self) -> str:
        """Возвращает строковое представление названия склада."""
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Сохраняет склад и создает ячейки хранения.

        Метод создает ячейки хранения только если они еще не созданы.
        """
        super().save(*args, **kwargs)

        if not StorageUnit.objects.filter(warehouse=self).exists():
            sizes = ['small', 'small', 'medium', 'medium', 'large', 'large']
            for size in sizes:
                StorageUnit.objects.create(warehouse=self, size=size, is_occupied=False)

    def get_free_storage_units_count(self) -> int:
        """Возвращает количество свободных ячеек на складе.

        Returns:
            int: Количество свободных ячеек на складе.
        """
        return StorageUnit.objects.filter(warehouse=self, is_occupied=False).count()


class StorageUnit(models.Model):
    """Модель ячейки хранения.

    Атрибуты:
        unit_id (int): Уникальный идентификатор ячейки.
        warehouse (Warehouse): Связанный склад.
        size (str): Размер ячейки.
        is_occupied (bool): Занятость ячейки.

    Методы:
        __str__(): Возвращает строковое представление размера ячейки.
        has_active_orders(): Проверяет, есть ли активные заказы для данной ячейки.
        is_available(start_date, duration): Проверяет доступность ячейки на заданный период.
    """
    SIZE_CHOICES = [
        ('small', 'Маленькая (до 1 м³)'),
        ('medium', 'Средняя (1-5 м³)'),
        ('large', 'Большая (более 5 м³)'),
    ]

    unit_id = models.AutoField(primary_key=True, verbose_name='ID ячейки')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, verbose_name='Склад')
    size = models.CharField(max_length=10, choices=SIZE_CHOICES, verbose_name='Размер ячейки')
    is_occupied = models.BooleanField(default=False, verbose_name='Занятость')

    class Meta:
        verbose_name = 'Бокс хранения'
        verbose_name_plural = 'Боксы хранения'

    def __str__(self) -> str:
        """Возвращает представление ячейки."""
        return f"{self.get_size_display()}"

    def has_active_orders(self) -> bool:
        """Проверяет, есть ли активные заказы для данной ячейки.

        Returns:
            bool: True, если есть активные заказы, иначе False.
        """
        return Order.objects.filter(storage_unit=self, status='active').exists()

    def is_available(self, start_date: datetime, duration: int) -> bool:
        """Проверяет доступность ячейки на заданный период.

        Args:
            start_date (datetime): Дата начала аренды.
            duration (int): Длительность хранения в днях.

        Returns:
            bool: True, если ячейка доступна, иначе False.
        """
        end_date = start_date + timedelta(days=duration)
        overlapping_orders = Order.objects.filter(
            storage_unit=self,
            start_date__lt=end_date,
            created_at__gt=start_date
        )
        return not overlapping_orders.exists()


class Order(models.Model):
    """Модель заказа.

    Атрибуты:
        created_at (datetime): Дата создания заказа.
        order_id (int): Уникальный идентификатор заказа.
        user (User): Связанный пользователь.
        storage_unit (StorageUnit): Связанная ячейка хранения.
        storage_duration (int): Срок хранения в днях.
        status (str): Статус заказа.
        start_date (datetime): Дата начала аренды.

    Методы:
        __str__(): Возвращает строковое представление заказа.
        is_expired(): Проверяет, просрочен ли заказ.
        save(): Сохраняет заказ и проверяет доступность ячейки.
        release_storage_unit(): Освобождает ячейку хранения.
        calculated_total_cost: Возвращает общую стоимость хранения.
        reminder_date(): Расчитывает дату напоминания о окончании срока хранения.
    """
    STATUS_CHOICES = [
        ('pending', 'Ожидает'),
        ('active', 'Активен'),
        ('expired', 'Просрочен'),
        ('completed', 'Закончен'),
    ]
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Дата создания заказа')
    order_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    storage_unit = models.ForeignKey(StorageUnit, on_delete=models.CASCADE, verbose_name='Ячейка хранения')
    storage_duration = models.PositiveIntegerField(verbose_name='Срок хранения (дни)')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active', verbose_name='Статус заказа', db_index=True)
    start_date = models.DateTimeField(verbose_name='Дата начала аренды', default=timezone.now)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    def __str__(self) -> str:
        """Возвращает представление заказа (ID и имя пользователя)."""
        return f"Заказ {self.order_id} от {self.user.name}"

    def is_expired(self) -> bool:
        """Проверяет, просрочен ли заказ.

        Returns:
            bool: True, если заказ просрочен, иначе False.
        """
        return timezone.now() > self.start_date + timedelta(days=self.storage_duration)

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Сохраняет заказ и проверяет доступность ячейки.

        Если ячейка уже занята на указанный период, вызывает ValidationError.
        """
        now = timezone.now()

        if not self.pk:
            overlapping_orders = Order.objects.filter(
                storage_unit=self.storage_unit,
                start_date__lt=self.start_date + timedelta(days=self.storage_duration),
                status__in=['active', 'pending']
            )
            if overlapping_orders.exists():
                raise ValidationError("Ячейка уже забронирована на этот период.")

        if self.status not in ['completed', 'expired']:
            if self.start_date > now:
                self.status = 'pending'
            elif self.start_date <= now < self.start_date + timedelta(days=self.storage_duration):
                self.status = 'active'
            else:
                self.status = 'expired'

        super().save(*args, **kwargs)
        self.storage_unit.is_occupied = self.status in ['active', 'pending']
        self.storage_unit.save()

    def release_storage_unit(self) -> None:
        """Освобождает ячейку хранения, устанавливая флаг is_occupied в False."""
        if self.storage_unit.is_occupied:
            self.storage_unit.is_occupied = False
            self.storage_unit.save()

    @property
    def calculated_total_cost(self) -> float:
        """Возвращает общую стоимость хранения на основе размера ячейки и срока хранения.

        Returns:
            float: Общая стоимость хранения.
        """
        costs = {'small': 100, 'medium': 300, 'large': 500}
        return self.storage_duration * costs.get(self.storage_unit.size, 0)

    def reminder_date(self) -> Optional[timezone.datetime]:
        """Расчет даты напоминания о окончания срока хранения.

        Returns:
            Optional[timezone.datetime]: Дата напоминания или None.
        """
        if self.storage_duration <= 14:
            return self.start_date
        return self.start_date + timedelta(days=self.storage_duration-14) if self.start_date else None


@receiver(post_delete, sender=User)
def user_post_delete_handler(sender: type, instance: User, **kwargs: Any) -> None:
    """Обработчик сигнала, который освобождает ячейки и удаляет заказы при удалении пользователя.
    Отображение происходит в админ панели.

    Args:
        sender (type): Тип сигнала.
        instance (User): Удаляемый пользователь.
    """
    orders = Order.objects.filter(user=instance)
    for order in orders:
        order.release_storage_unit()
        order.delete()


class Link(models.Model):
    """Модель сокращенной ссылки.

    Атрибуты:
        original_url (str): Оригинальная ссылка.
        short_url (str): Сокращенная ссылка.
        click_count (int): Количество кликов по сокращенной ссылке.

    Методы:
        save(): Сохраняет ссылку и обновляет количество кликов.
        update_click_count(): Обновляет количество кликов по ссылке.
        __str__(): Возвращает строковое представление ссылки.
    """
    original_url = models.URLField(verbose_name='Оригинальная ссылка')
    short_url = models.CharField(verbose_name='Сокращенная ссылка', max_length=100, blank=True)
    click_count = models.IntegerField(verbose_name='Кол-во кликов', default=0, null=True, blank=True)

    class Meta:
        verbose_name = 'Ссылка'
        verbose_name_plural = 'Ссылки'

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Сохраняет ссылку и генерирует ее сокращенную версию.

        Также обновляет количество кликов по ссылке.
        """
        if not self.short_url:
            self.short_url = shorten_link(self.original_url)
        super().save(*args, **kwargs)
        self.update_click_count()

    def update_click_count(self) -> None:
        """Обновляет количество кликов по сокращенной ссылке."""
        if self.short_url:
            try:
                new_click_count = count_clikcs(self.short_url)
                self.click_count = new_click_count
                self.save()
            except Exception as e:
                print(f"Ошибка при обновлении количества кликов: {e}")

    def __str__(self) -> str:
        """Возвращает представление сокращенной и оригинальной ссылок
        с количеством кликов.
        """
        return f'{self.short_url} -> {self.original_url}, кол-во кликов {self.click_count}'
