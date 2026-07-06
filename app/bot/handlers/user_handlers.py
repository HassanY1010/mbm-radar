import datetime
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatInviteLink
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, update
from app.database.session import async_session
from app.models.models import User, UserPreferences, Subscription, Plan, Watchlist, Payment
from app.core.config import settings
from app.bot.bot_service import bot
from app.core.logging import bot_logger

user_router = Router()

class FilterStates(StatesGroup):
    waiting_for_max_price = State()
    waiting_for_max_float = State()
    waiting_for_min_rvol = State()
    waiting_for_min_gap = State()
    waiting_for_min_volume = State()
    waiting_for_support_msg = State()
    waiting_for_min_score = State()

def get_main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🔍 تعديل الفلاتر", callback_data="menu_filters"),
            InlineKeyboardButton(text="💳 اشتراكي", callback_data="menu_sub")
        ],
        [
            InlineKeyboardButton(text="📊 قائمة المراقبة", callback_data="menu_watchlist"),
            InlineKeyboardButton(text="📞 الدعم الفني", callback_data="menu_support")
        ],
        [
            InlineKeyboardButton(text="⚙️ إعادة الضبط", callback_data="menu_reset")
        ]
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="👑 لوحة الإدارة", callback_data="menu_admin")])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@user_router.message(CommandStart())
async def start_cmd(message: Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    async with async_session() as db:
        # Check if user exists
        res = await db.execute(select(User).filter_by(telegram_id=tg_id))
        user = res.scalar_one_or_none()
        
        is_admin_id = (tg_id == settings.ADMIN_TELEGRAM_ID)
        
        if not user:
            user = User(
                telegram_id=tg_id,
                username=username,
                first_name=first_name,
                is_admin=is_admin_id
            )
            db.add(user)
            await db.flush()
            
            # Create default preferences
            preferences = UserPreferences(
                user_id=user.id,
                max_price=settings.SCANNER_MAX_PRICE,
                max_float=settings.SCANNER_MAX_FLOAT,
                max_market_cap=settings.SCANNER_MAX_MARKET_CAP,
                min_rvol=settings.SCANNER_MIN_RVOL,
                min_volume=settings.SCANNER_MIN_VOLUME,
                min_gap_pct=settings.SCANNER_MIN_GAP_PCT,
                min_change_pct=settings.SCANNER_MIN_CHANGE_PCT,
                min_score_threshold=settings.MIN_SCORE_THRESHOLD
            )
            db.add(preferences)
            await db.commit()
            bot_logger.info(f"Registered new user {tg_id}")
        else:
            # Sync admin status if changed in config
            if is_admin_id and not user.is_admin:
                user.is_admin = True
                await db.commit()

        is_admin = user.is_admin

    welcome_text = (
        f"👋 مرحباً بك {first_name} في <b>MBM Radar</b>!\n\n"
        f"نظام رصد الأسهم الأمريكية المضاربية الشرعية اللحظي.\n"
        f"يقوم النظام بفحص السوق واكتشاف الأسهم التي تتحرك بقوة، وتصفيتها شرعياً وفنياً قبل إرسال التنبيهات.\n\n"
        f"استخدم الأزرار أدناه للتحكم بحسابك وفلاترك:"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(is_admin), parse_mode="HTML")

@user_router.message(Command("exit", "cancel"))
async def exit_handler(message: Message, state: FSMContext):
    """Exit command to cancel any current action, clear state, and return to the main menu"""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        
    tg_id = message.from_user.id
    async with async_session() as db:
        res = await db.execute(select(User).filter_by(telegram_id=tg_id))
        user = res.scalar_one_or_none()
        is_admin = user.is_admin if user else False

    welcome_text = (
        f"👋 تم إلغاء العملية والعودة للقائمة الرئيسية بنجاح!\n\n"
        f"القائمة الرئيسية لـ <b>MBM Radar</b>:"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(is_admin), parse_mode="HTML")

@user_router.message(F.text.lower().in_({"exit", "cancel", "خروج", "الغاء", "إلغاء"}))
async def text_exit_handler(message: Message, state: FSMContext):
    """Fallback text handler to cancel actions when user writes cancel keywords"""
    await exit_handler(message, state)

@user_router.callback_query(F.data == "menu_main")
async def back_to_main(callback: CallbackQuery):
    async with async_session() as db:
        res = await db.execute(select(User).filter_by(telegram_id=callback.from_user.id))
        user = res.scalar_one_or_none()
        is_admin = user.is_admin if user else False
        
    await callback.message.edit_text(
        "القائمة الرئيسية لـ MBM Radar:",
        reply_markup=get_main_keyboard(is_admin)
    )
    await callback.answer()

# --- Filters Section ---
@user_router.callback_query(F.data == "menu_filters")
async def show_filters(callback: CallbackQuery):
    async with async_session() as db:
        query = select(UserPreferences).join(User).where(User.telegram_id == callback.from_user.id)
        res = await db.execute(query)
        pref = res.scalar_one_or_none()
        
    if not pref:
        await callback.answer("خطأ: لم يتم العثور على الإعدادات.")
        return
        
    status_alerts = "✅ مفعلة" if pref.alerts_enabled else "❌ معطلة"
    status_shariah = "✅ شرعي فقط" if pref.is_shariah_only else "⚠️ الكل (غير مستحسن)"
    # Volume operator representation
    vol_op = getattr(pref, "volume_filter_type", ">=")
    vol_op_text = "📈 أكبر من أو يساوي (≥)" if vol_op == ">=" else "📉 أقل من أو يساوي (≤)"
    min_score_val = getattr(pref, "min_score_threshold", 3.5)
    
    text = (
        f"🔍 <b>إعدادات الفلاتر والتنبيهات الخاصة بك:</b>\n\n"
        f"• حالة التنبيهات: {status_alerts}\n"
        f"• تصفية الأسهم الشرعية: {status_shariah}\n"
        f"• الحد الأقصى للسعر: <b>${pref.max_price:.2f}</b>\n"
        f"• الحد الأقصى للأسهم الحرة (Float): <b>{pref.max_float:,.0f}</b>\n"
        f"• الحد الأدنى للحجم النسبي (RVOL): <b>{pref.min_rvol:.2f}x</b>\n"
        f"• الحد الأدنى للفجوة (Gap%): <b>{pref.min_gap_pct:.2f}%</b>\n"
        f"• جودة الفرصة الأدنى: <b>{min_score_val:.1f}/10</b>\n\n"
        f"📦 <b>فلتر حجم التداول (Volume):</b>\n"
        f"• النوع: <b>{vol_op_text}</b>\n"
        f"• القيمة: <b>{pref.min_volume:,}</b>\n\n"
        f"اختر الفلتر الذي ترغب في تعديله أدناه:"
    )
    
    buttons = [
        [
            InlineKeyboardButton(text="🔔 تشغيل/إيقاف التنبيهات", callback_data="toggle_alerts"),
            InlineKeyboardButton(text="🕋 تصفية الشرعي", callback_data="toggle_shariah")
        ],
        [
            InlineKeyboardButton(text="💵 السعر الأقصى", callback_data="edit_price"),
            InlineKeyboardButton(text="🏊‍♂️ الـ Float الأقصى", callback_data="edit_float")
        ],
        [
            InlineKeyboardButton(text="📊 RVOL الأدنى", callback_data="edit_rvol"),
            InlineKeyboardButton(text="📈 الفجوة الأدنى Gap%", callback_data="edit_gap")
        ],
        [
            InlineKeyboardButton(text="🔄 اتجاه الـ Volume", callback_data="toggle_volume_op"),
            InlineKeyboardButton(text="📦 قيمة الـ Volume", callback_data="edit_volume")
        ],
        [
            InlineKeyboardButton(text="⭐ جودة الفرصة الأدنى", callback_data="edit_score")
        ],
        [
            InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="menu_main")
        ]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

@user_router.callback_query(F.data == "toggle_alerts")
async def toggle_alerts_handler(callback: CallbackQuery):
    async with async_session() as db:
        query = select(UserPreferences).join(User).where(User.telegram_id == callback.from_user.id)
        res = await db.execute(query)
        pref = res.scalar_one_or_none()
        if pref:
            pref.alerts_enabled = not pref.alerts_enabled
            await db.commit()
            
    await show_filters(callback)

@user_router.callback_query(F.data == "toggle_shariah")
async def toggle_shariah_handler(callback: CallbackQuery):
    async with async_session() as db:
        query = select(UserPreferences).join(User).where(User.telegram_id == callback.from_user.id)
        res = await db.execute(query)
        pref = res.scalar_one_or_none()
        if pref:
            pref.is_shariah_only = not pref.is_shariah_only
            await db.commit()
            
    await show_filters(callback)

@user_router.callback_query(F.data == "edit_price")
async def edit_price_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FilterStates.waiting_for_max_price)
    await callback.message.answer("يرجى إرسال الحد الأقصى لسعر السهم (مثال: 15.5):")
    await callback.answer()

