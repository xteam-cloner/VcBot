# Ultroid - UserBot
# Copyright (C) 2021-2022 TeamUltroid
#
# This file is a part of < https://github.com/TeamUltroid/Ultroid/ >
# PLease read the GNU Affero General Public License in
# <https://www.github.com/TeamUltroid/Ultroid/blob/main/LICENSE/>.

"""
✘ Commands Available -

• `{i}play <song name/song url/reply to file>`
   Play the song in voice chat, or add the song to queue.

• `{i}playfrom <channel username> ; <limit>`
   Play music from channel files at current chat..

• `{i}radio <link>`
   Stream Live Radio m3u8 links.

• `{i}ytlive <link>`
   Stream Live YouTube
"""

import re,os
from telethon.tl import types
# Pastikan semua impor ini benar, terutama 'download' yang kita modifikasi di __init__.py
from . import vc_asst, get_string, inline_mention, add_to_queue, mediainfo, file_download, LOGS, is_url_ok, bash, download, Player, VC_QUEUE
from telethon.errors.rpcerrorlist import ChatSendMediaForbiddenError, MessageIdInvalidError


@vc_asst("play")
async def play_music_(event):
    if "playfrom" in event.text.split()[0]:
        return  # For PlayFrom Conflict
    try:
        xx = await event.eor(get_string("com_1"), parse_mode="md")
    except MessageIdInvalidError:
        # Changing the way, things work
        xx = event
        xx.out = False
    chat = event.chat_id
    from_user = inline_mention(event.sender, html=True)
    reply, song = None, None
    if event.reply_to:
        reply = await event.get_reply_message()
    if len(event.text.split()) > 1:
        input = event.text.split(maxsplit=1)[1]
        tiny_input = input.split()[0]
        if tiny_input[0] in ["@", "-"]:
            try:
                # Menggunakan event.client.parse_id (jika masih digunakan di Ultroid)
                chat = await event.client.parse_id(tiny_input) 
            except Exception as er:
                LOGS.exception(er)
                return await xx.edit(str(er))
            try:
                song = input.split(maxsplit=1)[1]
            except IndexError:
                pass
            except Exception as e:
                return await event.eor(str(e))
        else:
            song = input
            
    if not (reply or song):
        return await xx.eor("Please specify a song name or reply to a audio file !", time=5
        )
        
    await xx.eor(get_string("vcbot_20"), parse_mode="md")
    
    # --- Penanganan Media ---
    if reply and reply.media and mediainfo(reply.media).startswith(("audio", "video")):
        # song = path file lokal
        song, thumb, song_name, link, duration = await file_download(xx, reply)
    else:
        # song = URL stream stabil (dari get_stream_link di __init__.py)
        # Jika yang diinput adalah list (misalnya playlist) ini akan ditangani
        song, thumb, song_name, link, duration = await download(song) 
        
    # PERBAIKAN: Cek jika pengambilan stream atau download file gagal
    if not song: 
        return await xx.eor(f"❌ Gagal mengambil stream audio atau mengunduh file untuk query/link.")
        
    if isinstance(link, list):
        # Penanganan list dari download() (misalnya playlist)
        first_link = link[0]
    else:
        first_link = link

    ultSongs = Player(chat, event)
    song_name_display = f"{song_name[:30]}..." if song_name else first_link[:30]
    
    # --- Logika Pemutaran / Queue ---
    
    if not ultSongs.group_call.is_connected:
        if not (await ultSongs.vc_joiner()):
            return
            
        # Memulai pemutaran audio dengan stream URL stabil atau path file
        await ultSongs.group_call.start_audio(song) 
        
        if isinstance(link, list):
            # Queue lagu-lagu sisanya
            for lin in link[1:]:
                # Note: 'song' di sini diisi None karena kita hanya menyimpan URL di queue
                add_to_queue(chat, None, lin, lin, None, from_user, duration) 
            link = song_name_display = first_link # Lagu yang sedang diputar
            
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
        # Jika sudah terhubung (Add to Queue)
        
        if isinstance(link, list):
            # Queue semua link dalam list
            for lin in link: 
                add_to_queue(chat, None, lin, lin, None, from_user, duration)
            
            return await xx.eor(
                f"✅ **Ditambahkan {len(link)} lagu** ke antrian, dimulai dari **<a href={first_link}>{first_link[:30]}...</a>**.",
                parse_mode="html",
            )
        
        # Queue lagu tunggal
        add_to_queue(chat, song, song_name, link, thumb, from_user, duration)
        
        return await xx.eor(
            f"▶ Ditambahkan 🎵 <a href={link}>{song_name_display}</a> ke antrian di urutan **#{list(VC_QUEUE[chat].keys())[-1]}**.",
            parse_mode="html",
        )


