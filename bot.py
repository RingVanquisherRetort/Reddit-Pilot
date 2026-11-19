"""Telegram control panel for a single authorized Reddit account."""
import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes
)
from config import load_settings
from database import (
    create_draft, get_draft, init_db, list_drafts, mark_failed, mark_published
)
from reddit_client import RedditClient

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("reddit_pilot")


def authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == load_settings().telegram_admin_id)


async def deny(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Доступ запрещён.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return await deny(update)
    await update.effective_message.reply_text(
        "Reddit Pilot готов. Команда /help покажет доступные функции."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return await deny(update)
    await update.effective_message.reply_text(
        "/me — подключённый аккаунт\n"
        "/subreddit <имя> — информация о сабреддите\n"
        "/search <запрос> — поиск публичных постов\n"
        "/draft <subreddit> | <заголовок> | <текст> — сохранить черновик\n"
        "/drafts — список черновиков\n"
        "/publish <id> — запросить подтверждение публикации"
    )


async def reddit_call(func, *args):
    return await asyncio.to_thread(func, *args)


async def me_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return await deny(update)
    try:
        data = await reddit_call(RedditClient().me)
        await update.effective_message.reply_text(
            f"Аккаунт: u/{data['name']}\n"
            f"Link karma: {data['link_karma']}\n"
            f"Comment karma: {data['comment_karma']}"
        )
    except Exception as exc:
        log.exception("Reddit /me failed")
        await update.effective_message.reply_text(f"Ошибка Reddit API: {exc}")


async def subreddit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return await deny(update)
    if not context.args:
        return await update.effective_message.reply_text("Использование: /subreddit python")
    name = context.args[0].removeprefix("r/")
    try:
        data = await reddit_call(RedditClient().subreddit_info, name)
        await update.effective_message.reply_text(
            f"r/{data['name']} — {data['title']}\n"
            f"Подписчики: {data['subscribers']:,}\n"
            f"18+: {'да' if data['over18'] else 'нет'}\n"
            f"{data['description'] or 'Описание отсутствует'}"
        )
    except Exception as exc:
        log.exception("Subreddit lookup failed")
        await update.effective_message.reply_text(f"Не удалось получить сабреддит: {exc}")


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return await deny(update)
    query = " ".join(context.args).strip()
    if not query:
        return await update.effective_message.reply_text("Использование: /search ваш запрос")
    try:
        results = await reddit_call(RedditClient().search, query, 5)
        if not results:
            return await update.effective_message.reply_text("Ничего не найдено.")
        lines = [
            f"• [{item['subreddit']}] {item['title']}\n"
            f"  score: {item['score']} · {item['url']}"
            for item in results
        ]
        await update.effective_message.reply_text(
            "\n\n".join(lines), disable_web_page_preview=True
        )
    except Exception as exc:
        log.exception("Search failed")
        await update.effective_message.reply_text(f"Ошибка поиска: {exc}")


async def draft_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return await deny(update)
    raw = update.effective_message.text.partition(" ")[2]
    parts = [part.strip() for part in raw.split("|", 2)]
    if len(parts) != 3 or not all(parts):
        return await update.effective_message.reply_text(
            "Формат: /draft subreddit | Заголовок | Текст публикации"
        )
    subreddit, title, body = parts
    subreddit = subreddit.removeprefix("r/").strip()
    cfg = load_settings()
    if cfg.allowed_subreddits and subreddit.lower() not in cfg.allowed_subreddits:
        return await update.effective_message.reply_text(
            "Этот сабреддит не входит в ALLOWED_SUBREDDITS."
        )
    if len(title) > 300 or len(body) > 40000:
        return await update.effective_message.reply_text("Заголовок или текст слишком длинный.")
    draft_id = create_draft(subreddit, title, body)
    await update.effective_message.reply_text(
        f"Черновик #{draft_id} сохранён. Для публикации: /publish {draft_id}"
    )


async def drafts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return await deny(update)
    drafts = list_drafts()
    if not drafts:
        return await update.effective_message.reply_text("Черновиков пока нет.")
    lines = [
        f"#{d['id']} · r/{d['subreddit']} · {d['status']} · {d['title'][:70]}"
        for d in drafts
    ]
    await update.effective_message.reply_text("\n".join(lines))


async def publish_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return await deny(update)
    if not context.args or not context.args[0].isdigit():
        return await update.effective_message.reply_text("Использование: /publish <id>")
    draft_id = int(context.args[0])
    draft = get_draft(draft_id)
    if not draft or draft["status"] != "draft":
        return await update.effective_message.reply_text("Черновик не найден или уже обработан.")
    cfg = load_settings()
    if cfg.allowed_subreddits and draft["subreddit"].lower() not in cfg.allowed_subreddits:
        return await update.effective_message.reply_text("Сабреддит не входит в ALLOWED_SUBREDDITS.")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Опубликовать", callback_data=f"publish:{draft_id}"),
        InlineKeyboardButton("Отмена", callback_data=f"cancel:{draft_id}"),
    ]])
    await update.effective_message.reply_text(
        f"Подтвердить публикацию в r/{draft['subreddit']}?\n\n"
        f"{draft['title']}\n\n{draft['body'][:1200]}",
        reply_markup=keyboard,
    )


async def publish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user or query.from_user.id != load_settings().telegram_admin_id:
        if query:
            await query.answer("Доступ запрещён.", show_alert=True)
        return
    await query.answer()
    action, raw_id = query.data.split(":", 1)
    draft_id = int(raw_id)
    if action == "cancel":
        await query.edit_message_text("Публикация отменена.")
        return
    draft = get_draft(draft_id)
    if not draft or draft["status"] != "draft":
        await query.edit_message_text("Черновик уже обработан или не найден.")
        return
    cfg = load_settings()
    if cfg.allowed_subreddits and draft["subreddit"].lower() not in cfg.allowed_subreddits:
        await query.edit_message_text("Сабреддит не входит в ALLOWED_SUBREDDITS.")
        return
    try:
        url = await reddit_call(
            RedditClient().submit_text, draft["subreddit"], draft["title"], draft["body"]
        )
        mark_published(draft_id, url)
        await query.edit_message_text(f"Опубликовано: {url}")
    except Exception as exc:
        log.exception("Publishing failed")
        mark_failed(draft_id, str(exc))
        await query.edit_message_text(f"Ошибка публикации: {exc}")


def main() -> None:
    cfg = load_settings()
    init_db()
    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("me", me_cmd))
    app.add_handler(CommandHandler("subreddit", subreddit_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("draft", draft_cmd))
    app.add_handler(CommandHandler("drafts", drafts_cmd))
    app.add_handler(CommandHandler("publish", publish_cmd))
    app.add_handler(CallbackQueryHandler(
        publish_callback, pattern=r"^(publish|cancel):\\d+$"
    ))
    log.info("Reddit Pilot Telegram bot starting")
    app.run_polling()


if __name__ == "__main__":
    main()
