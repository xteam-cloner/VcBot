import re, asyncio, os 
from telethon.errors.rpcerrorlist import ChatSendMediaForbiddenError
from . import vc_asst, Player, get_string, inline_mention, is_url_ok, mediainfo, vid_download, file_download,LOGS


@vc_asst("vplay")
async def video_c(event):
    xx = await event.eor(get_string("com_1"))
    chat = event.chat_id
    from_user = inline_mention(event.sender)
    reply, song = None, None
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
                song = input.split(maxsplit=1)[1]
            except BaseException:
                pass
        else:
            song = input
            
    if not (reply or song):
        return await xx.eor(get_string("vcbot_15"), time=5)
    await xx.eor(get_string("vcbot_20"))
    
    if reply and reply.media and mediainfo(reply.media).startswith("video"):
        song, thumb, title, link, duration = await file_download(xx, reply)
    else:
        is_link = is_url_ok(song)
        if is_link is False:
            return await xx.eor(f"`{song}`\n\nNot a playable link.🥱")
            
        if is_link is None or re.search("youtube", song) or re.search("youtu", song):
            try:
                song, thumb, title, link, duration = await vid_download(song)
            except ValueError as e:
                return await xx.eor(f"❌ **Gagal mencari:** {e}", time=8)
            except Exception as e:
                return await xx.eor(f"❌ **Error unduhan:** {e}", time=8)
        else:
            song, thumb, title, link, duration = (
                song,
                "https://telegra.ph/file/22bb2349da20c7524e4db.mp4",
                song,
                song,
                "♾",
            )
            
    is_valid_source = (
        song and 
        (re.match(r'^https?://|^ftps?://|^\.', song) or os.path.exists(song) or 'telegra.ph' in song)
    )

    if not song or not is_valid_source:
        return await xx.eor(
            "❌ **Gagal:** Tidak dapat menemukan media atau sumber tidak valid. Coba kata kunci atau link lain.",
            time=8,
        )

    ultSongs = Player(chat, xx, True)
    if not (await ultSongs.vc_joiner()):
        return
        
    text = "🎸 **Now playing:** [{}]({})\n⏰ **Duration:** `{}`\n👥 **Chat:** `{}`\n🙋‍♂ **Requested by:** {}".format(
        title, link, duration, chat, from_user
    )
    try:
        await xx.reply(
            text,
            file=thumb,
            link_preview=False,
        )
    except ChatSendMediaForbiddenError:
        await xx.reply(text, link_preview=False)
        
    await asyncio.sleep(1)
    await ultSongs.group_call.start_video(song, with_audio=True)
    await xx.delete()
    
