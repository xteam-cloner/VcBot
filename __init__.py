import asyncio
import os
import re
import traceback
from time import time
from traceback import format_exc

from pytgcalls import GroupCallFactory
from pytgcalls.exceptions import GroupCallNotFoundError
from telethon.errors.rpcerrorlist import (
    ParticipantJoinMissingError,
    ChatSendMediaForbiddenError,
)
from xteam import HNDLR, LOGS, asst, udB, vcClient
from xteam._misc._decorators import compile_pattern
from xteam.fns.helper import (
    bash,
    downloader,
    inline_mention,
    mediainfo,
    time_formatter,
)
from xteam.fns.admins import admin_check
from xteam.fns.tools import is_url_ok
from xteam.fns.ytdl import get_videos_link
from xteam._misc import owner_and_sudos, sudoers
from xteam._misc._assistant import in_pattern
from xteam._misc._wrappers import eod, eor
from xteam.version import __version__ as UltVer
from telethon import events
from telethon.tl import functions, types
from telethon.utils import get_display_name

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None
    LOGS.error("'yt-dlp' not found!")

try:
    import av
except ImportError:
    av = None
    LOGS.error("'PyAV' not found!")

try:
   from youtubesearchpython import VideosSearch
   from youtubesearchpython import Playlist
except ImportError:
    VideosSearch = None
    Playlist = None

from strings import get_string

asstUserName = asst.me.username
LOG_CHANNEL = udB.get_key("LOG_CHANNEL")
ACTIVE_CALLS, VC_QUEUE = [], {}
MSGID_CACHE, VIDEO_ON = {}, {}
CLIENTS = {}


def VC_AUTHS():
    _vcsudos = udB.get_key("VC_SUDOS") or []
    return [int(a) for a in [*owner_and_sudos(), *_vcsudos]]


class Player:
    def __init__(self, chat, event=None, video=False):
        self._chat = chat
        self._current_chat = event.chat_id if event else LOG_CHANNEL
        self._video = video
        if CLIENTS.get(chat):
            self.group_call = CLIENTS[chat]
        else:
            _client = GroupCallFactory(
                vcClient, GroupCallFactory.MTPROTO_CLIENT_TYPE.TELETHON,
            )
            self.group_call = _client.get_group_call()
            CLIENTS.update({chat: self.group_call})

    async def make_vc_active(self):
        try:
            await vcClient(
                functions.phone.CreateGroupCallRequest(
                    self._chat, title="🎧 Ultroid Music 🎶"
                )
            )
        except Exception as e:
            LOGS.exception(e)
            return False, e
        return True, None

    async def startCall(self):
        if VIDEO_ON:
            for chats in VIDEO_ON:
                await VIDEO_ON[chats].stop()
            VIDEO_ON.clear()
            await asyncio.sleep(3)
        if self._video:
            for chats in list(CLIENTS):
                if chats != self._chat:
                    await CLIENTS[chats].stop()
                    del CLIENTS[chats]
            VIDEO_ON.update({self._chat: self.group_call})
        if self._chat not in ACTIVE_CALLS:
            try:
                self.group_call.on_network_status_changed(self.on_network_changed)
                self.group_call.on_playout_ended(self.playout_ended_handler)
                await self.group_call.join(self._chat)
            except GroupCallNotFoundError as er:
                LOGS.info(er)
                dn, err = await self.make_vc_active()
                if err:
                    return False, err
            except Exception as e:
                LOGS.exception(e)
                return False, e
        return True, None

    async def on_network_changed(self, call, is_connected):
        chat = self._chat
        if is_connected:
            if chat not in ACTIVE_CALLS:
                ACTIVE_CALLS.append(chat)
        elif chat in ACTIVE_CALLS:
            ACTIVE_CALLS.remove(chat)

    async def playout_ended_handler(self, call, source, mtype):
        if os.path.exists(source):
            os.remove(source)
        await self.play_from_queue()

    async def play_from_queue(self):
        chat_id = self._chat
        if chat_id in VIDEO_ON:
            await self.group_call.stop_video()
            VIDEO_ON.pop(chat_id)
        try:
            song_source, title, link, thumb, from_user, pos, dur = await get_from_queue(
                chat_id
            )
            
            if song_source and "youtube.com" in song_source:
                 local_path, thumb, title, link, dur = await download_yt_file(song_source)
                 if not local_path:
                      LOGS.error(f"Failed to download next song from queue: {song_source}")
                      VC_QUEUE[chat_id].pop(pos)
                      if not VC_QUEUE[chat_id]:
                           VC_QUEUE.pop(chat_id)
                      await self.play_from_queue() 
                      return
                 song_source = local_path
            
            try:
                await self.group_call.start_audio(song_source) 
            except ParticipantJoinMissingError:
                await self.vc_joiner()
                await self.group_call.start_audio(song_source)
            except av.error.InvalidDataError:
                 LOGS.error(f"Media Error: File/Stream invalid or corrupted: {song_source}")
                 await vcClient.send_message(
                     self._current_chat,
                     "⚠️ **ERROR MEDIA:** File yang akan diputar tidak valid atau rusak. Melanjutkan ke antrian berikutnya.",
                     parse_mode="html",
                 )
                 VC_QUEUE[chat_id].pop(pos)
                 if not VC_QUEUE[chat_id]:
                     VC_QUEUE.pop(chat_id)
                 await self.play_from_queue()
                 return
            
            if MSGID_CACHE.get(chat_id):
                await MSGID_CACHE[chat_id].delete()
                del MSGID_CACHE[chat_id]
            text = f"<strong>🎧 Now playing #{pos}: <a href={link}>{title}</a>\n⏰ Duration:</strong> <code>{dur}</code>\n👤 <strong>Requested by:</strong> {from_user}"

            try:
                xx = await vcClient.send_message(
                    self._current_chat,
                    f"<strong>🎧 Now playing #{pos}: <a href={link}>{title}</a>\n⏰ Duration:</strong> <code>{dur}</code>\n👤 <strong>Requested by:</strong> {from_user}",
                    file=thumb,
                    link_preview=False,
                    parse_mode="html",
                )

            except ChatSendMediaForbiddenError:
                xx = await vcClient.send_message(
                    self._current_chat, text, link_preview=False, parse_mode="html"
                )
            MSGID_CACHE.update({chat_id: xx})
            
            VC_QUEUE[chat_id].pop(pos)
            if not VC_QUEUE[chat_id]:
                VC_QUEUE.pop(chat_id)

        except (IndexError, KeyError):
            await self.group_call.stop()
            del CLIENTS[self._chat]
            await vcClient.send_message(
                self._current_chat,
                f"• Successfully Left Vc : <code>{chat_id}</code> •",
                parse_mode="html",
            )
        except Exception as er:
            LOGS.exception(er)
            await vcClient.send_message(
                self._current_chat,
                f"<strong>ERROR:</strong> <code>{format_exc()}</code>",
                parse_mode="html",
            )

    async def vc_joiner(self):
        chat_id = self._chat
        done, err = await self.startCall()

        if done:
            await vcClient.send_message(
                self._current_chat,
                f"• Joined VC in <code>{chat_id}</code>",
                parse_mode="html",
            )

            return True
        await vcClient.send_message(
            self._current_chat,
            f"<strong>ERROR while Joining Vc -</strong> <code>{chat_id}</code> :\n<code>{err}</code>",
            parse_mode="html",
        )
        return False