@user_router.message(FilterStates.waiting_for_max_price)
async def process_price_input(message: Message, state: FSMContext):
    try:
        val = float(message.text)
        if val <= 0:
            raise ValueError()
            
        async with async_session() as db:
            query = select(UserPreferences).join(User).where(User.telegram_id == message.from_user.id)
            res = await db.execute(query)
            pref = res.scalar_one_or_none()
            if pref:
                pref.max_price = val
                await db.commit()
                
        await message.answer(f"✅ تم تحديث السعر الأقصى إلى: ${val:.2f}")
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال قيمة عددية صحيحة أكبر من صفر:")

@user_router.callback_query(F.data == "edit_float")
async def edit_float_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FilterStates.waiting_for_max_float)
    await callback.message.answer("يرجى إرسال الحد الأقصى للأسهم الحرة Float (مثال: 20000000):")
    await callback.answer()

@user_router.message(FilterStates.waiting_for_max_float)
async def process_float_input(message: Message, state: FSMContext):
    try:
        val = float(message.text)
        if val <= 0:
            raise ValueError()
            
        async with async_session() as db:
            query = select(UserPreferences).join(User).where(User.telegram_id == message.from_user.id)
            res = await db.execute(query)
            pref = res.scalar_one_or_none()
            if pref:
                pref.max_float = val
                await db.commit()
                
        await message.answer(f"✅ تم تحديث الـ Float الأقصى إلى: {val:,.0f}")
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال قيمة عددية صحيحة:")

