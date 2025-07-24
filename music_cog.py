import asyncio
import functools
import random

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# 헬퍼 함수 및 설정
YDL_OPTS = {
    "format": "bestaudio[ext=m4a]/bestaudio/best", "quiet": True,
    "noplaylist": True, "default_search": "ytsearch",
}
YDL_OPTS_AUTOPLAY = {
    "format": "bestaudio/best", "quiet": True, "noplaylist": False,
    "extract_flat": "in_playlist", "playlistend": 5,
}
FFMPEG_BEFORE_OPTS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTS = {"options": "-vn"}

async def ytdlp_extract(query_or_url: str, opts: dict = YDL_OPTS) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(_blocking_ytdlp_extract, query_or_url, opts))

def _blocking_ytdlp_extract(query_or_url: str, opts: dict) -> dict:
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(query_or_url, download=False)

async def search_youtube(query: str) -> dict:
    info = await ytdlp_extract(query)
    if "entries" in info: info = info["entries"][0]
    formats = sorted((f for f in info.get("formats", []) if f.get("acodec") != "none"), key=lambda f: f.get("abr") or 0, reverse=True)
    stream_url = formats[0]["url"] if formats else info["url"]
    return {"title": info["title"], "stream_url": stream_url, "video_id": info["id"]}

async def fetch_youtube_recommendation(video_id: str) -> dict | None:
    try:
        playlist_info = await ytdlp_extract(f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}", opts=YDL_OPTS_AUTOPLAY)
        if not playlist_info or "entries" not in playlist_info or len(playlist_info["entries"]) < 2: return None
        recommended_entry = random.choice(playlist_info["entries"][1:])
        full_info = await ytdlp_extract(recommended_entry['url'])
        formats = sorted((f for f in full_info.get("formats", []) if f.get("acodec") != "none"), key=lambda f: f.get("abr") or 0, reverse=True)
        stream_url = formats[0]["url"] if formats else full_info["url"]
        return {"title": full_info["title"], "stream_url": stream_url, "video_id": full_info["id"], "requester": "자동 재생"}
    except Exception as e:
        print(f"[fetch_youtube_recommendation] 실패: {e}")
        return None

