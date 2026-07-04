import os
import shutil
import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func, update
from app.database.session import async_session, async_engine
from app.models.models import User, Subscription, Payment, Signal, Settings, Plan
from app.core.config import settings
from app.bot.bot_service import bot
from app.core.logging import bot_logger

admin_router = Router()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_plan_price = State()

# Middleware role check helper
async def is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_TELEGRAM_ID

def get_admin_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📊 الإحصائيات المالية", callback_data="admin_stats"),
            InlineKeyboardButton(text="📢 إرسال رسالة جماعية (Broadcast)", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton(text="🛠️ إدارة الخطط", callback_data="admin_plans"),
            InlineKeyboardButton(text="💾 النسخ الاحتياطي & الاستعادة", callback_data="admin_backup")
        ],
        [
            InlineKeyboardButton(text="📜 عرض السجلات", callback_data="admin_logs"),
            InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@admin_router.callback_query(F.data == "menu_admin")
async def show_admin_dashboard(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ غير مصرح لك بالدخول إلى لوحة التحكم هذه.")
        return
        
    async with async_session() as db:
        # User counts
        users_count_res = await db.execute(select(func.count(User.id)))
        users_count = users_count_res.scalar() or 0
        
        # Subscribed users
        subs_count_res = await db.execute(select(func.count(Subscription.id)).filter_by(status="active"))
        subs_count = subs_count_res.scalar() or 0
        
        # Signal count
        signals_count_res = await db.execute(select(func.count(Signal.id)))
        signals_count = signals_count_res.scalar() or 0

    text = (
        f"👑 <b>لوحة الإدارة الرئيسية - MBM Radar</b>\n\n"
        f"• إجمالي المستخدمين المسجلين: <b>{users_count} مستخدم</b>\n"
        f"• المشتركين النشطين بالقناة: <b>{subs_count} مشترك</b>\n"
        f"• إجمالي التنبيهات المرسلة: <b>{signals_count} تنبيه</b>\n"
    )
    
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_stats")
async def show_financial_stats(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id): return

    async with async_session() as db:
        # Total revenue
        rev_res = await db.execute(select(func.sum(Payment.amount)).filter_by(status="completed"))
        revenue = rev_res.scalar() or 0.0
        
        # Breakdown by payment provider
        stripe_rev_res = await db.execute(select(func.sum(Payment.amount)).filter_by(status="completed", provider="stripe"))
        stripe_rev = stripe_rev_res.scalar() or 0.0
        
        manual_rev_res = await db.execute(select(func.sum(Payment.amount)).filter_by(status="completed", provider="manual_bot"))
        manual_rev = manual_rev_res.scalar() or 0.0

    text = (
        f"📊 <b>الإحصائيات المالية والتقارير:</b>\n\n"
        f"• إجمالي الأرباح والإيرادات: <b>${revenue:.2f}</b>\n"
        f"• المدفوعات عبر Stripe: <b>${stripe_rev:.2f}</b>\n"
        f"• المدفوعات اليدوية بالبوت: <b>${manual_rev:.2f}</b>\n\n"
        f"يتم تحديث التقارير المالية بشكل لحظي عند كل عملية شراء."
    )
    
    buttons = [[InlineKeyboardButton(text="🔙 العودة للوحة الإدارة", callback_data="menu_admin")]]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

# --- Broadcast Section ---
@admin_router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.answer("📣 يرجى إدخال نص الرسالة المراد إرسالها لجميع المشتركين والمستخدمين:")
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    
    msg_text = message.text
    async with async_session() as db:
        res = await db.execute(select(User.telegram_id))
        user_ids = res.scalars().all()

    success_count = 0
    fail_count = 0
    
    await message.answer(f"⏳ بدء إرسال الرسالة إلى {len(user_ids)} مستخدم...")
    
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=f"📢 <b>رسالة جماعية من إدارة MBM Radar:</b>\n\n{msg_text}", parse_mode="HTML")
            success_count += 1
            await asyncio.sleep(0.05)  # Telegram API flood control limit
        except Exception:
            fail_count += 1
            
    await message.answer(f"✅ انتهى الإرسال!\n• تم إرسالها بنجاح: {success_count}\n• فشلت: {fail_count}")
    await state.clear()

# --- Backup & Restore Section ---
@admin_router.callback_query(F.data == "admin_backup")
async def database_backup_manager(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    
    # Check if database file is SQLite (for backup convenience)
    db_url = settings.DATABASE_URL
    
    if "sqlite" in db_url:
        db_path = db_url.split("///")[-1]
        backup_path = f"{db_path}.backup"
        try:
            shutil.copy(db_path, backup_path)
            # Send file to admin
            file_to_send = FSInputFile(backup_path)
            await bot.send_document(chat_id=callback.from_user.id, document=file_to_send, caption=f"💾 نسخة احتياطية لقاعدة البيانات SQLite: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
            await callback.answer("✅ تم إرسال النسخة الاحتياطية بنجاح.")
        except Exception as err:
            await callback.message.answer(f"❌ فشل إنشاء النسخة الاحتياطية لـ SQLite: {str(err)}")
    else:
        # Non-sqlite Postgres databases backup
        await callback.message.answer("ℹ️ نظام قاعدة البيانات النشط هو PostgreSQL. يتم حفظ النسخ الاحتياطية تلقائياً عبر Docker volumes.")
        await callback.answer()

# --- Plans Management ---
@admin_router.callback_query(F.data == "admin_plans")
async def list_admin_plans(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    
    async with async_session() as db:
        res = await db.execute(select(Plan))
        plans = res.scalars().all()
        
    text = "🛠️ <b>إدارة باقات الاشتراك والأسعار:</b>\n\n"
    buttons = []
    
    for plan in plans:
        text += f"• باقة: <b>{plan.name}</b> | المدة: {plan.duration_days} يوم | السعر: <b>${plan.price:.2f}</b>\n"
        buttons.append([InlineKeyboardButton(text=f"⚙️ تعديل سعر {plan.name}", callback_data=f"edit_plan_price_{plan.id}")])
        
    buttons.append([InlineKeyboardButton(text="🔙 العودة للوحة الإدارة", callback_data="menu_admin")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("edit_plan_price_"))
async def start_plan_price_edit(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    plan_id = int(callback.data.split("_")[-1])
    
    await state.update_data(edit_plan_id=plan_id)
    await state.set_state(AdminStates.waiting_for_plan_price)
    
    await callback.message.answer("💵 يرجى إدخال السعر الجديد للباقة (مثال: 34.99):")
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_plan_price)
async def process_new_plan_price(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return
    
    try:
        new_price = float(message.text)
        if new_price <= 0: raise ValueError
        
        data = await state.get_data()
        plan_id = data.get("edit_plan_id")
        
        async with async_session() as db:
            await db.execute(update(Plan).filter_by(id=plan_id).values(price=new_price))
            await db.commit()
            
        await message.answer("✅ تم تحديث سعر الباقة بنجاح.")
        await state.clear()
    except ValueError:
        await message.answer("❌ يرجى إدخال سعر صحيح (رقم عشري أكبر من صفر):")

# --- Logs Review ---
@admin_router.callback_query(F.data == "admin_logs")
async def view_recent_logs(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    
    # Read last 30 lines of scanner and bot logs
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "logs")
    log_file = os.path.join(log_dir, "app.log")
    
    text = "📜 <b>آخر السجلات والنشاطات بالنظام:</b>\n\n"
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                recent_lines = lines[-20:]
                text += "<pre>" + "".join(recent_lines) + "</pre>"
        except Exception as e:
            text += f"تعذر قراءة ملف السجلات: {str(e)}"
    else:
        text += "ملف السجلات غير متوفر حالياً."
        
    buttons = [[InlineKeyboardButton(text="🔙 العودة للوحة الإدارة", callback_data="menu_admin")]]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()
