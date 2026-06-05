"""SMM-агент: шаблоны контента, расписание, черновики в админ-канал, апрув в основной."""
import asyncio
import os
import random
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger

from bot.runtime import runtime
from config import ADMIN_TELEGRAM_ID, CHANNEL_URL
from database.settings_repo import get_setting, set_setting
from database.signals_repo import stats_aggregate, top_routes, top_symbols
from database.templates_repo import (
    create_post,
    create_template,
    delete_template,
    get_post_by_admin_msg,
    get_template,
    list_templates,
    toggle_template,
    update_post_status,
)


router = Router()


MSK_TZ = timezone(timedelta(hours=3))

DEFAULT_SCHEDULE = "10:00,15:00,20:00"


_pending_template_input: dict[int, dict] = {}  # admin_id -> {"step": "await_name" or "await_content", "name": ...}


def _is_admin(message_or_callback) -> bool:
    return message_or_callback.from_user.id == ADMIN_TELEGRAM_ID


def _waiting_template(message: Message) -> bool:
    return message.from_user and message.from_user.id in _pending_template_input


async def _get_admin_channel_id() -> str | None:
    return await get_setting("content_admin_channel_id")


async def _get_main_channel_id() -> str | None:
    return await get_setting("channel_id")


async def _get_schedule() -> list[str]:
    raw = await get_setting("content_schedule", DEFAULT_SCHEDULE) or DEFAULT_SCHEDULE
    slots: list[str] = []
    for s in raw.split(","):
        s = s.strip()
        if s and ":" in s:
            slots.append(s)
    return sorted(set(slots))


async def _get_last_slot() -> str:
    return await get_setting("content_last_slot", "") or ""


async def _set_last_slot(slot_iso: str) -> None:
    await set_setting("content_last_slot", slot_iso)


# ----------------- Variable substitution -----------------

async def _build_variables() -> dict[str, str]:
    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    agg = await stats_aggregate(since)
    pairs = await top_symbols(since, limit=1)
    routes = await top_routes(since, limit=1)

    top_pair = pairs[0][0] if pairs else "—"
    top_route = (
        f"{routes[0][0]} → {routes[0][1]}" if routes else "—"
    )
    bot_un = runtime.bot_username or "your_bot"
    return {
        "SIGNALS_24H": str(agg["total"]),
        "UNIQUE_PAIRS_24H": str(agg["unique_symbols"]),
        "MAX_SPREAD": f"{agg['max_profit']:.2f}%",
        "AVG_SPREAD": f"{agg['avg_profit']:.2f}%",
        "TOP_PAIR": top_pair,
        "TOP_ROUTE": top_route,
        "BOT_LINK": f"https://t.me/{bot_un}",
        "CHANNEL_LINK": CHANNEL_URL,
        "DATE": datetime.now(MSK_TZ).strftime("%d.%m.%Y"),
        "TIME": datetime.now(MSK_TZ).strftime("%H:%M"),
    }


def _render(text: str, vars_: dict[str, str]) -> str:
    rendered = text
    for k, v in vars_.items():
        rendered = rendered.replace("{" + k + "}", v)
    return rendered


# ----------------- AI rewrite (опционально) -----------------

async def _maybe_ai_rewrite(text: str) -> str:
    """Если задан OPENAI_API_KEY и content_ai_enabled=true — переформулирует через GPT.
    Иначе возвращает текст как есть.
    """
    if (await get_setting("content_ai_enabled", "false") or "").lower() != "true":
        return text
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return text
    try:
        import aiohttp
        prompt = (
            "Перепиши пост для Telegram-канала о криптоарбитраже. "
            "Сохрани все цифры, ссылки и эмодзи. Сделай текст живым, лаконичным, без воды. "
            "Не добавляй вступительных фраз. Верни только финальный текст без кавычек.\n\n"
            f"Исходник:\n{text}"
        )
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 800,
                },
                timeout=30,
            ) as r:
                data = await r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"AI rewrite failed: {e}")
        return text


