import asyncio
from aiogram.types import FSInputFile
from services.bot_instance import bot


async def register_video():
    video = FSInputFile("media/iphone_l2tp.mp4")
    msg = await bot.send_video(
        chat_id=5796072869,
        video=video,
        caption=f"iphone_l2tp"
    )
    print("FILE_ID =", msg.video.file_id)


    video = FSInputFile("media/iphone_ovpn.mp4")
    msg = await bot.send_video(
        chat_id=5796072869,
        video=video,
        caption=f"iphone_ovpn"
    )
    print("FILE_ID =", msg.video.file_id)


    video = FSInputFile("media/iphone_anyconnect.mp4")
    msg = await bot.send_video(
        chat_id=5796072869,
        video=video,
        caption=f"iphone_anyconnect"
    )
    print("FILE_ID =", msg.video.file_id)

    video = FSInputFile("media/android_ovpn.mp4")
    msg = await bot.send_video(
        chat_id=5796072869,
        video=video,
        caption=f"android_ovpn"
    )
    print("FILE_ID =", msg.video.file_id)


    video = FSInputFile("media/android_anyconnect.mp4")
    msg = await bot.send_video(
        chat_id=5796072869,
        video=video,
        caption=f"android_anyconnect"
    )
    print("FILE_ID =", msg.video.file_id)


    video = FSInputFile("media/windows_l2tp.mp4")
    msg = await bot.send_video(
        chat_id=5796072869,
        video=video,
        caption=f"windows_l2tp"
    )
    print("FILE_ID =", msg.video.file_id)


if __name__ == "__main__":
    asyncio.run(register_video())
