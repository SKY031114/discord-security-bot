import discord
from discord.ext import commands
import datetime
import re
import os

# 1. 인텐트 설정 (메시지 내용 읽기 필수)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 📌 로그 채널 ID
LOG_CHANNEL_ID = 1555532609524858982  

# 📌 금지어 목록 ("씨발" 및 주요 욕설 포함)
BAD_WORDS = [
    "씨발", "시발", "씨바", "시바", "씨팔", "시팔", 
    "개새끼", "병신", "존나", "지랄", "꺼져", "미친놈"
]

# 유저별 도배 방지 기록
user_message_timestamps = {}
SPAM_THRESHOLD_COUNT = 5   # 제한 메시지 수
SPAM_THRESHOLD_TIME = 5    # 제한 시간 (초)

# --- 로그 전송 전용 함수 ---
async def send_security_log(guild: discord.Guild, author: discord.User, reason: str, content: str, channel_id: int):
    """보안 감지 내역을 지정된 관리자 로그 채널로 Embed 전송"""
    if not LOG_CHANNEL_ID:
        return

    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        print(f"[경고] 로그 채널 ID({LOG_CHANNEL_ID})를 찾을 수 없습니다.")
        return

    embed = discord.Embed(
        title="🚨 보안 필터링 감지 보고서",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="👤 대상 유저", value=f"{author.mention} (`{author.name}` / ID: `{author.id}`)", inline=False)
    embed.add_field(name="📌 감지 사유", value=f"`{reason}`", inline=True)
    embed.add_field(name="📍 발생 채널", value=f"<#{channel_id}>", inline=True)
    embed.add_field(name="💬 원본 메시지 내용", value=f"```{content if content else '내용 없음'}```", inline=False)
    embed.set_footer(text="서버 보안 모니터링 시스템")

    try:
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"[로그 전송 실패] {e}")


@bot.event
async def on_ready():
    print(f"✅ 보안 봇 온라인 완료: {bot.user.name} ({bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="서버 보안 감시 및 로그 기록 중"))


@bot.event
async def on_message(message: discord.Message):
    # 봇 메시지 무시
    if message.author.bot:
        return

    now = datetime.datetime.now()
    user_id = message.author.id
    clean_content = message.content.replace(" ", "")  # 띄어쓰기 제거 후 검사

    # -------------------------------------------------------------
    # [보안 1] 금지어 감지 ("씨발" 필터링 - 관리자 포함 전체 대상)
    # -------------------------------------------------------------
    for bad_word in BAD_WORDS:
        if bad_word in clean_content:
            try:
                await message.delete()
            except Exception as e:
                print(f"메시지 삭제 권한 부족: {e}")

            await message.channel.send(
                f"⚠️ {message.author.mention}님, 유해 단어가 포함되어 메시지가 삭제되었습니다.",
                delete_after=5
            )
            await send_security_log(
                guild=message.guild,
                author=message.author,
                reason=f"금지어 사용 ('{bad_word}')",
                content=message.content,
                channel_id=message.channel.id
            )
            return

    # -------------------------------------------------------------
    # [보안 2] 스팸/초대 링크 차단
    # -------------------------------------------------------------
    discord_invite_pattern = r"(discord\.gg|discord\.com/invite)/[a-zA-Z0-9]+"
    if re.search(discord_invite_pattern, message.content):
        try:
            await message.delete()
        except:
            pass

        await message.channel.send(
            f"🚫 {message.author.mention}님, 서버 초대 링크 홍보는 금지되어 있습니다.",
            delete_after=5
        )
        await send_security_log(
            guild=message.guild,
            author=message.author,
            reason="서버 초대 링크 유포",
            content=message.content,
            channel_id=message.channel.id
        )
        return

    # -------------------------------------------------------------
    # [보안 3] 메시지 도배 방지
    # -------------------------------------------------------------
    if user_id not in user_message_timestamps:
        user_message_timestamps[user_id] = []

    timestamps = [
        t for t in user_message_timestamps[user_id]
        if (now - t).total_seconds() < SPAM_THRESHOLD_TIME
    ]
    timestamps.append(now)
    user_message_timestamps[user_id] = timestamps

    if len(timestamps) >= SPAM_THRESHOLD_COUNT:
        try:
            await message.delete()
        except:
            pass

        await message.channel.send(
            f"🚨 {message.author.mention}님, 도배가 감지되었습니다. 천천히 채팅해 주세요!",
            delete_after=5
        )
        await send_security_log(
            guild=message.guild,
            author=message.author,
            reason=f"{SPAM_THRESHOLD_TIME}초 내 {SPAM_THRESHOLD_COUNT}개 이상 도배",
            content=message.content,
            channel_id=message.channel.id
        )
        return

    await bot.process_commands(message)


# -------------------------------------------------------------
# [관리자 명령어]
# -------------------------------------------------------------

# 메시지 삭제 (!청소 <개수>)
@bot.command(name="청소")
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, amount: int = 10):
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 메시지 {len(deleted) - 1}개를 정리했습니다.", delete_after=3)


# 타임아웃 부여 (!타임아웃 @유저 <일수> <사유>) - 최대 3일
@bot.command(name="타임아웃")
@commands.has_permissions(moderate_members=True)
async def timeout_member(ctx, member: discord.Member, days: int = 1, *, reason: str = "사유 없음"):
    if days < 1 or days > 3:
        await ctx.send("❌ 타임아웃 기간은 최소 1일, 최대 3일까지만 설정할 수 있습니다.", delete_after=5)
        return

    duration = datetime.timedelta(days=days)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"⏳ {member.mention} 님에게 {days}일 동안 타임아웃을 부여했습니다. (사유: {reason})")

    log_channel = ctx.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(
            title="🛑 수동 제재 보고서 (타임아웃)",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="👤 제재 대상", value=f"{member.mention} (`{member.name}`)", inline=False)
        embed.add_field(name="👮 담당 관리자", value=f"{ctx.author.mention}", inline=True)
        embed.add_field(name="⏱️ 제재 기간", value=f"`{days}일`", inline=True)
        embed.add_field(name="📌 제재 사유", value=f"`{reason}`", inline=False)
        await log_channel.send(embed=embed)


# 멤버 차단 (!차단 @유저 <사유>)
@bot.command(name="차단")
@commands.has_permissions(ban_members=True)
async def ban_member(ctx, member: discord.Member, *, reason: str = "사유 없음"):
    await member.ban(reason=reason)
    await ctx.send(f"⛔ {member.mention} 님이 차단되었습니다. (사유: {reason})")


# 권한 에러 처리
@clear_messages.error
@timeout_member.error
@ban_member.error
async def permission_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ 이 명령어를 사용할 권한이 없습니다.", delete_after=5)


TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
