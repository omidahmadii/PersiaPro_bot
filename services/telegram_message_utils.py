from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardMarkup, Message

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_MESSAGE_LIMIT = 4096


def split_text_by_lines(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    lines = (text or "").splitlines()
    if not lines:
        return []

    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0

    for line in lines:
        extra_length = len(line) + (1 if current_lines else 0)
        if current_lines and current_length + extra_length > limit:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_length = len(line)
            continue

        if not current_lines and len(line) > limit:
            for index in range(0, len(line), limit):
                chunks.append(line[index:index + limit])
            current_length = 0
            current_lines = []
            continue

        current_lines.append(line)
        current_length += extra_length

    if current_lines:
        chunks.append("\n".join(current_lines))

    return [chunk for chunk in chunks if chunk]


async def send_photo_with_details(
    message: Message,
    *,
    photo: str,
    caption: str,
    details: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML",
) -> None:
    full_text = details or caption or ""
    caption_chunks = split_text_by_lines(full_text, TELEGRAM_CAPTION_LIMIT)
    safe_caption = caption_chunks[0] if caption_chunks else ""

    await message.answer_photo(
        photo,
        caption=safe_caption,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )

    overflow_text = "\n".join(caption_chunks[1:]) if len(caption_chunks) > 1 else ""
    for chunk in split_text_by_lines(overflow_text, TELEGRAM_MESSAGE_LIMIT):
        await message.answer(chunk, parse_mode=parse_mode)