@user_router.callback_query(F.data == "edit_rvol")
async def edit_rvol_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FilterStates.waiting_for_min_rvol)
    await callback.message.answer("يرجى إرسال الحد الأدنى للحجم النسبي RVOL (مثال: 3.5):")
    await callback.answer()

@user_router.message(FilterStates.waiting_for_min_rvol)
async def process_rvol_input(message: Message, state: FSMContext):
    try:
        val = float(message.text)
        if val < 1:
            raise ValueError()
            
        async with async_session() as db:
            query = select(UserPreferences).join(User).where(User.telegram_id == message.from_user.id)
            res = await db.execute(query)
            pref = res.scalar_one_or_none()
            if pref:
                pref.min_rvol = val
                await db.commit()
                
        await message.answer(f"✅ تم تحديث الـ RVOL الأدنى إلى: {val:.2f}x")
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال قيمة عددية صحيحة لا تقل عن 1:")

@user_router.callback_query(F.data == "edit_gap")
async def edit_gap_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FilterStates.waiting_for_min_gap)
    await callback.message.answer("يرجى إرسال الحد الأدنى للفجوة Gap% (مثال: 2.0):")
    await callback.answer()

@user_router.message(FilterStates.waiting_for_min_gap)
async def process_gap_input(message: Message, state: FSMContext):
    try:
        val = float(message.text)
        if val < 0:
            raise ValueError()
            
        async with async_session() as db:
            query = select(UserPreferences).join(User).where(User.telegram_id == message.from_user.id)
            res = await db.execute(query)
            pref = res.scalar_one_or_none()
            if pref:
                pref.min_gap_pct = val
                await db.commit()
                
        await message.answer(f"✅ تم تحديث الفجوة الأدنى إلى: {val:.2f}%")
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال قيمة عددية صحيحة:")

@user_router.callback_query(F.data == "edit_score")
async def edit_score_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FilterStates.waiting_for_min_score)
    await callback.message.answer("يرجى إرسال الحد الأدنى لجودة الفرصة (مثال: 7.5):")
    await callback.answer()