def vc_asst(dec, **kwargs):
    def ult(func):
        kwargs["func"] = (
            lambda e: not e.is_private and not e.via_bot_id and not e.fwd_from
        )
        handler = udB.get_key("VC_HNDLR") or HNDLR
        kwargs["pattern"] = compile_pattern(dec, handler)
        vc_auth = kwargs.get("vc_auth", True)
        key = udB.get_key("VC_AUTH_GROUPS") or {}
        if "vc_auth" in kwargs:
            del kwargs["vc_auth"]

        async def vc_handler(e):
            VCAUTH = list(key.keys())
            if not (
                (e.out)
                or (e.sender_id in VC_AUTHS())
                or (vc_auth and e.chat_id in VCAUTH)
            ):
                return
            elif vc_auth and key.get(e.chat_id):
                cha, adm = key.get(e.chat_id), key[e.chat_id]["admins"]
                if adm and not (await admin_check(e)):
                    return
            try:
                await func(e)
            except Exception:
                LOGS.exception(Exception)
                await asst.send_message(
                    LOG_CHANNEL,
                    f"VC Error - <code>{UltVer}</code>\n\n<code>{e.text}</code>\n\n<code>{format_exc()}</code>",
                    parse_mode="html",
                )

        vcClient.add_event_handler(
            vc_handler,
            events.NewMessage(**kwargs),
        )

    return ult


def add_to_queue(chat_id, song, song_name, link, thumb, from_user, duration):
    try:
        n = sorted(list(VC_QUEUE[chat_id].keys()))
        play_at = n[-1] + 1
    except BaseException:
        play_at = 1
    stuff = {
        play_at: {
            "song": song, 
            "title": song_name,
            "link": link,
            "thumb": thumb,
            "from_user": from_user,
            "duration": duration,
        }
    }
    if VC_QUEUE.get(chat_id):
        VC_QUEUE[int(chat_id)].update(stuff)
    else:
        VC_QUEUE.update({chat_id: stuff})
    return VC_QUEUE[chat_id]


def list_queue(chat):
    if VC_QUEUE.get(chat):
        txt, n = "", 0
        for x in list(VC_QUEUE[chat].keys())[:18]:
            n += 1
            data = VC_QUEUE[chat][x]
            txt += f'<strong>{n}. <a href={data["link"]}>{data["title"]}</a> :</strong> <i>By: {data["from_user"]}</i>\n'
        txt += "\n\n....."
        return txt