# ----------------- Scheduler loop -----------------

def _draft_keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Опубликовать", callback_data=f"cnt_pub:{post_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"cnt_rej:{post_id}"),
        ],
    ])


async def _post_draft(bot: Bot, template, slot_iso: str) -> None:
    admin_chat = await _get_admin_channel_id()
    if not admin_chat:
        logger.warning("content scheduler: admin channel not set")
        return
    vars_ = await _build_variables()
    rendered = _render(template.text, vars_)
    rendered = await _maybe_ai_rewrite(rendered)

    header = f"📝 <b>Черновик</b> · {slot_iso}\nШаблон: <code>{template.name}</code>\n\n"
    full_text = header + rendered
    try:
        if template.photo_file_id:
            sent = await bot.send_photo(
                chat_id=admin_chat,
                photo=template.photo_file_id,
                caption=full_text[:1024],
            )
        else:
            sent = await bot.send_message(
                chat_id=admin_chat,
                text=full_text,
                disable_web_page_preview=True,
            )
    except Exception as e:
        logger.warning(f"draft post failed: {e}")
        return
    post = await create_post(
        template_id=template.id,
        admin_chat_id=sent.chat.id,
        admin_message_id=sent.message_id,
        rendered_text=rendered,
        scheduled_slot=slot_iso,
    )
    try:
        await bot.edit_message_reply_markup(
            chat_id=sent.chat.id,
            message_id=sent.message_id,
            reply_markup=_draft_keyboard(post.id),
        )
    except Exception as e:
        logger.warning(f"set draft kb failed: {e}")


async def content_scheduler_loop(bot: Bot) -> None:
    logger.info("Фоновый цикл SMM-агента запущен")
    while True:
        try:
            schedule = await _get_schedule()
            if not schedule:
                await asyncio.sleep(60)
                continue
            now_msk = datetime.now(MSK_TZ).replace(second=0, microsecond=0)
            last_iso = await _get_last_slot()

            for slot in schedule:
                hh, mm = slot.split(":")
                target = now_msk.replace(hour=int(hh), minute=int(mm))
                slot_iso = target.strftime("%Y-%m-%dT%H:%M")
                if now_msk >= target and slot_iso > last_iso:
                    templates = await list_templates(only_enabled=True)
                    if not templates:
                        logger.info(f"slot {slot_iso} fired, but no enabled templates")
                        await _set_last_slot(slot_iso)
                        break
                    tmpl = random.choice(templates)
                    await _post_draft(bot, tmpl, slot_iso)
                    await _set_last_slot(slot_iso)
                    break
        except Exception as e:
            logger.exception(f"content scheduler error: {e}")
        await asyncio.sleep(60)


# ----------------- Approve / Reject callbacks -----------------