@user_router.message(FilterStates.waiting_for_min_score)
async def process_score_input(message: Message, state: FSMContext):
    try:
        val = float(message.text)
        if val < 0.0 or val > 10.0:
            raise ValueError()
            
        async with async_session() as db:
            query = select(UserPreferences).join(User).where(User.telegram_id == message.from_user.id)
            res = await db.execute(query)
            pref = res.scalar_one_or_none()
            if pref:
                pref.min_score_threshold = val
                await db.commit()
                
        await message.answer(f"✅ تم تحديث الحد الأدنى لجودة الفرصة إلى: {val:.1f}/10")
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال قيمة عددية صحيحة بين 0.0 و 10.0:")

@user_router.callback_query(F.data == "toggle_volume_op")
async def toggle_volume_op_handler(callback: CallbackQuery):
    async with async_session() as db:
        query = select(UserPreferences).join(User).where(User.telegram_id == callback.from_user.id)
        res = await db.execute(query)
        pref = res.scalar_one_or_none()
        if pref:
            current_op = getattr(pref, "volume_filter_type", ">=")
            new_op = "<=" if current_op == ">=" else ">="
            pref.volume_filter_type = new_op
            await db.commit()
            
    await show_filters(callback)

@user_router.callback_query(F.data == "edit_volume")
async def edit_volume_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FilterStates.waiting_for_min_volume)
    await callback.message.answer("📦 يرجى إدخال قيمة الـ Volume الجديدة:\n\nمثال:\n500000\nأو\n1000000")
    await callback.answer()

@user_router.message(FilterStates.waiting_for_min_volume)
async def process_volume_input(message: Message, state: FSMContext):
    try:
        cleaned_text = message.text.replace(",", "").replace(".", "").strip()
        val = int(cleaned_text)
        if val <= 0:
            raise ValueError()
            
        async with async_session() as db:
            query = select(UserPreferences).join(User).where(User.telegram_id == message.from_user.id)
            res = await db.execute(query)
            pref = res.scalar_one_or_none()
            if pref:
                pref.min_volume = val
                await db.commit()
                
        await message.answer(f"✅ تم تحديث قيمة الـ Volume إلى: {val:,}")
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال قيمة عددية صحيحة أكبر من صفر:")

# --- Subscriptions Section ---
@user_router.callback_query(F.data == "menu_sub")
async def show_subscription(callback: CallbackQuery):
    async with async_session() as db:
        # Load user and active subscription
        query = select(User).where(User.telegram_id == callback.from_user.id)
        res = await db.execute(query)
        user = res.scalar_one_or_none()
        
        if not user:
            await callback.answer("مستخدم غير مسجل.")
            return
            
        sub_query = select(Subscription).filter_by(user_id=user.id, status="active")
        sub_res = await db.execute(sub_query)
        sub = sub_res.scalar_one_or_none()
        
        plans_res = await db.execute(select(Plan).filter_by(is_active=True))
        plans = plans_res.scalars().all()

    if sub:
        remaining_days = (sub.end_date - datetime.datetime.utcnow()).days
        remaining_days = max(remaining_days, 0)
        
        # Try generating channel link if subscribed
        invite_link_str = "بانتظار إنشاء الرابط..."
        try:
            invite = await bot.create_chat_invite_link(
                chat_id=settings.TELEGRAM_CHANNEL_ID,
                member_limit=1
            )
            invite_link_str = invite.invite_link
        except Exception as link_err:
            bot_logger.error(f"Failed to create invite link: {str(link_err)}")
            invite_link_str = "يجب إضافة البوت كـ Admin بالقناة أولاً مع صلاحية دعوة الأعضاء."

        text = (
            f"💳 <b>تفاصيل اشتراكك النشط:</b>\n\n"
            f"• الباقة: <b>{sub.plan.name}</b>\n"
            f"• تاريخ الانتهاء: <b>{sub.end_date.strftime('%Y-%m-%d')}</b>\n"
            f"• الأيام المتبقية: <b>{remaining_days} يوم</b>\n\n"
            f"🔗 <b>رابط الانضمام للقناة الخاصة:</b>\n"
            f"{invite_link_str}\n\n"
            f"<i>(ملاحظة: هذا الرابط صالح للاستخدام مرة واحدة ولمستخدم واحد فقط).</i>"
        )
        buttons = [[InlineKeyboardButton(text="🔙 العودة للقائمة", callback_data="menu_main")]]
    else:
        text = (
            f"💳 <b>أنت غير مشترك حالياً!</b>\n\n"
            f"للانضمام إلى قناة التنبيهات الخاصة بـ MBM Radar، وتلقي التنبيهات المباشرة، يرجى اختيار إحدى الخطط التالية للاشتراك:"
        )
        buttons = []
        for plan in plans:
            buttons.append([InlineKeyboardButton(
                text=f"🛒 {plan.name} - ${plan.price:.2f} ({plan.duration_days} يوم)",
                callback_data=f"buy_plan_{plan.id}"
            )])
        buttons.append([InlineKeyboardButton(text="🔙 العودة", callback_data="menu_main")])
        
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()

