import logging
import os
import random
import re
import qrcode
from io import BytesIO
from telegram import InputFile
from datetime import datetime, timedelta

import django
import telegram
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone
from django.utils.timezone import now
from environs import Env
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    Filters,
    MessageHandler,
    Updater,
)

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'storage_bot.settings')
django.setup()

from reservations.models import (
    Order,
    StorageUnit,
    User,
    Warehouse
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для диалога
CONSENT = 0
MAIN_MENU = 1
REQUEST_NAME = 2
REQUEST_PHONE = 3
REQUEST_START_DATE = 4
REQUEST_DURATION = 5
REQUEST_ADDRESS = 6


def start(update: Update, context: CallbackContext):
    welcome_message = (
        "Привет! 👋 Добро пожаловать в SelfStorage – сервис для хранения вещей.\n\n"
        "📦 Когда наш сервис может быть полезен:\n"
        "- Если у тебя дома не хватает места для сезонных вещей, таких как лыжи, сноуборды или велосипед.\n"
        "- Во время переезда – чтобы временно хранить мебель и другие вещи.\n"
        "- Если есть ценные вещи, которые занимают слишком много пространства, но выбрасывать их жалко.\n\n"
        "📍 Напиши /help, чтобы узнать о доступных командах и начать работу.\n\n"
        "Для продолжения работы с ботом необходимо дать согласие на обработку персональных данных."
    )
    update.message.reply_text(welcome_message)

    # Отправляем файл с согласием на обработку данных
    pdf_file = "consent_form.pdf"
    try:
        with open(pdf_file, "rb") as file:
            context.bot.send_document(chat_id=update.effective_chat.id, document=file)
    except FileNotFoundError:
        update.message.reply_text("Файл с соглашением не найден. Пожалуйста, попробуйте позже.")

    # Показываем кнопки для подтверждения
    reply_markup = ReplyKeyboardMarkup([["Принять"], ["Отказаться"]],
                                       one_time_keyboard=True,
                                       resize_keyboard=True)
    update.message.reply_text(
        "После ознакомления с документом выберите действие:\n\n"
        "✅ Нажмите 'Принять', чтобы продолжить.\n"
        "❌ Нажмите 'Отказаться', чтобы выйти. \n\n"
        "⚠️Нажимая 'Принять', я подтверждаю своё согласие на обработку персональных данных.",
        reply_markup=reply_markup,
    )
    return CONSENT


def handle_consent(update: Update, context: CallbackContext):
    user_response = update.message.text
    if user_response == "Принять":
        reply_markup = ReplyKeyboardMarkup(
            [["Мой заказ", "Тарифы и условия хранения"], ["Заказать ячейку"]],
            resize_keyboard=True
        )
        update.message.reply_text(
            "Спасибо! Вы приняли условия обработки персональных данных. Теперь мы можем продолжить работу. 🛠️\n\n"
            "Выберите действие из меню ниже:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    elif user_response == "Отказаться":
        # Повторно показываем кнопки
        reply_markup = ReplyKeyboardMarkup([["Принять"], ["Отказаться"]],
                                           one_time_keyboard=True,
                                           resize_keyboard=True)
        update.message.reply_text(
            "Вы отказались от обработки персональных данных. "
            "Без этого мы не можем предоставить услугу. Если передумаете, выберите 'Принять'.",
            reply_markup=reply_markup
        )
        return CONSENT  # Оставляем пользователя в этом состоянии
    else:
        # Повторно показываем кнопки, если ввод некорректен
        reply_markup = ReplyKeyboardMarkup([["Принять"], ["Отказаться"]],
                                           one_time_keyboard=True,
                                           resize_keyboard=True)
        update.message.reply_text(
            "Пожалуйста, выберите одну из предложенных опций: Принять или Отказаться.",
            reply_markup=reply_markup
        )
        return CONSENT


def tariffs(update: Update, context: CallbackContext):
    # Тарифы для каждого размера
    tariffs_data = {
        'small': 100,
        'medium': 300,
        'large': 500,
    }
    size_labels = dict(StorageUnit.SIZE_CHOICES)  # Преобразуем в словарь для удобства

    # Подсчитываем количество свободных ячеек по каждому размеру
    free_sizes_count = (
        StorageUnit.objects.filter(is_occupied=False)
        .values('size')
        .annotate(count=Count('size'))
    )

    # Формируем текст для тарифов
    tariffs_info = "📋 *Тарифы на хранение и количество свободных ячеек:*\n\n"
    for size_data in free_sizes_count:
        size = size_data['size']
        count = size_data['count']
        price = tariffs_data.get(size, 0)
        tariffs_info += f"- {size_labels.get(size, 'Неизвестно')} ({count} свободных): {price} руб./день\n"

    tariffs_info += (
        "\n⚠️ *Запрещенные для хранения вещи:*\n"
        "Мы не принимаем на хранение имущество, которое ограничено по законодательству РФ "
        "или создает неудобства для других арендаторов.\n\n"
        "❌*Нельзя хранить*:\n"
        "- Оружие, боеприпасы, взрывчатые вещества\n"
        "- Токсичные, радиоактивные и легковоспламеняющиеся вещества\n"
        "- Животных\n"
        "- Пищевые продукты с истекающим сроком годности\n"
        "- Любое имущество, нарушающее законодательство РФ"
    )

    update.message.reply_text(tariffs_info, parse_mode=telegram.ParseMode.MARKDOWN)


def handle_self_delivery(update: Update, context: CallbackContext):
    update.callback_query.answer()
    context.user_data['delivery_type'] = "self_delivery"

    warehouses = Warehouse.objects.all()

    self_delivery_info = "🚗 *Адреса складов для самостоятельной доставки ваших вещей:*\n\n"
    for idx, warehouse in enumerate(warehouses, start=1):
        self_delivery_info += f"{idx}️⃣ Склад: {warehouse.warehouse_address}\n"

    self_delivery_info += (
        "\n📍 Если вы не уверены в размере подходящей ячейки или не хотите самостоятельно измерять вещи, "
        "наш персонал произведет все замеры на месте."
    )
    keyboard = [
        [InlineKeyboardButton("Продолжить оформление заказа", callback_data="continue_order_self_delivery")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.callback_query.message.reply_text(
        self_delivery_info,
        parse_mode=telegram.ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


def start_order_form_self_delivery(update: Update, context: CallbackContext):
    update.callback_query.answer()
    update.callback_query.message.reply_text(
        "👤 Для начала укажите ваше ФИО: (например: Иванов Иван Иванович)",
        reply_markup=ReplyKeyboardRemove()  # Убираем главное меню
    )
    return REQUEST_NAME


def handle_courier_delivery(update: Update, context: CallbackContext):
    update.callback_query.answer()
    courier_info = (
        "📦 *Курьерская доставка:*\n\n"
        "Мы бесплатно заберём ваши вещи из дома или офиса. Все замеры будут произведены курьером на месте.\n\n"
        "📋 *Процесс оформления заказа:*\n"
        "1️⃣ Вы указываете свои данные (ФИО, телефон, адрес и срок хранения).\n"
        "2️⃣ Курьер связывается с вами.\n"
        "3️⃣ Мы забираем ваши вещи и помещаем их на хранение в ячейку.\n\n"
        "🚚 Курьер приедет в удобное для вас время и заберёт вещи быстро и безопасно.\n\n"
        "Нажмите *Продолжить оформление заказа*, чтобы ввести данные и завершить заказ."
    )

    keyboard = [
        [InlineKeyboardButton("Продолжить оформление заказа", callback_data="continue_order")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.callback_query.message.reply_text(
        courier_info,
        parse_mode=telegram.ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


def order_box(update: Update, context: CallbackContext):
    # Убираем кнопку из главного меню и выводим выбор метода доставки
    keyboard = [
        [InlineKeyboardButton("Доставить мои вещи курьером", callback_data="deliver_courier")],
        [InlineKeyboardButton("Привезу самостоятельно", callback_data="self_delivery")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        "Как вы хотите заказать ячейку? Выберите способ доставки.",
        reply_markup=reply_markup
    )
    # Завершаем основной ConversationHandler, чтобы не было конфликтов
    return ConversationHandler.END


def start_order_form(update: Update, context: CallbackContext):
    logger.info(f"Пользователь {update.effective_user.id} начал оформление заказа.")
    update.callback_query.answer()
    update.callback_query.message.reply_text(
        "👤 Для начала укажите ваше ФИО: (например: Иванов Иван Иванович)",
        reply_markup=ReplyKeyboardRemove()  # Убираем главное меню
    )
    return REQUEST_NAME


def request_name(update: Update, context: CallbackContext):
    user_name = update.message.text.strip()
    if not re.match(r"^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+$", user_name):
        update.message.reply_text("⚠️ Пожалуйста, укажите ваше ФИО в формате: Иванов Иван Иванович.")
        return REQUEST_NAME

    context.user_data['name'] = user_name
    update.message.reply_text("📞 Укажите ваш номер телефона (например: +79991234567):")
    return REQUEST_PHONE


def request_phone(update: Update, context: CallbackContext):
    phone = update.message.text.strip()
    if not re.match(r"^\+7\d{10}$", phone):
        update.message.reply_text("⚠️ Пожалуйста, укажите корректный номер телефона в формате: +79991234567.")
        return REQUEST_PHONE

    context.user_data['phone'] = phone
    update.message.reply_text("📅 Укажите дату начала хранения (в формате ДД.ММ.ГГГГ):")
    return REQUEST_START_DATE


def request_start_date(update: Update, context: CallbackContext):
    start_date_str = update.message.text.strip()
    try:
        start_date = datetime.strptime(start_date_str, "%d.%m.%Y")
        start_date = timezone.make_aware(start_date)
        if start_date.date() < datetime.now().date():
            update.message.reply_text("⚠️ Дата начала хранения не может быть в прошлом.")
            return REQUEST_START_DATE
    except ValueError:
        update.message.reply_text("⚠️ Укажите дату в формате ДД.ММ.ГГГГ.")
        return REQUEST_START_DATE

    context.user_data['start_date'] = start_date
    update.message.reply_text("📦 Укажите срок хранения в днях (например: 30):")
    return REQUEST_DURATION


def request_duration(update: Update, context: CallbackContext):
    try:
        duration = int(update.message.text.strip())
        if duration <= 0:
            raise ValueError
        context.user_data['storage_duration'] = duration

        # Проверяем тип доставки
        delivery_type = context.user_data.get('delivery_type')
        if delivery_type == "self_delivery":
            return finalize_order_self(update, context, delivery_type="self_delivery")

        else:# Если доставка курьером, запрашиваем адрес
            update.message.reply_text(
                "📍 Укажите адрес, откуда нужно забрать вещи (например: г. Москва, ул. Ленина, д. 10):"
            )
            return REQUEST_ADDRESS
    except ValueError:
        update.message.reply_text(
            "⚠️ Пожалуйста, введите корректный срок хранения в днях (число дней не может быть отрицательным)."
        )
        return REQUEST_DURATION


def request_duration_self_delivery(update: Update, context: CallbackContext):
    try:
        duration = int(update.message.text.strip())
        if duration <= 0:
            raise ValueError
        context.user_data['storage_duration'] = duration

        # Завершение заказа
        return finalize_order_self(update, context, delivery_type="self_delivery")
    except ValueError:
        update.message.reply_text("⚠️ Пожалуйста, введите корректный срок хранения в днях.")
        return REQUEST_DURATION


def finalize_order_courier(update: Update, context: CallbackContext):
    context.user_data['address'] = update.message.text.strip()

    # Создаем или находим пользователя в базе данных
    user, created = User.objects.get_or_create(
        user_id=update.effective_user.id,
        defaults={
            'name': context.user_data['name'],
            'phone_number': context.user_data['phone'],
        }
    )
    if not created:  # Если пользователь уже существует, обновим данные
        user.name = context.user_data['name']
        user.phone_number = context.user_data['phone']
        user.save()

    # Ищем свободную ячейку
    free_units = StorageUnit.objects.filter(is_occupied=False)
    if not free_units.exists():
        update.message.reply_text("⚠️ На данный момент все ячейки заняты. Попробуйте позже.")
        return ConversationHandler.END

    # Рандомно выбираем свободную ячейку
    selected_unit = random.choice(free_units)

    # Создаем заказ
    try:
        order = Order.objects.create(
            user=user,
            created_at=context.user_data['start_date'],
            storage_unit=selected_unit,
            storage_duration=context.user_data['storage_duration']
        )
        update.message.reply_text(
            "✅ Спасибо! Ваш заказ принят.\n\n"
            f"📋 *Детали заказа:*\n"
            f"👤 ФИО: {user.name}\n"
            f"📞 Телефон: {user.phone_number}\n"
            f"📅 Дата начала хранения: {context.user_data['start_date']}\n"
            f"📦 Срок хранения: {context.user_data['storage_duration']} дней\n"
            f"📍 Адрес: {context.user_data['address']}\n"
            f"🏷️ Ячейка хранения: {selected_unit}\n\n"
            "Курьер свяжется с вами в ближайшее время. 😊",
            parse_mode=telegram.ParseMode.MARKDOWN
        )
    except ValidationError as e:
        update.message.reply_text(f"⚠️ Ошибка при создании заказа: {e}")
        return ConversationHandler.END
    reply_markup = ReplyKeyboardMarkup(
        [["Мой заказ", "Тарифы и условия хранения"], ["Заказать ячейку"]],
        resize_keyboard=True
    )
    update.message.reply_text(
        "Если вас интересует что-то еще, выберите действие из меню ниже:",
        reply_markup=reply_markup
    )
    return ConversationHandler.END


def finalize_order_self(update: Update, context: CallbackContext, delivery_type="courier"):
    user, created = User.objects.get_or_create(
        user_id=update.effective_user.id,
        defaults={
            'name': context.user_data['name'],
            'phone_number': context.user_data['phone'],
        }
    )
    if not created:  # Если пользователь уже существует, обновим данные
        user.name = context.user_data['name']
        user.phone_number = context.user_data['phone']
        user.save()

    # Ищем свободную ячейку
    free_units = StorageUnit.objects.filter(is_occupied=False)
    if not free_units.exists():
        update.message.reply_text("⚠️ На данный момент все ячейки заняты. Попробуйте позже.")
        return ConversationHandler.END

    # Рандомно выбираем свободную ячейку
    selected_unit = random.choice(free_units)

    # Создаем заказ
    try:
        order = Order.objects.create(
            user=user,
            created_at=context.user_data['start_date'],
            storage_unit=selected_unit,
            storage_duration=context.user_data['storage_duration']
        )
        update.message.reply_text(
            "✅ Спасибо! Ваш заказ принят.\n\n"
            f"📋 *Детали заказа:*\n"
            f"👤 ФИО: {user.name}\n"
            f"📞 Телефон: {user.phone_number}\n"
            f"📅 Дата начала хранения: {context.user_data['start_date']}\n"
            f"📦 Срок хранения: {context.user_data['storage_duration']} дней\n"
            f"📍 Самостоятельная доставка\n"
            f"🏷️ Ячейка хранения: {selected_unit}\n\n",
            parse_mode=telegram.ParseMode.MARKDOWN
        )
    except ValidationError as e:
        update.message.reply_text(f"⚠️ Ошибка при создании заказа: {e}")
        return ConversationHandler.END
    reply_markup = ReplyKeyboardMarkup(
        [["Мой заказ", "Тарифы и условия хранения"], ["Заказать ячейку"]],
        resize_keyboard=True
    )
    update.message.reply_text(
        "Если вас интересует что-то еще, выберите действие из меню ниже:",
        reply_markup=reply_markup
    )
    return ConversationHandler.END


def main_menu(update, context):
    reply_markup = ReplyKeyboardMarkup(
        [["Мой заказ", "Тарифы и условия хранения"], ["Заказать ячейку"]],
        resize_keyboard=True
    )
    update.message.reply_text(
        "Добро пожаловать в меню! Выберите действие:",
        reply_markup=reply_markup
    )
    return MAIN_MENU


from telegram import ParseMode

def handle_my_order(update: Update, context: CallbackContext):

    telegram_user_id = update.message.chat_id
    try:
        user = User.objects.get(user_id=telegram_user_id)
        orders = user.get_orders()

        if not orders.exists() or not any(order.status != 'completed' for order in orders):
            update.message.reply_text(
                "📦 У вас пока нет активных заказов.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        orders_info = "📋 *Ваши заказы:*\n\n"
        for order in orders:
            if order.status != 'completed':
                status_emoji = {
                    'pending': "⏳",
                    'active': "✅",
                    'expired': "⚠️",
                    'completed': "✔️"
                }.get(order.status, "❓")

                end_date = order.start_date + timedelta(days=order.storage_duration)
                days_left = (end_date - now()).days

                # Формируем информацию о заказе
                orders_info += (
                    f"{status_emoji} *Заказ {order.order_id}:*\n"
                    f"- Ячейка: {order.storage_unit.get_size_display()}\n"
                    f"- Склад: {order.storage_unit.warehouse.name}\n"
                    f"- Адрес склада: {order.storage_unit.warehouse.warehouse_address or 'Адрес не указан'}\n"
                    f"- Срок хранения: {order.storage_duration} дней\n"
                    f"- Осталось дней: {days_left if days_left > 0 else 'Истёк'}\n"
                    f"- Статус: {order.get_status_display()}\n"
                    f"- Дата начала аренды: {order.start_date.strftime('%d.%m.%Y')}\n"
                    f"- Общая стоимость: {order.calculated_total_cost} руб.\n\n"
                )

                keyboard = [
                    [InlineKeyboardButton("🔑 Забрать заказ", callback_data=f"pickup_order_{order.order_id}")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                update.message.reply_text(
                    orders_info,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
    except User.DoesNotExist:(
        update.message.reply_text(
            "❌ Учетная запись не найдена. Возможно, вы ещё не зарегистрировались.",
            parse_mode=ParseMode.MARKDOWN
        ))


def handle_pickup_order(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    # Извлекаем ID заказа из callback_data
    order_id = query.data.split('_')[-1]

    try:
        order = Order.objects.get(order_id=order_id)

        # Логируем текущий статус заказа
        print(f"[DEBUG] Заказ найден: ID={order.order_id}, Статус={order.status}")

        if order.status == 'completed':
            query.message.reply_text("❌ Этот заказ уже завершен!")
            return

        # Генерируем данные для QR-кода
        qr_data = f"Order ID: {order_id}, User: {order.user.name}, Storage Unit: {order.storage_unit.unit_id}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        # Сохраняем QR-код в буфер
        qr_image = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        qr_image.save(buffer, format="PNG")
        buffer.seek(0)

        # Отправляем QR-код пользователю
        query.message.reply_photo(photo=InputFile(buffer, filename=f"order_{order_id}_qr.png"),
                                  caption="🔑 Вот ваш QR-код для открытия ячейки.")

        # Меняем статус заказа на "completed"
        order.status = 'completed'
        order.save()  # Сохраняем изменения
        print(f"[DEBUG] Статус заказа обновлен: ID={order.order_id}, Новый статус={order.status}")

        # Освобождаем ячейку
        order.release_storage_unit()
        print("[DEBUG] Метод release_storage_unit выполнен успешно.")

    except Order.DoesNotExist:
        query.message.reply_text("❌ Заказ не найден. Возможно, он уже был завершен.")
    except ValidationError as e:
        query.message.reply_text(f"⚠️ Ошибка валидации: {e}")
        print(f"[ERROR] Ошибка валидации: {e}")
    except Exception as e:
        query.message.reply_text("❌ Произошла ошибка при обработке заказа.")
        print(f"[ERROR] Непредвиденная ошибка: {e}")



def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Вы завершили взаимодействие с ботом. До свидания!")
    return ConversationHandler.END


# Регистрация CallbackQueryHandler для обработки инлайн-кнопок
def main():
    env = Env()
    env.read_env()

    token = env.str('TG_BOT_TOKEN')
    bot = telegram.Bot(token=token)

    updater = Updater(token)
    dispatcher = updater.dispatcher

    start_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CONSENT: [
                MessageHandler(Filters.regex("^(Принять|Отказаться)$"), handle_consent),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    main_menu_handler = ConversationHandler(
        entry_points=[
            CommandHandler("main_menu", main_menu),  # Вход в главное меню через эту команду
            MessageHandler(Filters.regex("^Меню$"), main_menu),
            MessageHandler(Filters.regex("^Мой заказ$"), handle_my_order),
            MessageHandler(Filters.regex("^Тарифы и условия хранения$"), tariffs),
            MessageHandler(Filters.regex("^Заказать ячейку$"), order_box),
        ],
        states={
            MAIN_MENU: [
                MessageHandler(Filters.regex("^Мой заказ$"), handle_my_order),
                MessageHandler(Filters.regex("^Тарифы и условия хранения$"), tariffs),
                MessageHandler(Filters.regex("^Заказать ячейку$"), order_box),
                MessageHandler(
                    Filters.text & ~Filters.command,
                    lambda update, context: update.message.reply_text("Выберите пункт из меню!")
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    order_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_order_form, pattern="^continue_order$"),
            CallbackQueryHandler(start_order_form_self_delivery, pattern="^continue_order_self_delivery$")
        ],
        states={
            REQUEST_NAME: [
                MessageHandler(Filters.text & ~Filters.command, request_name),
            ],
            REQUEST_PHONE: [
                MessageHandler(Filters.text & ~Filters.command, request_phone),
            ],
            REQUEST_START_DATE: [
                MessageHandler(Filters.text & ~Filters.command, request_start_date),
            ],
            REQUEST_DURATION: [
                MessageHandler(Filters.text & ~Filters.command, request_duration),
                #MessageHandler(Filters.text & ~Filters.command, request_duration_self_delivery),
            ],
            REQUEST_ADDRESS: [
                #MessageHandler(Filters.text & ~Filters.command, finalize_order_self),
                MessageHandler(Filters.text & ~Filters.command, finalize_order_courier),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dispatcher.add_handler(start_conv_handler)  # Стартовый ConversationHandler
    dispatcher.add_handler(order_conv_handler) # Отдельный ConversationHandler для оформления заказа
    dispatcher.add_handler(main_menu_handler)
    dispatcher.add_handler(CallbackQueryHandler(handle_courier_delivery, pattern="^deliver_courier$"))
    dispatcher.add_handler(CallbackQueryHandler(handle_self_delivery, pattern="^self_delivery$"))
    dispatcher.add_handler(CallbackQueryHandler(start_order_form, pattern="^continue_order$"))
    dispatcher.add_handler(CallbackQueryHandler(handle_pickup_order, pattern=r'^pickup_order_\d+$'))

    # Запуск бота
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()

