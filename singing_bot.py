import os
import asyncio
import discord
from discord.ext import commands

# ✨✨✨ 실행 확인용 코드 ✨✨✨
print("="*50)
print(">>> 노래 봇 v4 (Cog 구조) 실행 중 <<<")
print("="*50)
# ✨✨✨ ✨✨✨ ✨✨✨ ✨✨✨

# ──────────────────── 기본 설정 ────────────────────
GUILD_ID = 453742755991126019 

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# commands.Bot을 상속받아 커스텀 봇 클래스 생성
class SingingBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    # 봇이 준비될 때 비동기적으로 필요한 설정을 하는 함수
    async def setup_hook(self):
        # music_cog.py 파일을 확장 모듈로 로드합니다.
        await self.load_extension("music_cog")
        print("🎵 music_cog 로드 완료")

        # ✨✨✨ 디버깅 코드 ✨✨✨
        # Cog가 로드된 후, 봇이 어떤 명령어들을 알고 있는지 확인합니다.
        commands_in_tree = self.tree.get_commands(guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
        print("-" * 50)
        print(f"동기화 전, bot.tree에서 찾은 명령어 수: {len(commands_in_tree)}")
        for cmd in commands_in_tree:
            print(f"  - 인식된 명령어: {cmd.name}")
        print("-" * 50)
        
        # 서버에 명령어를 동기화합니다.
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"✅ [{GUILD_ID}] 서버에 슬래시 명령어 {len(synced)}개 등록 완료")
        else:
            synced = await self.tree.sync()
            print(f"✅ 글로벌 슬래시 명령어 {len(synced)}개 등록 완료")

    async def on_ready(self):
        print(f"✅ 봇 로그인: {self.user}")

# 봇을 실행하는 메인 함수
async def main():
    try:
        with open("token.txt", "r") as f:
            token = f.read().strip()
        
        bot = SingingBot()
        print("봇을 시작합니다...")
        await bot.start(token)
    except FileNotFoundError:
        print("❌ 'token.txt' 파일을 찾을 수 없어요. 파일을 만들고 봇 토큰을 넣어주세요.")
    except Exception as e:
        print(f"❌ 봇 시작 중 오류 발생: {e}")

# 스크립트가 직접 실행될 때 main 함수를 호출
if __name__ == "__main__":
    asyncio.run(main())