@user_router.callback_query(F.data.startswith("buy_plan_"))
async def simulate_payment(callback: CallbackQuery):
    plan_id = int(callback.data.split("_")[-1])
    
    async with async_session() as db:
        plan = await db.get(Plan, plan_id)
        user_res = await db.execute(select(User).filter_by(telegram_id=callback.from_user.id))
        user = user_res.scalar_one()

        if not plan:
            await callback.answer("الخطة غير متوفرة.")
            return

        # Use Payment Service factory
        from app.payments.payment_service import PaymentService
        processor = PaymentService.get_processor()
        
        # Create checkout session
        checkout_info = await processor.create_checkout_session(
            user_id=user.id,
            plan_id=plan.id,
            amount=plan.price
        )
        
        if checkout_info.get("status") == "completed":
            # Simulate Checkout and activate directly (for Mock provider)
            start = datetime.datetime.utcnow()
            end = start + datetime.timedelta(days=plan.duration_days)
            
            # Disable previous active subs if any
            await db.execute(
                update(Subscription)
                .filter_by(user_id=user.id, status="active")
                .values(status="expired")
            )
            
            sub = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status="active",
                start_date=start,
                end_date=end
            )
            db.add(sub)
            
            # Add payment record
            payment = Payment(
                user_id=user.id,
                amount=plan.price,
                status="completed",
                provider=settings.PAYMENT_PROVIDER,
                transaction_id=checkout_info.get("transaction_id")
            )
            db.add(payment)
            await db.commit()
            
            await callback.message.answer(f"🎉 تم تفعيل اشتراكك بنجاح في باقة {plan.name}! يرجى فتح تبويب اشتراكي للحصول على رابط القناة.")
        else:
            # If live payment gateway like Stripe is active, send checkout link
            checkout_url = checkout_info.get("checkout_url")
            await callback.message.answer(
                f"🛒 <b>طلب اشتراك في باقة {plan.name}:</b>\n\n"
                f"يرجى إتمام عملية الدفع بقيمة <b>${plan.price:.2f}</b> عبر الرابط التالي:\n"
                f"🔗 <a href='{checkout_url}'>اضغط هنا لفتح بوابة الدفع الآمنة</a>\n\n"
                f"<i>(ملاحظة: سيتم تفعيل حسابك تلقائياً وبشكل فوري فور إشعار السيرفر باكتمال الدفع).</i>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        
    await show_subscription(callback)

# --- Reset Settings Section ---
@user_router.callback_query(F.data == "menu_reset")
async def reset_settings(callback: CallbackQuery):
    async with async_session() as db:
        query = select(UserPreferences).join(User).where(User.telegram_id == callback.from_user.id)
        res = await db.execute(query)
        pref = res.scalar_one_or_none()
        if pref:
            pref.max_price = settings.SCANNER_MAX_PRICE
            pref.max_float = settings.SCANNER_MAX_FLOAT
            pref.min_rvol = settings.SCANNER_MIN_RVOL
            pref.min_gap_pct = settings.SCANNER_MIN_GAP_PCT
            pref.alerts_enabled = True
            pref.is_shariah_only = True
            await db.commit()
            
    await callback.answer("✅ تم إعادة ضبط إعدادات الفلاتر الافتراضية بنجاح.")
    await show_filters(callback)

# --- Watchlist Section ---
@user_router.callback_query(F.data == "menu_watchlist")
async def show_watchlist(callback: CallbackQuery):
    async with async_session() as db:
        user_res = await db.execute(select(User).filter_by(telegram_id=callback.from_user.id))
        user = user_res.scalar_one()
        
        wl_res = await db.execute(select(Watchlist).filter_by(user_id=user.id))
        watchlist_items = wl_res.scalars().all()
        
    text = "📊 <b>قائمة المراقبة الخاصة بك:</b>\n\n"
    if not watchlist_items:
        text += "قائمتك فارغة حالياً. يمكنك إضافة أسهم لمراقبتها مباشرة.\n"
    else:
        for item in watchlist_items:
            text += f"• <b>{item.ticker}</b> (أضيف في: {item.added_at.strftime('%Y-%m-%d')})\n"
            
    text += "\nلإضافة سهم: اكتب `/add TICKER`\nلإزالة سهم: اكتب `/remove TICKER`"
    
    buttons = [[InlineKeyboardButton(text="🔙 العودة للقائمة الرئيسية", callback_data="menu_main")]]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

@user_router.message(Command("add"))
async def add_to_watchlist(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ يرجى تحديد الرمز. مثال: `/add AAPL`", parse_mode="Markdown")
        return
        
    ticker = args[1].upper()
    async with async_session() as db:
        user_res = await db.execute(select(User).filter_by(telegram_id=message.from_user.id))
        user = user_res.scalar_one_or_none()
        if not user:
            return
            
        # Check if already in watchlist
        existing = await db.execute(select(Watchlist).filter_by(user_id=user.id, ticker=ticker))
        if existing.scalar_one_or_none():
            await message.answer(f"السهم {ticker} موجود بالفعل في قائمة المراقبة.")
            return
            
        db.add(Watchlist(user_id=user.id, ticker=ticker))
        await db.commit()
        
    await message.answer(f"✅ تم إضافة {ticker} بنجاح إلى قائمة المراقبة.")

@user_router.message(Command("remove"))
async def remove_from_watchlist(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ يرجى تحديد الرمز. مثال: `/remove AAPL`", parse_mode="Markdown")
        return
        
    ticker = args[1].upper()
    async with async_session() as db:
        user_res = await db.execute(select(User).filter_by(telegram_id=message.from_user.id))
        user = user_res.scalar_one_or_none()
        if not user:
            return
            
        wl_res = await db.execute(select(Watchlist).filter_by(user_id=user.id, ticker=ticker))
        item = wl_res.scalar_one_or_none()
        if not item:
            await message.answer(f"السهم {ticker} غير موجود في قائمة المراقبة الخاصة بك.")
            return
            
        await db.delete(item)
        await db.commit()
        
    await message.answer(f"✅ تم إزالة {ticker} بنجاح من قائمة المراقبة.")

# --- Technical Support Section ---
@user_router.callback_query(F.data == "menu_support")
async def technical_support(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FilterStates.waiting_for_support_msg)
    await callback.message.answer("💬 يرجى إرسال رسالتك أو استفسارك للدعم الفني (سيقوم أحد المسؤولين بالرد عليك قريباً):")
    await callback.answer()

@user_router.message(FilterStates.waiting_for_support_msg)
async def process_support_message(message: Message, state: FSMContext):
    msg_text = message.text
    # Forward this message to Admin telegram channel/chat
    try:
        await bot.send_message(
            chat_id=settings.ADMIN_TELEGRAM_ID,
            text=f"💬 <b>استفسار دعم فني جديد:</b>\n\n"
                 f"• من المستخدم: {message.from_user.first_name} (ID: {message.from_user.id})\n"
                 f"• الرسالة:\n{msg_text}",
            parse_mode="HTML"
        )
        await message.answer("✅ تم إرسال رسالتك إلى الدعم الفني بنجاح. شكراً لك!")
    except Exception as e:
        await message.answer("❌ تعذر إرسال الرسالة إلى المسؤولين في الوقت الحالي. يرجى المحاولة لاحقاً.")
        bot_logger.error(f"Support message forwarding failure: {str(e)}")
        
    await state.clear()
