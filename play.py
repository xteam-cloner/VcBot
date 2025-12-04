
import re,os
from telethon.tl import types
from . import vc_asst, get_string, inline_mention, add_to_queue, mediainfo, file_download, LOGS, is_url_ok, bash, download, Player, VC_QUEUE
from telethon.errors.rpcerrorlist import ChatSendMediaForbiddenError, MessageIdInvalidError


@vc_asst("play")
async def play_music_(event):
    if "playfrom" in event.text.split()[0]:
        return
    try:
        xx = await event.eor(get_string("com_1"), parse_mode="md")
    except MessageIdInvalidError:
        xx = event
        xx.out = False
        
    chat = event.chat_id
    from_user = inline_mention(event.sender, html=True)
    reply, query = None, None # Ganti 'song' menjadi 'query' untuk menghindari kebingungan
    
    if event.reply_to:
        reply = await event.get_reply_message()
    if len(event.text.split()) > 1:
        input = event.text.split(maxsplit=1)[1]
        tiny_input = input.split()[0]
        if tiny_input[0] in ["@", "-"]:
            try:
                chat = await event.client.parse_id(tiny_input)
            except Exception as er:
                LOGS.exception(er)
                return await xx.edit(str(er))
            try:
                query = input.split(maxsplit=1)[1]
            except IndexError:
                pass
            except Exception as e:
                return await event.eor(str(e))
        else:
            query = input
            
    if not (reply or query):
        return await xx.eor("Please specify a song name or reply to a audio file !", time=5)
        
    await xx.eor(get_string("vcbot_20"), parse_mode="md")
    
    # --- Download/Ekstraksi ---
    local_source, thumb, song_name, link, duration = None, None, None, None, None
    
    # Kasus A: Balasan ke File Media (Mengembalikan Path Lokal)
    if reply and reply.media and mediainfo(reply.media).startswith(("audio", "video")):
        local_source, thumb, song_name, link, duration = await file_download(xx, reply)
    # Kasus B: Pencarian/Link YouTube atau URL Non-YouTube (Mengembalikan Path Lokal atau URL Stream)
    elif query:
        # 'download' sekarang mengembalikan PATH LOKAL (atau URL Stream untuk non-YouTube)
        local_source, thumb, song_name, link, duration = await download(query)

    # Cek kegagalan download/ekstraksi
    if not local_source:
        return await xx.eor(f"❌ Gagal mendapatkan atau mengunduh audio untuk: **{query}**.")
    
    # Gunakan nama file yang lebih singkat untuk tampilan
    song_name_display = f"{song_name[:30]}..." if song_name else link[:30]

    ultSongs = Player(chat, event)
    
    if not ultSongs.group_call.is_connected:
        if not (await ultSongs.vc_joiner()):
            return
            
        # PENTING: Menggunakan local_source (Path Lokal atau URL Stream Radio)
        await ultSongs.group_call.start_audio(local_source)
        
        # Penanganan list dihilangkan karena download_yt_file hanya mengambil lagu pertama
        
        text = "🎸 <strong>Now playing: <a href={}>{}</a>\n⏰ Duration:</strong> <code>{}</code>\n👥 <strong>Chat:</strong> <code>{}</code>\n🙋‍♂ <strong>Requested by: {}</strong>".format(
            link, song_name_display, duration, chat, from_user
        )
        try:
            await xx.reply(
                text,
                file=thumb,
                link_preview=False,
                parse_mode="html",
            )
            await xx.delete()
        except ChatSendMediaForbiddenError:
            await xx.eor(text, link_preview=False)
            
        if thumb and os.path.exists(thumb):
            os.remove(thumb)
            
    else:
        # Add to Queue
        
        # local_source adalah PATH LOKAL FILE yang sudah didownload
        add_to_queue(chat, local_source, song_name, link, thumb, from_user, duration)
        
        return await xx.eor(
            f"▶ Ditambahkan 🎵 <a href={song_name_display}</a> ke antrian di urutan #{list(VC_QUEUE[chat].keys())[-1]}.",
            parse_mode="html",
        )

# ... (Perintah playfrom, radio, ytlive tetap sama, pastikan mereka menggunakan Path Lokal atau URL yang stabil)
