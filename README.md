# 🎵 singing-bot

디스코드 음성 채널에서 유튜브 음악을 재생하는 봇입니다. 슬래시 명령어로 조작합니다.

## 명령어

| 명령어 | 설명 |
| --- | --- |
| `/재생 <검색어 또는 YouTube 링크>` | 노래를 검색해 재생합니다. 재생 중이면 대기열에 추가합니다. |
| `/스킵` | 현재 곡을 건너뜁니다. |
| `/반복` | 현재 곡 반복 재생을 켜거나 끕니다. |
| `/자동재생` | 대기열이 비면 비슷한 노래를 자동으로 이어서 재생합니다. |
| `/목록` | 예약된 노래 목록을 확인합니다. |
| `/종료` | 봇을 음성 채널에서 내보냅니다. |
| `/명령어` | 사용 가능한 명령어를 확인합니다. |

## 동작 방식

- `yt-dlp`로 유튜브에서 오디오 스트림 주소를 가져오고, FFmpeg로 음성 채널에 재생합니다.
- 서버(길드)마다 대기열, 반복, 자동재생 상태를 따로 관리합니다.
- 자동재생은 방금 재생한 곡의 유튜브 믹스 목록에서 다음 곡을 고릅니다.
- 재생할 곡이 없으면 음성 채널에서 자동으로 나갑니다.
- 음악 기능은 `music_cog.py`에 Cog로 분리했습니다.

## 기술 스택

Python, discord.py, yt-dlp, FFmpeg

## 실행 방법

Python 3.10 이상과 [FFmpeg](https://ffmpeg.org/download.html)가 필요합니다.

```bash
pip install discord.py PyNaCl yt-dlp
```

1. [Discord Developer Portal](https://discord.com/developers/applications)에서 봇을 만들고 토큰을 발급받습니다.
2. 프로젝트 폴더에 `token.txt` 파일을 만들고 토큰을 넣습니다. 이 파일은 `.gitignore`에 등록돼 있어 저장소에 올라가지 않습니다.
3. `singing_bot.py`의 `GUILD_ID`를 봇을 사용할 서버 ID로 바꿉니다.
4. 봇을 실행합니다.

```bash
python singing_bot.py
```