@router.callback_query(F.data.startswith("cnt_pub:"))
async def cb_publish(callback: CallbackQuery, bot: Bot) -> None:
    if not _is_admin(callback):
        await callback.answer()
        return
    post_id = int(callback.data.split(":", 1)[1])
    main_chat = await _get_main_channel_id()
    if not main_chat:
        await callback.answer("Основной канал не задан")
        await callback.message.reply(
            "❌ Сначала задай основной канал: <code>/channel set @your_channel</code>"
        )
        return
    try:
        await bot.copy_message(
            chat_id=main_chat,
            from_chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
    except Exception as e:
        logger.warning(f"content publish failed: {e}")
        await callback.answer("Ошибка")
        await callback.message.reply(f"❌ Не удалось опубликовать: {e}")
        return
    await update_post_status(post_id, "published")
    await callback.answer("Опубликовано")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        ts = datetime.now(MSK_TZ).strftime("%H:%M МСК")
        await callback.message.reply(f"✅ Опубликовано в канал в {ts}")
    except Exception:
        pass


@router.callback_query(F.data.startswith("cnt_rej:"))
async def cb_reject(callback: CallbackQuery) -> None:
    if not _is_admin(callback):
        await callback.answer()
        return
    post_id = int(callback.data.split(":", 1)[1])
    await update_post_status(post_id, "rejected")
    await callback.answer("Отклонено")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply("❌ Черновик отклонён.")
    except Exception:
        pass


# ----------------- Admin commands -----------------

@router.message(Command("cancel"))
async def cmd_cancel_template(message: Message) -> None:
    if _pending_template_input.pop(message.from_user.id, None):
        await message.answer("❌ Создание шаблона отменено.")


@router.message(_waiting_template)
async def handle_template_input(message: Message) -> None:
    user_id = message.from_user.id
    state = _pending_template_input.get(user_id, {})
    step = state.get("step")
    if step == "await_name":
        name = (message.text or "").strip()
        if not name or len(name) > 60:
            await message.answer("❌ Имя пустое или слишком длинное. Попробуй ещё раз.")
            return
        _pending_template_input[user_id] = {"step": "await_content", "name": name}
        await message.answer(
            f"Имя сохранено: <b>{name}</b>\n\n"
            f"Теперь отправь сам шаблон одним сообщением. Можно с фото.\n"
            f"Доступные плейсхолдеры:\n"
            f"<code>{{SIGNALS_24H}}</code> <code>{{UNIQUE_PAIRS_24H}}</code> "
            f"<code>{{MAX_SPREAD}}</code> <code>{{AVG_SPREAD}}</code>\n"
            f"<code>{{TOP_PAIR}}</code> <code>{{TOP_ROUTE}}</code>\n"
            f"<code>{{BOT_LINK}}</code> <code>{{CHANNEL_LINK}}</code> "
            f"<code>{{DATE}}</code> <code>{{TIME}}</code>"
        )
        return
    if step == "await_content":
        name = state.get("name", "untitled")
        text = message.caption or message.text or ""
        photo_id = message.photo[-1].file_id if message.photo else None
        if not text and not photo_id:
            await message.answer("❌ Пусто. Пришли текст или фото с подписью.")
            return
        tmpl = await create_template(name, text, photo_id)
        _pending_template_input.pop(user_id, None)
        await message.answer(
            f"✅ Шаблон <code>#{tmpl.id}</code> «{tmpl.name}» сохранён."
        )


@router.message(Command("content"))
async def cmd_content(message: Message) -> None:
    if not _is_admin(message):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        admin_ch = await _get_admin_channel_id() or "не задан"
        main_ch = await _get_main_channel_id() or "не задан"
        schedule = ", ".join(await _get_schedule())
        ai_on = (await get_setting("content_ai_enabled", "false") or "false").lower() == "true"
        await message.answer(
            f"<b>🤖 SMM-агент</b>\n\n"
            f"Админ-канал: <code>{admin_ch}</code>\n"
            f"Основной канал: <code>{main_ch}</code>\n"
            f"Расписание (МСК): <b>{schedule}</b>\n"
            f"AI-рерайт: {'✅ вкл' if ai_on else '❌ выкл'}\n\n"
            f"<b>Команды:</b>\n"
            f"<code>/content add</code> — добавить шаблон\n"
            f"<code>/content list</code> — все шаблоны\n"
            f"<code>/content del N</code> — удалить шаблон #N\n"
            f"<code>/content toggle N</code> — вкл/выкл шаблон #N\n"
            f"<code>/content preview N</code> — превью с подставленными данными\n"
            f"<code>/content set_admin -1001234567890</code> — задать админ-канал\n"
            f"<code>/content schedule 10:00,15:00,20:00</code> — задать времена (МСК)\n"
            f"<code>/content ai on</code> / <code>off</code> — AI-рерайт (нужен OPENAI_API_KEY в .env)\n"
            f"<code>/content vars</code> — список плейсхолдеров"
        )
        return

    sub = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if sub == "add":
        _pending_template_input[message.from_user.id] = {"step": "await_name"}
        await message.answer(
            "📝 Создание шаблона.\n\n"
            "Шаг 1/2: напиши короткое имя шаблона (для твоего удобства).\n"
            "Для отмены — /cancel"
        )
    elif sub == "list":
        ts = await list_templates()
        if not ts:
            await message.answer("Шаблонов пока нет.")
            return
        lines = ["<b>Шаблоны:</b>"]
        for t in ts:
            flag = "✅" if t.enabled else "⏸"
            has_photo = " 🖼" if t.photo_file_id else ""
            preview = (t.text[:60] + "...") if len(t.text) > 60 else t.text
            lines.append(f"{flag} #{t.id} «{t.name}»{has_photo}\n  <i>{preview}</i>")
        await message.answer("\n".join(lines))
    elif sub == "del":
        try:
            tid = int(arg)
        except ValueError:
            await message.answer("❌ Использование: <code>/content del 5</code>")
            return
        ok = await delete_template(tid)
        await message.answer("✅ Удалён." if ok else "❌ Не найден.")
    elif sub == "toggle":
        try:
            tid = int(arg)
        except ValueError:
            await message.answer("❌ Использование: <code>/content toggle 5</code>")
            return
        t = await toggle_template(tid)
        if not t:
            await message.answer("❌ Не найден.")
            return
        await message.answer(f"{'✅ Включён' if t.enabled else '⏸ Выключен'}: #{t.id} «{t.name}»")
    elif sub == "preview":
        try:
            tid = int(arg)
        except ValueError:
            await message.answer("❌ Использование: <code>/content preview 5</code>")
            return
        t = await get_template(tid)
        if not t:
            await message.answer("❌ Не найден.")
            return
        vars_ = await _build_variables()
        rendered = _render(t.text, vars_)
        await message.answer(
            f"<b>Превью #{t.id} «{t.name}»</b>\n\n{rendered}",
            disable_web_page_preview=True,
        )
    elif sub == "set_admin":
        if not arg:
            await message.answer(
                "❌ Использование: <code>/content set_admin -1001234567890</code> "
                "или <code>/content set_admin @username_channel</code>"
            )
            return
        await set_setting("content_admin_channel_id", arg.strip())
        await message.answer(f"✅ Админ-канал: <code>{arg.strip()}</code>")
    elif sub == "schedule":
        if not arg:
            await message.answer("❌ Использование: <code>/content schedule 10:00,15:00,20:00</code>")
            return
        await set_setting("content_schedule", arg.strip())
        await message.answer(f"✅ Расписание: <b>{arg.strip()}</b> (МСК)")
    elif sub == "ai":
        on = arg.lower() in ("on", "true", "1", "yes")
        await set_setting("content_ai_enabled", "true" if on else "false")
        note = "" if os.getenv("OPENAI_API_KEY") else "\n⚠️ OPENAI_API_KEY не задан в .env — рерайт не сработает."
        await message.answer(
            (f"✅ AI-рерайт включён.{note}") if on else "⏸ AI-рерайт выключен."
        )
    elif sub == "vars":
        await message.answer(
            "<b>Доступные плейсхолдеры:</b>\n\n"
            "<code>{SIGNALS_24H}</code> — кол-во сигналов за 24ч\n"
            "<code>{UNIQUE_PAIRS_24H}</code> — уникальных пар\n"
            "<code>{MAX_SPREAD}</code> — макс. чистый спред\n"
            "<code>{AVG_SPREAD}</code> — средний\n"
            "<code>{TOP_PAIR}</code> — самая частая пара\n"
            "<code>{TOP_ROUTE}</code> — самый частый маршрут\n"
            "<code>{BOT_LINK}</code> — ссылка на бота\n"
            "<code>{CHANNEL_LINK}</code> — ссылка на канал\n"
            "<code>{DATE}</code> — дата (МСК)\n"
            "<code>{TIME}</code> — время (МСК)"
        )
    else:
        await message.answer("Неизвестная команда. /content — справка.")
