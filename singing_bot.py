import os
import asyncio
import functools
import random

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# ──────────────────── 기본 설정 ────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

queues: dict[int, list[dict]] = {}
repeat_flag: dict[int, bool] = {}
skip_once_flag: dict[int, bool] = {}
current_tracks: dict[int, dict] = {}

YDL_OPTS = {
    "format": "bestaudio[ext=m4a]/bestaudio/best",
    "quiet": True,
    "noplaylist": True,
    "default_search": "ytsearch",
}
FFMPEG_BEFORE_OPTS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTS = {"options": "-vn"}


# ──────────────────── YT-DLP 비동기 래퍼 ────────────────────
async def ytdlp_extract(query_or_url: str) -> dict:
    """YT-DLP를 블로킹 없이 호출(스레드 실행)"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(_blocking_ytdlp_extract, query_or_url),
    )


def _blocking_ytdlp_extract(query_or_url: str) -> dict:
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        return ydl.extract_info(query_or_url, download=False)


# ──────────────────── 검색 & 추천 트랙 ────────────────────
async def search_youtube(query: str) -> dict:
    info = await ytdlp_extract(query)
    if "entries" in info:  # ytsearch 결과
        info = info["entries"][0]

    # 가장 높은 비트레이트 오디오 URL
    formats = sorted(
        (f for f in info.get("formats", []) if f.get("acodec") != "none"),
        key=lambda f: f.get("abr") or 0,
        reverse=True,
    )
    stream_url = formats[0]["url"] if formats else info["url"]

    return {
        "title": info["title"],
        "stream_url": stream_url,
        "video_id": info["id"],
    }


async def try_fetch_track(video_id: str) -> dict | None:
    """video_id로부터 트랙 정보 시도"""
    try:
        info = await ytdlp_extract(f"https://www.youtube.com/watch?v={video_id}")
        formats = sorted(
            (f for f in info.get("formats", []) if f.get("acodec") != "none"),
            key=lambda f: f.get("abr") or 0,
            reverse=True,
        )
        stream_url = formats[0]["url"] if formats else info["url"]
        return {
            "title": info["title"],
            "stream_url": stream_url,
            "video_id": info["id"],
            "requester": "autoplay",
        }
    except Exception as e:
        print(f"[try_fetch_track] 실패: {e}")
        return None




# ──────────────────── 플레이어 로직 ────────────────────
async def start_playing(guild: discord.Guild, track: dict):
    vc = guild.voice_client
    if not vc or not vc.is_connected():
        return

    source = discord.FFmpegPCMAudio(
        track["stream_url"], before_options=FFMPEG_BEFORE_OPTS, **FFMPEG_OPTS
    )
    current_tracks[guild.id] = track

    def _after(error: Exception | None):
        if error:
            print(f"[ERROR] Player error: {error}")
        asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)

    vc.play(source, after=_after)


async def play_next(guild: discord.Guild):
    gid = guild.id
    print(f"[play_next] 재생 종료 감지. 서버 ID: {gid}")
    prev = current_tracks.pop(gid, None)
    print(f"[play_next] 이전 곡: {prev['title'] if prev else '없음'}")

    skip_once = skip_once_flag.pop(gid, False)
    next_track = None

    if not skip_once and prev:
        print("[play_next] 반복 재생 활성화")
        next_track = {
            "title": prev["title"],
            "stream_url": prev["stream_url"],
            "video_id": prev["video_id"],
            "requester": prev["requester"],
        }
    elif queues.get(gid):
        print("[play_next] 큐에서 다음 곡 재생")
        next_track = queues[gid].pop(0)

    if next_track:
        await start_playing(guild, next_track)
    else:
        print("[play_next] 더 이상 재생할 곡이 없어 퇴장")
        if guild.voice_client and guild.voice_client.is_connected():
            await guild.voice_client.disconnect()



# ──────────────────── Slash Commands ────────────────────
@bot.tree.command(name="재생", description="노래를 검색하고 재생합니다")
@app_commands.describe(query="검색어 또는 YouTube 링크")
async def slash_play(interaction: discord.Interaction, query: str):
    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.response.send_message(
            "🔊 먼저 음성 채널에 들어가 주세요!", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)
    track = await search_youtube(query)
    track["requester"] = interaction.user

    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()

    if vc.is_playing():
        queues.setdefault(interaction.guild_id, []).append(track)
        await interaction.followup.send(
            f"➕ **{track['title']}** 예약 완료!", ephemeral=True
        )
    else:
        await start_playing(interaction.guild, track)
        await interaction.followup.send(
            f"🎶 **현재 재생 중:** {track['title']}", ephemeral=True
        )


@bot.tree.command(name="스킵", description="현재 곡을 스킵합니다")
async def slash_skip(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            skip_once_flag[interaction.guild_id] = True
            vc.stop()
            await interaction.followup.send("⏭️ 곡을 스킵했어요!", ephemeral=True)
        else:
            await interaction.followup.send(
                "⚠️ 현재 재생 중인 곡이 없어요.", ephemeral=True
            )
    except Exception as e:
        print(f"[스킵 오류] {e}")
        await interaction.followup.send("❌ 스킵 중 오류 발생!", ephemeral=True)

@bot.tree.command(name="목록", description="현재 예약된 노래 목록을 확인합니다")
async def slash_queue(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    gid = interaction.guild_id
    queue = queues.get(gid, [])

    if not queue:
        await interaction.followup.send("📭 예약된 노래가 없어요!", ephemeral=True)
        return

    message_lines = []
    for i, track in enumerate(queue, start=1):
        message_lines.append(f"{i}. {track['title']}")

    response = "\n".join(message_lines)
    await interaction.followup.send(f"📃 **예약된 목록:**\n{response}", ephemeral=True)

@bot.tree.command(name="종료", description="봇을 음성 채널에서 퇴장시킵니다")
async def slash_leave(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    vc = interaction.guild.voice_client
    if vc and vc.is_connected():
        await vc.disconnect()
        queues.pop(interaction.guild_id, None)
        current_tracks.pop(interaction.guild_id, None)
        skip_once_flag.pop(interaction.guild_id, None)
        await interaction.followup.send("👋 봇이 음성 채널에서 퇴장했어요.", ephemeral=True)
    else:
        await interaction.followup.send("❗ 봇이 현재 음성 채널에 있지 않아요.", ephemeral=True)

@bot.tree.command(name="명령어", description="사용 가능한 명령어 목록을 확인합니다")
async def slash_help(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    help_text = (
        "📖 **사용 가능한 명령어 목록:**\n\n"
        "🎵 `/재생 [검색어|링크]` - YouTube에서 음악을 검색하고 재생합니다\n"
        "➕ `/목록` - 예약된 노래 목록을 확인합니다\n"
        "⏭️ `/스킵` - 현재 재생 중인 곡을 스킵합니다\n"
        "👋 `/종료` - 봇이 음성 채널에서 퇴장합니다\n"
        "ℹ️ `/명령어` - 명령어 목록을 확인합니다\n"
    )

    await interaction.followup.send(help_text, ephemeral=True)


# ──────────────────── 봇 준비 이벤트 ────────────────────
@bot.event
async def on_ready():
    await bot.wait_until_ready()
    try:
        synced = await bot.tree.sync()
        print(f"✅ 슬래시 명령어 등록 완료: {len(synced)}개")
    except Exception as e:
        print(f"❌ 슬래시 명령어 등록 실패: {e}")
    print(f"✅ 봇 로그인: {bot.user}")


token = os.environ.get("BOT_TOKEN")

if token is None:
    print("오류: BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
else:
    bot.run(token)