# 음악 기능들을 담고 있는 Cog 클래스
class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: dict[int, list[dict]] = {}
        self.repeat_flag: dict[int, bool] = {}
        self.autoplay_flag: dict[int, bool] = {}
        self.skip_once_flag: dict[int, bool] = {}
        self.current_tracks: dict[int, dict] = {}
        self.last_text_channel: dict[int, discord.TextChannel] = {}

    async def start_playing(self, guild: discord.Guild, track: dict):
        vc = guild.voice_client
        if not vc or not vc.is_connected(): return
        source = discord.FFmpegPCMAudio(track["stream_url"], before_options=FFMPEG_BEFORE_OPTS, **FFMPEG_OPTS)
        self.current_tracks[guild.id] = track
        def _after(error: Exception | None):
            if error: print(f"[ERROR] Player error: {error}")
            asyncio.run_coroutine_threadsafe(self.play_next(guild), self.bot.loop)
        vc.play(source, after=_after)

    async def play_next(self, guild: discord.Guild):
        gid = guild.id
        prev = self.current_tracks.pop(gid, None)
        skip_once = self.skip_once_flag.pop(gid, False)
        next_track = None
        if self.repeat_flag.get(gid) and not skip_once and prev:
            next_track = prev
        elif self.queues.get(gid):
            next_track = self.queues[gid].pop(0)
        elif self.autoplay_flag.get(gid) and prev:
            recommended_track = await fetch_youtube_recommendation(prev['video_id'])
            if recommended_track:
                next_track = recommended_track
                # ✨✨✨ 아래 두 줄을 주석 처리하여 메시지 전송을 막습니다. ✨✨✨
                # text_channel = self.last_text_channel.get(gid)
                # if text_channel: await text_channel.send(f"💿 **자동 재생:** {next_track['title']}")
        if next_track:
            await self.start_playing(guild, next_track)
        else:
            if guild.voice_client and guild.voice_client.is_connected(): await guild.voice_client.disconnect()

    @app_commands.command(name="재생", description="노래를 검색하고 재생합니다")
    @app_commands.describe(query="검색어 또는 YouTube 링크")
    async def slash_play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice or not interaction.user.voice.channel: return await interaction.response.send_message("🔊 먼저 음성 채널에 들어가 주세요!", ephemeral=True)
        self.last_text_channel[interaction.guild_id] = interaction.channel
        await interaction.response.defer(ephemeral=True)
        track = await search_youtube(query)
        track["requester"] = interaction.user
        vc = interaction.guild.voice_client
        if not vc: vc = await interaction.user.voice.channel.connect()
        if vc.is_playing() or self.current_tracks.get(interaction.guild_id):
            self.queues.setdefault(interaction.guild_id, []).append(track)
            await interaction.followup.send(f"➕ **{track['title']}** 예약 완료!", ephemeral=True)
        else:
            await self.start_playing(interaction.guild, track)
            await interaction.followup.send(f"🎶 **현재 재생 중:** {track['title']}", ephemeral=True)

    @app_commands.command(name="스킵", description="현재 곡을 스킵합니다")
    async def slash_skip(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            self.skip_once_flag[interaction.guild_id] = True
            vc.stop()
            await interaction.followup.send("⏭️ 곡을 스킵했어요!", ephemeral=True)
        else: await interaction.followup.send("⚠️ 현재 재생 중인 곡이 없어요.", ephemeral=True)

    @app_commands.command(name="반복", description="현재 곡 반복 재생을 켜거나 끕니다")
    async def slash_repeat(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        is_repeating = self.repeat_flag.get(gid, False)
        self.repeat_flag[gid] = not is_repeating
        if not is_repeating: await interaction.followup.send("🔁 현재 곡 반복을 **켰어요**.", ephemeral=True)
        else: await interaction.followup.send("▶️ 현재 곡 반복을 **껐어요**.", ephemeral=True)

    @app_commands.command(name="자동재생", description="노래가 끝나면 비슷한 노래를 자동으로 재생합니다")
    async def slash_autoplay(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        is_autoplaying = self.autoplay_flag.get(gid, False)
        self.autoplay_flag[gid] = not is_autoplaying
        if not is_autoplaying: await interaction.followup.send("💿 자동 재생을 **켰어요**.", ephemeral=True)
        else: await interaction.followup.send("🛑 자동 재생을 **껐어요**.", ephemeral=True)

    @app_commands.command(name="목록", description="현재 예약된 노래 목록을 확인합니다")
    async def slash_queue(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        queue = self.queues.get(gid, [])
        if not queue: return await interaction.followup.send("📭 예약된 노래가 없어요!", ephemeral=True)
        message_lines = [f"{i}. {track['title']}" for i, track in enumerate(queue, start=1)]
        await interaction.followup.send(f"📃 **예약된 목록:**\n" + "\n".join(message_lines), ephemeral=True)

    @app_commands.command(name="종료", description="봇을 음성 채널에서 퇴장시킵니다")
    async def slash_leave(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            for d in (self.queues, self.current_tracks, self.skip_once_flag, self.repeat_flag, self.autoplay_flag):
                d.pop(interaction.guild_id, None)
            await vc.disconnect()
            await interaction.followup.send("👋 봇이 음성 채널에서 퇴장했어요.", ephemeral=True)
        else: await interaction.followup.send("❗ 봇이 현재 음성 채널에 있지 않아요.", ephemeral=True)

    @app_commands.command(name="명령어", description="사용 가능한 명령어 목록을 확인합니다")
    async def slash_help(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        help_text = ("📖 **사용 가능한 명령어 목록:**\n\n"
                     "🎵 `/재생 [검색어|링크]` - YouTube에서 음악을 검색하고 재생합니다\n"
                     "💿 `/자동재생` - 예약 목록이 끝나면 자동으로 노래를 추천받아 재생합니다\n"
                     "➕ `/목록` - 예약된 노래 목록을 확인합니다\n"
                     "⏭️ `/스킵` - 현재 재생 중인 곡을 스킵합니다\n"
                     "🔁 `/반복` - 현재 곡 반복 재생을 켜거나 끕니다\n"
                     "👋 `/종료` - 봇이 음성 채널에서 퇴장합니다\n"
                     "ℹ️ `/명령어` - 명령어 목록을 확인합니다\n")
        await interaction.followup.send(help_text, ephemeral=True)

# Cog를 봇에 추가하기 위한 필수 함수
async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
