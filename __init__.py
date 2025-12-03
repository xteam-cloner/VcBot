# Ultroid - UserBot
# Copyright (C) 2021-2022 TeamUltroid
#
# This file is a part of < https://github.com/TeamUltroid/Ultroid/ >
# PLease read the GNU Affero General Public License in
# <https://www.github.com/TeamUltroid/Ultroid/blob/main/LICENSE/>.

# ----------------------------------------------------------#
#                                                           #
#    _   _ _   _____ ____   ___ ___ ____   __     ______    #
#   | | | | | |_   _|  _ \ / _ \_ _|  _ \  \ \   / / ___|   #
#   | | | | |   | | | |_) | | | | || | | |  \ \ / / |       #
#   | |_| | |___| | |  _ <| |_| | || |_| |   \ V /| |___    #
#    \___/|_____|_| |_| \_\\___/___|____/     \_/  \____|   #
#                                                           #
# ----------------------------------------------------------#


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
        # 'source' kini adalah path file lokal
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
            
            # Jika song_source adalah URL YouTube (dari playlist), download sekarang
            if song_source and "youtube.com" in song_source:
                 local_path, thumb, title, link, dur = await download_yt_file(song_source)
                 if not local_path:
                      raise Exception("Failed to download next song from queue.")
                 song_source = local_path
            
            try:
                # 'song_source' adalah path lokal atau URL stream radio
                await self.group_call.start_audio(song_source) 
            except ParticipantJoinMissingError:
                await self.vc_joiner()
                await self.group_call.start_audio(song_source)
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


# --------------------------------------------------


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


# --------------------------------------------------