@vc_asst("playfrom")
async def play_music_(event):
    msg = await event.eor(get_string("com_1"))
    chat = event.chat_id
    limit = 10
    from_user = inline_mention(await event.get_sender(), html=True)
    if len(event.text.split()) <= 1:
        return await msg.edit(
            "Use in Proper Format\n`.playfrom <channel username> ; <limit>`"
        )
    input = event.text.split(maxsplit=1)[1]
    if ";" in input:
        try:
            limit = input.split(";")
            input = limit[0].strip()
            limit = int(limit[1].strip()) if limit[1].strip().isdigit() else 10
            input = await event.client.parse_id(input)
        except (IndexError, ValueError):
            pass
    try:
        fromchat = (await event.client.get_entity(input)).id
    except Exception as er:
        return await msg.eor(str(er))
    await msg.eor("`• Started Playing from Channel....`")
    send_message = True
    ultSongs = Player(chat, event)
    count = 0
    async for song in event.client.iter_messages(
        fromchat, limit=limit, wait_time=5, filter=types.InputMessagesFilterMusic
    ):
        count += 1
        song_path, thumb, song_name, link, duration = await file_download(
            msg, song, fast_download=False
        )
        
        # PERBAIKAN: Cek jika download gagal
        if not song_path:
            LOGS.warning(f"Gagal mengunduh file dari channel {fromchat}, melewatkan lagu.")
            continue
            
        song_name_display = f"{song_name[:30]}..."
        
        if not ultSongs.group_call.is_connected:
            if not (await ultSongs.vc_joiner()):
                return
            await ultSongs.group_call.start_audio(song_path)
            text = "🎸 <strong>Now playing: <a href={}>{}</a>\n⏰ Duration:</strong> <code>{}</code>\n👥 <strong>Chat:</strong> <code>{}</code>\n🙋‍♂ <strong>Requested by: {}</strong>".format(
                link, song_name_display, duration, chat, from_user
            )
            try:
                await msg.reply(
                    text,
                    file=thumb,
                    link_preview=False,
                    parse_mode="html",
                )
            except ChatSendMediaForbiddenError:
                await msg.reply(text, link_preview=False, parse_mode="html")
            if thumb and os.path.exists(thumb):
                os.remove(thumb)
        else:
            # Menggunakan song_path (path file lokal) untuk queue
            add_to_queue(chat, song_path, song_name, link, thumb, from_user, duration)
            if send_message and count == 1:
                await msg.eor(
                    f"▶ Added 🎵 <strong><a href={link}>{song_name_display}</a></strong> to queue at <strong>#{list(VC_QUEUE[chat].keys())[-1]}.</strong>",
                    parse_mode="html",
                )
                send_message = False


@vc_asst("radio")
async def radio_mirchi(e):
    xx = await e.eor(get_string("com_1"))
    if len(e.text.split()) <= 1:
        return await xx.eor("Are You Kidding Me?\nWhat to Play?")
    input = e.text.split()
    if input[1][0] in ["-", "@"]:
        try:
            chat = await e.client.parse_id(input[1])
        except Exception as er:
            return await xx.edit(str(er))
        song = e.text.split(maxsplit=2)[2]
    else:
        song = e.text.split(maxsplit=1)[1]
        chat = e.chat_id
    if not is_url_ok(song):
        return await xx.eor(f"`{song}`\n\nNot a playable link.🥱")
        
    ultSongs = Player(chat, e)
    if not ultSongs.group_call.is_connected and not (await ultSongs.vc_joiner()):
        return
        
    # Radio streaming langsung (biasanya .m3u8 atau .mp3)
    await ultSongs.group_call.start_audio(song)
    
    await xx.reply(
        f"• Started Radio 📻\n\n• Station : `{song}`",
        file="https://telegra.ph/file/d09d4461199bdc7786b01.mp4",
    )
    await xx.delete()


@vc_asst("(live|ytlive)")
async def live_stream(e):
    xx = await e.eor(get_string("com_1"))
    if len(e.text.split()) <= 1:
        return await xx.eor("Are You Kidding Me?\nWhat to Play?")
    input = e.text.split()
    if input[1][0] in ["@", "-"]:
        chat = await e.client.parse_id(input[1])
        song = e.text.split(maxsplit=2)[2]
    else:
        song = e.text.split(maxsplit=1)[1]
        chat = e.chat_id
    if not is_url_ok(song):
        return await xx.eor(f"`{song}`\n\nNot a playable link.🥱")
        
    is_live_vid = False
    if re.search("youtu", song):
        # Memeriksa status live
        is_live_vid = (await bash(f'youtube-dl -j "{song}" | jq ".is_live"'))[0] 
        
    if is_live_vid.strip() != "true":
        return await xx.eor(f"Only Live Youtube Urls supported!\n{song}")
        
    # Menggunakan download() untuk mendapatkan URL stream audio (meskipun live, lebih stabil)
    file, thumb, title, link, duration = await download(song) 
    
    # PERBAIKAN: Cek jika pengambilan stream gagal
    if not file:
        return await xx.eor(f"❌ Gagal mendapatkan stream live audio untuk {title}.")

    ultSongs = Player(chat, e)
    if not ultSongs.group_call.is_connected and not (await ultSongs.vc_joiner()):
        return
        
    from_user = inline_mention(e.sender)
    
    await xx.reply(
        "🎸 **Now playing:** [{}]({})\n⏰ **Duration:** `{}`\n👥 **Chat:** `{}`\n🙋‍♂ **Requested by:** {}".format(
            title, link, duration, chat, from_user
        ),
        file=thumb,
        link_preview=False,
    )
    await xx.delete()
    
    # file = URL stream stabil dari download()
    await ultSongs.group_call.start_audio(file) 
  