async def get_from_queue(chat_id):
    play_this = list(VC_QUEUE[int(chat_id)].keys())[0]
    info = VC_QUEUE[int(chat_id)][play_this]
    song = info.get("song")
    title = info["title"]
    link = info["link"]
    thumb = info["thumb"]
    from_user = info["from_user"]
    duration = info["duration"]
        
    return song, title, link, thumb, from_user, play_this, duration


async def download_yt_file(ytlink):
    if not YoutubeDL:
        LOGS.error("yt-dlp not installed!")
        return None, None, None, None, None
        
    if not os.path.isdir("vcbot/download"):
        os.makedirs("vcbot/download")
        
    ytd_opts = {
        "format": "bestaudio/best",
        "outtmpl": "vcbot/download/%(id)s.%(ext)s", 
        "prefer_ffmpeg": True,
        "addmetadata": True,
        "geo-bypass": True,
        "nocheckcertificate": True,
        "quiet": True, 
        "no_warnings": True,
        "forcethumbnail": True,
        "writethumbnail": True,
    }
    
    try:
        with YoutubeDL(ytd_opts) as ydl:
            info = ydl.extract_info(ytlink, download=True)
            
            if 'entries' in info:
                info = info['entries'][0]
                
            local_path = ydl.prepare_filename(info) 
            
            intended_dir = "vcbot/download"
            if not local_path.startswith(intended_dir):
                 local_path = os.path.join(intended_dir, os.path.basename(local_path))


            title = info.get("title", "Unknown")
            duration_sec = info.get("duration")
            duration = time_formatter(duration_sec * 1000) if duration_sec else "♾"
            thumb = f"https://i.ytimg.com/vi/{info['id']}/hqdefault.jpg"
            link = info['webpage_url']

            return local_path, thumb, title, link, duration
            
    except Exception as e:
        LOGS.error(f"Failed to download YT file: {e}")
        return None, None, None, None, None

async def download(query):
    if query.startswith("https://") and "youtube" not in query.lower():
        thumb, duration = None, "Unknown"
        title = link = query
        dl = query 
        return dl, thumb, title, link, duration
    else:
        if not VideosSearch:
             return None, None, None, None, None
        search = VideosSearch(query, limit=1).result()
        if not search["result"]:
            return None, None, None, None, None
            
        data = search["result"][0]
        link = data["link"]
        
        local_path, thumb, title, link, duration = await download_yt_file(link)
        
        return local_path, thumb, title, link, duration

async def dl_playlist(chat, from_user, link):
    if not Playlist:
        LOGS.error("youtubesearchpython not installed for Playlist!")
        return None, None, None, None, None
        
    try:
        links = await get_videos_link(link) 
    except Exception as er:
        LOGS.exception(er)
        return None, None, None, None, None
        
    if not links:
        return None, None, None, None, None

    first_link = links[0]
    local_path, thumb, title, link, duration = await download_yt_file(first_link)
    
    if not local_path:
        return None, None, None, None, None

    for url in links[1:]:
        try:
            if not VideosSearch:
                 continue
            search = VideosSearch(url, limit=1).result()
            if not search["result"]:
                 continue
            vid = search["result"][0]
            dur_sec = vid.get("duration")
            dur = time_formatter(dur_sec * 1000) if dur_sec else "♾"
            title_q = vid["title"]
            thumb_q = f"https://i.ytimg.com/vi/{vid['id']}/hqdefault.jpg"
            link_q = vid["link"]
            
            add_to_queue(chat, link_q, title_q, link_q, thumb_q, from_user, dur)
        except Exception as er:
            LOGS.exception(er)
            
    return local_path, thumb, title, link, duration


async def vid_download(query):
    if not VideosSearch:
        return None, None, None, None, None
    search = VideosSearch(query, limit=1).result()
    data = search["result"][0]
    link = data["link"]
    video, thumb, title, link, duration = await download_yt_file(link)
    return video, thumb, title, link, duration

async def file_download(event_or_message, message, fast_download=True):
    if not message.media:
        return None, None, None, None, None

    download_dir = "vcbot/download/"
    if not os.path.isdir(download_dir):
        os.makedirs(download_dir)

    await event_or_message.edit("• Mengunduh media...")
    
    local_path = None
    try:
        local_path = await downloader(
            message,
            file_name=download_dir
        )
    except Exception as e:
        LOGS.exception(f"Failed to download replied media file: {e}")
        return None, None, None, None, None

    try:
        info = mediainfo(local_path) 
        
        song_name = getattr(message.document, 'file_name', os.path.basename(local_path))
        duration_sec = getattr(message.document, 'duration', None)
        duration = time_formatter(duration_sec * 1000) if duration_sec else "♾"
        
        link = local_path 
        
        if message.document and message.document.thumbs:
            thumb = await message.download_media(message.document.thumbs[0])
        else:
            thumb = None

        return local_path, thumb, song_name, link, duration
        
    except Exception as e:
        LOGS.exception(f"Failed to process mediainfo: {e}")
        if local_path and os.path.exists(local_path):
             os.remove(local_path)
        return None, None, None, None, None
            