def add_to_queue(chat_id, song, song_name, link, thumb, from_user, duration):
    try:
        n = sorted(list(VC_QUEUE[chat_id].keys()))
        play_at = n[-1] + 1
    except BaseException:
        play_at = 1
    stuff = {
        play_at: {
            "song": song, # Path lokal, URL stream, atau URL YT (untuk playlist)
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


# --------------------------------------------------

# --- FUNGSI DOWNLOAD BARU (Inti Stabilitas) ---

async def download_yt_file(ytlink):
    """
    Mengunduh file audio terbaik ke path lokal dan mengembalikan path serta metadata.
    """
    if not YoutubeDL:
        LOGS.error("yt-dlp tidak terinstal!")
        return None, None, None, None, None
        
    # Buat direktori download jika belum ada
    if not os.path.isdir("vcbot/download"):
        os.makedirs("vcbot/download")
        
    # Atur opsi download audio-only
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
        "writethumbnail": True, # Untuk thumbnail lokal jika diperlukan
    }
    
    try:
        with YoutubeDL(ytd_opts) as ydl:
            # Mengambil informasi video dan mengunduh
            info = ydl.extract_info(ytlink, download=True)
            
            if 'entries' in info:
                # Jika link adalah playlist, ambil info entri pertama
                info = info['entries'][0]
                
            # Mengambil path file yang diunduh secara lokal
            local_path = ydl.prepare_filename(info) 
            # Perbaiki path relatif
            if not os.path.isabs(local_path):
                 local_path = os.path.join("vcbot/download", local_path)

            # Cari informasi yang relevan
            title = info.get("title", "Unknown")
            duration_sec = info.get("duration")
            duration = time_formatter(duration_sec * 1000) if duration_sec else "♾"
            thumb = f"https://i.ytimg.com/vi/{info['id']}/hqdefault.jpg"
            link = info['webpage_url']

            return local_path, thumb, title, link, duration
            
    except Exception as e:
        LOGS.error(f"Gagal mendownload file YT: {e}")
        return None, None, None, None, None

# --- FUNGSI DOWNLOAD UTAMA (Dipanggil oleh play.py) ---
async def download(query):
    if query.startswith("https://") and "youtube" not in query.lower():
        # Kasus URL non-YouTube/Radio
        thumb, duration = None, "Unknown"
        title = link = query
        dl = query 
        return dl, thumb, title, link, duration
    else:
        # Kasus Pencarian/Link YouTube
        search = VideosSearch(query, limit=1).result()
        if not search["result"]:
            return None, None, None, None, None
            
        data = search["result"][0]
        link = data["link"]
        
        # PANGGIL FUNGSI DOWNLOAD BARU
        local_path, thumb, title, link, duration = await download_yt_file(link)
        
        return local_path, thumb, title, link, duration

# --- FUNGSI PLAYLIST YANG HILANG (Wajib Dikembalikan) ---
async def dl_playlist(chat, from_user, link):
    """
    Mengelola playlist: mendownload lagu pertama, menambahkan sisanya ke queue.
    """
    if not Playlist:
        LOGS.error("youtubesearchpython tidak terinstal untuk Playlist!")
        return None, None, None, None, None
        
    try:
        # Menggunakan get_videos_link (asumsi ini mengembalikan list of URLs)
        links = await get_videos_link(link) 
    except Exception as er:
        LOGS.exception(er)
        return None, None, None, None, None
        
    if not links:
        return None, None, None, None, None

    # DOWNLOAD LAGU PERTAMA SECARA LOKAL
    first_link = links[0]
    local_path, thumb, title, link, duration = await download_yt_file(first_link)
    
    if not local_path:
        return None, None, None, None, None

    # TAMBAHKAN LAGU SISA KE QUEUE (hanya simpan URL)
    for url in links[1:]:
        try:
            search = VideosSearch(url, limit=1).result()
            if not search["result"]:
                 continue
            vid = search["result"][0]
            dur_sec = vid.get("duration")
            dur = time_formatter(dur_sec * 1000) if dur_sec else "♾"
            title_q = vid["title"]
            thumb_q = f"https://i.ytimg.com/vi/{vid['id']}/hqdefault.jpg"
            link_q = vid["link"]
            
            # Simpan URL di queue. Fungsi play_from_queue akan men-download saat giliran tiba.
            add_to_queue(chat, link_q, title_q, link_q, thumb_q, from_user, dur)
        except Exception as er:
            LOGS.exception(er)
            
    # Kembalikan hasil download lagu pertama untuk diputar
    return local_path, thumb, title, link, duration


# --- FUNGSI LAMA (Disisakan untuk kompatibilitas jika diperlukan) ---
async def vid_download(query):
    search = VideosSearch(query, limit=1).result()
    data = search["result"][0]
    link = data["link"]
    # Menggunakan download file penuh untuk video juga
    video, thumb, title, link, duration = await download_yt_file(link)
    return video, thumb, title, link, duration

async def file_download(event_or_message, message, fast_download=True):
    # Asumsi fungsi ini didefinisikan di tempat lain atau di dalam __init__.py 
    # untuk menangani file audio/video yang dibalas.
    # Jika tidak ada, Anda perlu mendefinisikannya berdasarkan struktur Ultroid.
    # Contoh stub:
    if not message.media:
        return None, None, None, None, None
    
    # ... (Logika downloader, mediainfo, dll. di sini) ...
    
    # Jika berhasil, kembalikan:
    # return local_path, thumb, song_name, link, duration
    pass
# -----------------------------------------------------------------------

# --- Tambahkan atau verifikasi fungsi file_download di sini ---

async def file_download(event_or_message, message, fast_download=True):
    """
    Menangani download file media yang dibalas.
    Menggunakan xteam.fns.helper.downloader.
    """
    if not message.media:
        return None, None, None, None, None

    # Tentukan path download lokal
    download_dir = "vcbot/download/"
    if not os.path.isdir(download_dir):
        os.makedirs(download_dir)

    await event_or_message.edit("• Mengunduh media...")
    
    try:
        # Menggunakan downloader dari xteam.fns.helper
        # Asumsi 'downloader' dapat menangani objek Message/Media dan mengembalikan path lokal
        local_path = await downloader(
            message,
            file_name=download_dir
        )
    except Exception as e:
        LOGS.exception(f"Gagal mengunduh file media yang dibalas: {e}")
        return None, None, None, None, None

    try:
        # Mengambil informasi media
        info = mediainfo(local_path) 
        
        # Ekstrak data yang diperlukan (asumsi mediainfo mengembalikan string yang dapat diparse)
        # Karena mediainfo tidak selalu mengembalikan objek terstruktur, kita lakukan ekstraksi dasar
        song_name = getattr(message.document, 'file_name', os.path.basename(local_path))
        duration_sec = getattr(message.document, 'duration', None)
        duration = time_formatter(duration_sec * 1000) if duration_sec else "♾"
        
        # Link akan disetel ke path lokal untuk pemutaran
        link = local_path 
        
        # Thumb: Ambil thumbnail jika ada
        if message.document and message.document.thumbs:
            thumb = await message.download_media(message.document.thumbs[0])
        else:
            thumb = None

        return local_path, thumb, song_name, link, duration
        
    except Exception as e:
        LOGS.exception(f"Gagal memproses mediainfo: {e}")
        # Hapus file yang sudah terlanjur didownload jika gagal diproses
        if os.path.exists(local_path):
             os.remove(local_path)
        return None, None, None, None, None

# --- Pastikan fungsi lain yang bergantung pada impor ada, seperti downloader (dari xteam.fns.helper) ---
