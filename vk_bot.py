import asyncio
import logging
import os
import tempfile
import ssl
import random
from pathlib import Path
import aiohttp
import certifi
from vkbottle import Bot, API

# Global fix for SSL certificate verification issues on macOS/Python 3.12
ssl._create_default_https_context = ssl._create_unverified_context
os.environ["SSL_CERT_FILE"] = certifi.where()

from config import load_settings, load_prompts
from transcribe import WhisperTranscriber

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("vk_bot")

async def main():
    # 1. Load configuration and initialize Whisper
    settings = load_settings()
    prompts = load_prompts(settings.prompts_file)

    if not settings.vk_token:
        log.error("VK_TOKEN not found in .env")
        return

    # Load model once at startup
    log.info("Initializing Whisper model...")
    transcriber = WhisperTranscriber(settings, prompts)

    # --- FIX SSL FOR VKBOTTLE ---
    api = API(token=settings.vk_token)
    bot = Bot(api=api)

    from vkbottle.http import AiohttpClient
    connector = aiohttp.TCPConnector(ssl=False)
    custom_client = AiohttpClient()
    custom_client.session = aiohttp.ClientSession(connector=connector)
    bot.api.http_client = custom_client
    # ----------------------------

    @bot.on.message()
    async def handle_message(message):
        all_attachments = []

        if message.attachments:
            all_attachments.extend(message.attachments)

        if hasattr(message, 'fwd_messages') and message.fwd_messages:
            for fwd in message.fwd_messages:
                if hasattr(fwd, 'attachments') and fwd.attachments:
                    all_attachments.extend(fwd.attachments)

        if not all_attachments:
            return

        for attachment in all_attachments:
            if attachment.type in {"voice", "audio_message", "audio"}:
                try:
                    url = None
                    if hasattr(attachment, 'audio_message') and attachment.audio_message:
                        url = getattr(attachment.audio_message, 'link_mp3', None)
                    if not url and hasattr(attachment, 'audio') and attachment.audio:
                        url = getattr(attachment.audio, 'url', None)
                    if not url:
                        audio_id = getattr(attachment, 'id', getattr(attachment, 'audio_id', None))
                        if not audio_id and hasattr(attachment, 'audio') and attachment.audio:
                            audio_id = getattr(attachment.audio, 'id', None)
                        if audio_id:
                            try:
                                audio_info = await bot.api.audio.get(ids=audio_id)
                                if audio_info and len(audio_info) > 0:
                                    url = audio_info[0].url
                            except Exception:
                                pass

                    if not url:
                        continue

                    # --- UI FEEDBACK ---
                    send_resp = await bot.api.messages.send(
                        peer_id=message.peer_id,
                        message="⏳ Идёт расшифровка сообщения...",
                        random_id=random.getrandbits(63)
                    )

                    status_msg_id = None
                    if isinstance(send_resp, int):
                        status_msg_id = send_resp
                    elif hasattr(send_resp, 'message_id'):
                        status_msg_id = send_resp.message_id
                    elif isinstance(send_resp, dict):
                        status_msg_id = send_resp.get('response')

                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_path = Path(temp_dir) / "voice.mp3"
                        download_connector = aiohttp.TCPConnector(ssl=False)
                        async with aiohttp.ClientSession(connector=download_connector) as session:
                            async with session.get(url) as resp:
                                if resp.status != 200:
                                    if status_msg_id:
                                        await bot.api.messages.edit(
                                            peer_id=message.peer_id,
                                            message_id=status_msg_id,
                                            text="❌ Ошибка при загрузке аудиофайла."
                                        )
                                    continue
                                with open(temp_path, "wb") as f:
                                    f.write(await resp.read())

                        log.info("Processing audio for peer %s...", message.peer_id)
                        text = await asyncio.to_thread(transcriber.transcribe, temp_path)

                        if not text or not text.strip():
                            final_text = "Не удалось распознать речь в аудиосообщении."
                        else:
                            final_text = text.strip()

                        if status_msg_id:
                            try:
                                await asyncio.sleep(1.0)
                                # IMPORTANT: For messages.edit in vkbottle, ensure the parameter name is correct.
                                # The API requires 'message' for the new text.
                                await bot.api.messages.edit(
                                    peer_id=message.peer_id,
                                    message_id=status_msg_id,
                                    message=final_text # Changed 'text' to 'message'
                                )
                                log.info("Status message edited successfully for peer %s", message.peer_id)
                            except Exception as e:
                                log.error("Failed to edit status message: %s", e)
                                await bot.api.messages.send(
                                    peer_id=message.peer_id,
                                    message=final_text,
                                    random_id=random.getrandbits(63)
                                )
                        else:
                            await bot.api.messages.send(
                                peer_id=message.peer_id,
                                message=final_text,
                                random_id=random.getrandbits(63)
                            )

                        if text and text.strip():
                            log.info("Transcription sent successfully to peer %s", message.peer_id)

                except Exception as e:
                    log.exception("Critical error processing voice message")
                    try:
                        if 'status_msg_id' in locals() and status_msg_id:
                            await bot.api.messages.edit(
                                peer_id=message.peer_id,
                                message_id=status_msg_id,
                                message=f"Произошла ошибка: {e}" # Changed 'text' to 'message'
                            )
                    except:
                        pass

    log.info("VK Bot started. Listening for voice messages...")
    await bot.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
