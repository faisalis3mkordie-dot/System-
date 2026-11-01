import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import aiohttp
from flask import Flask
from threading import Thread
from collections import defaultdict, deque
import time
from datetime import timedelta

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
AI_ENABLED = False

FREE_AI_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/gpt-oss-120b:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "openai/gpt-oss-20b:free",
    "meta-llama/llama-3.2-3b-instruct:free",
]

async def ask_ai(prompt: str) -> str:
    if not OPENROUTER_API_KEY:
        return "❌ ما فيه مفتاح ذكاء اصطناعي مضبوط حالياً."

    last_error = None
    async with aiohttp.ClientSession() as session:
        for model in FREE_AI_MODELS:
            try:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "أنت بوت ديسكورد اسمك IT، ترد باللهجة العربية بشكل ودود ومختصر ومفيد.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 500,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    data = await resp.json()
                    if resp.status != 200:
                        print(f"OpenRouter error on {model} (status {resp.status}): {data}")
                        last_error = data.get("error", {}).get("message", str(data))
                        continue
                    try:
                        return data["choices"][0]["message"]["content"].strip()
                    except (KeyError, IndexError):
                        last_error = "تعذر فهم رد الذكاء الاصطناعي"
                        continue
            except Exception as e:
                print(f"OpenRouter exception on {model}: {e}")
                last_error = str(e)
                continue

    return f"❌ كل النماذج المجانية مشغولة حالياً، جرب بعد شوي. ({last_error})"

app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"

def run():
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)
OWNER_ID = 1128794542385147986
CO_OWNER_IDS = {1282065589895954463}
BROADCAST_OWNER_ID = 1282065589895954463

CO_OWNERS = {}
DELAY = 0.05
BROADCAST_CONCURRENCY = 12
BROADCAST_MIN_INTERVAL = 0.025
BROADCAST_MAX_ATTEMPTS = 3
BLACKLIST = {".euo."}

# ── Anti-Raid Config ──
antiraid_enabled = defaultdict(bool)
join_times = defaultdict(deque)
RAID_JOIN_LIMIT = 10
RAID_TIME_WINDOW = 10
raid_triggered = defaultdict(bool)

def is_authorized(ctx):
    return ctx.author.id == OWNER_ID or ctx.author.id in CO_OWNER_IDS or ctx.author.name in CO_OWNERS

def is_authorized_interaction(interaction):
    return interaction.user.id == OWNER_ID or interaction.user.id in CO_OWNER_IDS or interaction.user.name in CO_OWNERS

def has_administrator_permission(member: discord.Member) -> bool:
    return (
        member.id == OWNER_ID
        or member.id in CO_OWNER_IDS
        or member.guild_permissions.administrator
    )

def can_manage_ranks(member: discord.Member) -> bool:
    return has_administrator_permission(member)

async def notify_owners(bot, msg):
    for uid in [OWNER_ID] + list(CO_OWNER_IDS):
        try:
            u = await bot.fetch_user(uid)
            await u.send(msg)
        except:
            pass

@bot.event
async def on_ready():
    bot.tree.clear_commands(guild=None)
    bot.tree.add_command(antiraid)
    bot.tree.add_command(show_all_rooms)
    await bot.tree.sync()
    print(f'✅ Logged in as: {bot.user.name}')
    print(f'✅ تم مسح كل الأوامر القديمة والإبقاء على /antiraid فقط')
    await bot.change_presence(activity=discord.Game(name="!bc للإرسال"))
    try:
        await bot.user.edit(username="IT System")
        print("✅ تم تغيير اسم البوت إلى IT System")
    except Exception as e:
        print(f"⚠️ ما قدر يغير اسم البوت: {e}")

@bot.event
async def on_command_error(ctx, error):
    print(f"Command error: {error}")
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ استخدم: `!bc all رسالتك` أو `!bc online رسالتك` أو `!bc offline رسالتك`")
    else:
        await ctx.send(f"❌ خطأ: {error}")

# ── Anti-Raid: تتبع الانضمامات ──
@bot.event
async def on_member_join(member):
    guild = member.guild
    if not antiraid_enabled[guild.id]:
        return

    now = time.time()
    q = join_times[guild.id]
    q.append(now)

    while q and now - q[0] > RAID_TIME_WINDOW:
        q.popleft()

    if len(q) >= RAID_JOIN_LIMIT and not raid_triggered[guild.id]:
        raid_triggered[guild.id] = True
        await handle_raid(guild)

async def handle_raid(guild):
    now = time.time()
    recent_members = [
        m for m in guild.members
        if not m.bot and (now - m.joined_at.timestamp()) <= RAID_TIME_WINDOW
    ]

    kicked = 0
    for member in recent_members:
        try:
            await member.kick(reason="🛡️ حماية ضد الرايد - انضمام مشبوه")
            kicked += 1
        except:
            pass

    try:
        await guild.edit(verification_level=discord.VerificationLevel.highest)
    except:
        pass

    owner = await bot.fetch_user(OWNER_ID)
    if owner:
        await owner.send(
            f"🚨 **تم اكتشاف رايد في سيرفر: {guild.name}!**\n"
            f"تم كيك **{kicked}** عضو مشبوه.\n"
            f"تم رفع مستوى التحقق إلى الأعلى.\n"
            f"استخدم `/antiraid unlock` لفتح السيرفر."
        )

    asyncio.create_task(auto_unlock(guild))

async def auto_unlock(guild):
    await asyncio.sleep(300)
    try:
        await guild.edit(verification_level=discord.VerificationLevel.low)
    except:
        pass
    raid_triggered[guild.id] = False
    join_times[guild.id].clear()
    owner = await bot.fetch_user(OWNER_ID)
    if owner:
        await owner.send(f"✅ تم فتح السيرفر **{guild.name}** تلقائياً بعد 5 دقائق.")

# ── Slash Command: /show-all-rooms-in-categories ──
@bot.tree.command(name="show-all-rooms-in-categories", description="تفعيل رؤية الرومات لـ everyone في كاتيقوري معينة")
@app_commands.describe(category="اختر الكاتيقوري")
async def show_all_rooms(interaction: discord.Interaction, category: discord.CategoryChannel):
    if not is_authorized_interaction(interaction):
        return await interaction.response.send_message("❌ ما عندك صلاحية!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    everyone = interaction.guild.default_role
    success = 0
    failed = 0

    for channel in category.channels:
        try:
            await channel.set_permissions(everyone, view_channel=True)
            success += 1
        except:
            failed += 1

    await interaction.followup.send(
        f"✅ تم تفعيل الرؤية لـ {success} روم في كاتيقوري **{category.name}**"
        + (f"\n❌ فشل: {failed} روم" if failed else ""),
        ephemeral=True
    )

# ── Slash Command: /antiraid ──
@bot.tree.command(name="antiraid", description="نظام الحماية من الرايد")
@app_commands.describe(action="اختر الإجراء")
@app_commands.choices(action=[
    app_commands.Choice(name="تفعيل الحماية", value="on"),
    app_commands.Choice(name="إيقاف الحماية", value="off"),
    app_commands.Choice(name="فتح السيرفر يدوياً", value="unlock"),
    app_commands.Choice(name="عرض الحالة", value="status"),
])
async def antiraid(interaction: discord.Interaction, action: str):
    if not is_authorized_interaction(interaction):
        return await interaction.response.send_message("❌ هذا الامر فقط لصاحب البوت ول @b0pm", ephemeral=True)

    guild_id = interaction.guild.id

    if action == "on":
        antiraid_enabled[guild_id] = True
        await interaction.response.send_message("🛡️ تم تفعيل نظام الحماية من الرايد!")

    elif action == "off":
        antiraid_enabled[guild_id] = False
        await interaction.response.send_message("🔓 تم إيقاف نظام الحماية من الرايد.")

    elif action == "unlock":
        raid_triggered[guild_id] = False
        join_times[guild_id].clear()
        try:
            await interaction.guild.edit(verification_level=discord.VerificationLevel.low)
        except:
            pass
        await interaction.response.send_message("✅ تم فتح السيرفر وإعادة تعيين نظام الحماية.")

    elif action == "status":
        status = "✅ مفعّل" if antiraid_enabled[guild_id] else "❌ موقوف"
        triggered = "⚠️ نعم، السيرفر مقفل حالياً!" if raid_triggered[guild_id] else "لا"
        await interaction.response.send_message(
            f"🛡️ **حالة نظام الحماية من الرايد:**\n"
            f"الحالة: {status}\n"
            f"رايد نشط: {triggered}\n"
            f"الحد: {RAID_JOIN_LIMIT} انضمامات خلال {RAID_TIME_WINDOW} ثواني"
        )

# ── Helper: تحويل المدة ──
def parse_duration(duration_str):
    units = {'s': 'seconds', 'm': 'minutes', 'h': 'hours', 'd': 'days'}
    try:
        unit = duration_str[-1].lower()
        amount = int(duration_str[:-1])
        if unit not in units:
            return None
        return timedelta(**{units[unit]: amount})
    except:
        return None

# ── دوال العقوبات والإدارة ──
async def do_timeout(ctx, member: discord.Member, duration: str, reason: str = "بدون سبب"):
    author = ctx.author
    if not has_administrator_permission(author):
        return await ctx.send("❌ ما عندك صلاحية تايم اوت! (مخصصة للسترتر)")

    delta = parse_duration(duration)
    if not delta:
        return await ctx.send("❌ المدة غلط! استخدم مثلاً: `1m` `1h` `1d`")

    if delta.total_seconds() > 60 * 60 * 24 * 28:
        return await ctx.send("❌ الحد الأقصى للتايم اوت هو 28 يوم!")

    try:
        await member.timeout(delta, reason=reason)
        labels = {'s': 'ثانية', 'm': 'دقيقة', 'h': 'ساعة', 'd': 'يوم'}
        unit_label = labels.get(duration[-1].lower(), '')
        await ctx.send(f"🔇 تم إسكات {member.mention} لمدة {duration[:-1]} {unit_label} | السبب: {reason}")

        log_msg = f"""🔇 **تايم اوت جديد**
👤 العضو: {member.mention} (`{member}`)
⏱️ المدة: {duration[:-1]} {unit_label}
📝 السبب: {reason}
🛡️ بواسطة: {ctx.author.mention} (`{ctx.author}`)
🏠 السيرفر: {ctx.guild.name}"""
        await notify_owners(bot, log_msg)

    except discord.Forbidden:
        await ctx.send("❌ ما عندي صلاحية أسكت هذا العضو! (تأكد أن رتبة البوت أعلى من العضو)")
    except Exception as e:
        await ctx.send(f"❌ خطأ: {e}")

async def do_warn(ctx, member: discord.Member, reason: str = "بدون سبب"):
    if not has_administrator_permission(ctx.author):
        return await ctx.send("❌ ما عندك صلاحية تحذير! (مخصصة للسترتر)")
    try:
        await ctx.send(f"⚠️ تم تحذير {member.mention} | السبب: {reason}")
        log_msg = f"""⚠️ **تحذير جديد**
👤 العضو: {member.mention} (`{member}`)
📝 السبب: {reason}
🛡️ بواسطة: {ctx.author.mention} (`{ctx.author}`)
🏠 السيرفر: {ctx.guild.name}"""
        await notify_owners(bot, log_msg)
    except Exception as e:
        await ctx.send(f"❌ خطأ: {e}")

TIMEOUT_TRIGGERS = ["تايم", "ميوت", "اسكات", "اسكت", "كل تبن", "كل زق"]
WARN_TRIGGERS = ["تحذير", "انذار"]
BAN_TRIGGERS = ["تف", "برا", "انقلع", "لف", "L", "مالديف", "خختفو", "شد"]

async def do_temp_ban(ctx, member: discord.Member, duration: str = None, reason: str = "بدون سبب"):
    if not has_administrator_permission(ctx.author):
        return await ctx.send("❌ ما عندك صلاحية باند! (مخصصة للسترتر)")

    labels = {'s': 'ثانية', 'm': 'دقيقة', 'h': 'ساعة', 'd': 'يوم'}
    delta = parse_duration(duration) if duration else None
    duration_label = f"{duration[:-1]} {labels.get(duration[-1].lower(), '')}" if delta else "دائم"

    try:
        await member.ban(reason=f"{reason} | بواسطة {ctx.author}")
        await ctx.send(f"🔨 تم باند {member.mention} | المدة: {duration_label} | السبب: {reason}")

        log_msg = f"""🔨 **باند جديد**
👤 العضو: {member} (`{member.id}`)
⏱️ المدة: {duration_label}
📝 السبب: {reason}
🛡️ بواسطة: {ctx.author.mention} (`{ctx.author}`)
🏠 السيرفر: {ctx.guild.name}"""
        await notify_owners(bot, log_msg)

        if delta:
            await asyncio.sleep(delta.total_seconds())
            try:
                await ctx.guild.unban(member, reason="انتهت مدة الباند")
            except:
                pass

    except discord.Forbidden:
        await ctx.send("❌ ما عندي صلاحية أباند هذا العضو! (تأكد أن رتبة البوت أعلى من العضو)")
    except Exception as e:
        await ctx.send(f"❌ خطأ: {e}")

async def do_unban(ctx, query: str):
    if not has_administrator_permission(ctx.author):
        return await ctx.send("❌ ما عندك صلاحية! (مخصصة للسترتر)")
    try:
        bans = [entry async for entry in ctx.guild.bans()]
        user = None
        for entry in bans:
            if str(entry.user.id) == query or entry.user.name.lower() == query.lower():
                user = entry.user
                break
        if not user:
            return await ctx.send(f"❌ ما لقيت يوزر بالاسم أو الـ ID: `{query}`")
        await ctx.guild.unban(user, reason=f"فك البان بواسطة {ctx.author}")
        await ctx.send(f"✅ تم فك البان عن **{user}**")
        
        log_msg = f"""✅ **فك بان**
👤 العضو: {user} (`{user.id}`)
🛡️ بواسطة: {ctx.author.mention}
🏠 السيرفر: {ctx.guild.name}"""
        await notify_owners(bot, log_msg)
    except discord.Forbidden:
        await ctx.send("❌ ما عندي صلاحية أفك البان!")
    except Exception as e:
        await ctx.send(f"❌ خطأ: {e}")

async def do_untimeout(ctx, member: discord.Member, reason: str):
    if not has_administrator_permission(ctx.author):
        return await ctx.send("❌ ما عندك صلاحية! (مخصصة للسترتر)")
    try:
        await member.timeout(None, reason=reason)
        await ctx.send(f"✅ تم شيل التايم اوت عن {member.mention} | السبب: {reason}")

        log_msg = f"""✅ **تم شيل التايم اوت**
👤 العضو: {member.mention} (`{member}`)
📝 السبب: {reason}
🛡️ بواسطة: {ctx.author.mention} (`{ctx.author}`)
🏠 السيرفر: {ctx.guild.name}"""
        await notify_owners(bot, log_msg)
    except discord.Forbidden:
        await ctx.send("❌ ما عندي صلاحية أشيل التايم اوت!")
    except Exception as e:
        await ctx.send(f"❌ خطأ: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()

    if bot.user in message.mentions and not message.mention_everyone:
        stripped = content
        for mstr in (f"<@{bot.user.id}>", f"<@!{bot.user.id}>"):
            stripped = stripped.replace(mstr, "").strip()
        if not stripped:
            await message.channel.send("هلا انا موجود")
            return
        if not AI_ENABLED:
            await message.reply("الذكاء الاصطناعي متوقف حاليًا.", mention_author=False)
            return
        else:
            async with message.channel.typing():
                reply = await ask_ai(stripped)
            await message.reply(reply, mention_author=False)
            return

    if content == "شيل" or content.startswith("شيل ") or content.startswith("شيل<"):
        rest = content[len("شيل"):].strip()
        parts = rest.split()
        if message.mentions:
            member = message.mentions[0]
            reason = " ".join(parts[1:]) if len(parts) > 1 else "بدون سبب"
            ctx = await bot.get_context(message)
            await do_untimeout(ctx, member, reason)
            return

    if content == "قفل" or content == "ق" or content.startswith("قفل ") or content.startswith("ق "):
        author_member = message.guild.get_member(message.author.id) or await message.guild.fetch_member(message.author.id)
        is_allowed = (
            message.author.id == OWNER_ID
            or (author_member and author_member.guild_permissions.administrator)
        )
        if not is_allowed:
            await message.channel.send("❌ ما عندك صلاحية قفل الروم (تتطلب ادمنستريتر)!")
            return
        target = message.channel_mentions[0] if message.channel_mentions else message.channel
        overwrite = target.overwrites_for(message.guild.default_role)
        overwrite.send_messages = False
        try:
            await target.set_permissions(message.guild.default_role, overwrite=overwrite)
            await message.channel.send(f"🔒 تم قفل {target.mention}")
        except discord.Forbidden:
            await message.channel.send("❌ ما عندي صلاحية أقفل هذا الروم!")
        except Exception as e:
            await message.channel.send(f"❌ خطأ: {e}")
        return

    if content == "فتح" or content == "ف" or content.startswith("فتح ") or content.startswith("ف "):
        author_member = message.guild.get_member(message.author.id) or await message.guild.fetch_member(message.author.id)
        is_allowed = (
            message.author.id == OWNER_ID
            or (author_member and author_member.guild_permissions.administrator)
        )
        if not is_allowed:
            await message.channel.send("❌ ما عندك صلاحية فتح الروم (تتطلب ادمنستريتر)!")
            return
        target = message.channel_mentions[0] if message.channel_mentions else message.channel
        overwrite = target.overwrites_for(message.guild.default_role)
        overwrite.send_messages = True
        try:
            await target.set_permissions(message.guild.default_role, overwrite=overwrite)
            await message.channel.send(f"🔓 تم فتح {target.mention}")
        except discord.Forbidden:
            await message.channel.send("❌ ما عندي صلاحية أفتح هذا الروم!")
        except Exception as e:
            await message.channel.send(f"❌ خطأ: {e}")
        return

    if content.startswith("اعطي كل الرولات"):
        if message.author.id != OWNER_ID and message.author.name not in CO_OWNERS:
            await message.channel.send("❌ هذا الأمر لصاحب البوت ونائبه فقط!")
            return
        if not message.mentions:
            await message.channel.send("❌ منشن العضو!")
            return
        member = message.mentions[0]
        bot_member = message.guild.get_member(bot.user.id)
        bot_top = bot_member.top_role.position if bot_member else 0
        assignable = [
            r for r in message.guild.roles
            if r.position < bot_top
            and not r.managed
            and r.name != "@everyone"
            and r not in member.roles
        ]
        if not assignable:
            await message.channel.send(f"❌ ما في رولات ممكن أعطيها لـ {member.mention}")
            return
        try:
            all_roles = list(set(member.roles + assignable))
            await member.edit(roles=all_roles)
            await message.channel.send(f"✅ تم إعطاء {member.mention} جميع الرولات ({len(assignable)} رول)")
        except discord.Forbidden:
            await message.channel.send("❌ ما عندي صلاحية أعطي بعض الرولات! (تأكد أن رتبة البوت أعلى من الرتب)")
        except Exception as e:
            await message.channel.send(f"❌ خطأ: {e}")
        return

    if content.startswith("تخفيض"):
        if not message.mentions:
            await message.channel.send("❌ لازم تمنشن العضو! مثال: `تخفيض @العضو 1`")
            return
        member = message.mentions[0]
        author_member = message.guild.get_member(message.author.id)
        if not author_member or not can_manage_ranks(author_member):
            await message.channel.send("❌ ما عندك صلاحية تخفيض!")
            return
        rest = content[len("تخفيض"):].strip()
        parts = [p for p in rest.split() if not p.startswith('<@')]
        steps = 1
        if parts:
            try:
                steps = int(parts[0])
            except:
                steps = 1
        bot_member = message.guild.get_member(bot.user.id)
        bot_top_position = bot_member.top_role.position if bot_member else 0
        member_top = member.top_role
        if member_top.managed or member_top.position >= bot_top_position:
            await message.channel.send("❌ ما أقدر أخفض هذا العضو لأن رتبته أعلى من رتبة البوت أو مساوية لها! ارفع رتبة البوت فوقه.")
            return

        eligible = sorted(
            [
                role
                for role in member.roles
                if role.name != "@everyone"
                and not role.managed
                and role.position < bot_top_position
            ],
            key=lambda role: role.position,
            reverse=True,
        )
        if not eligible:
            await message.channel.send(f"❌ {member.mention} ما عنده رتب تقدر تنزلها!")
            return
        to_remove = eligible[:steps]
        try:
            await member.remove_roles(*to_remove)
            names = " ← ".join(r.name for r in to_remove)
            await message.channel.send(f"⬇️ تم تخفيض {member.mention} بـ {len(to_remove)} رتبة: **{names}**")
        except discord.Forbidden:
            await message.channel.send("❌ ما عندي صلاحية أخفض هذا العضو! (تأكد أن رتبة البوت أعلى من رتبته)")
        except Exception as e:
            await message.channel.send(f"❌ خطأ: {e}")
        return

    if content.startswith("ترقية") or content.startswith("ترقيه"):
        trigger = "ترقية" if content.startswith("ترقية") else "ترقيه"
        if not message.mentions:
            await message.channel.send("❌ لازم تمنشن العضو! مثال: `ترقية @العضو 1`")
            return
        member = message.mentions[0]
        author_member = message.guild.get_member(message.author.id)
        if not author_member or not can_manage_ranks(author_member):
            await message.channel.send("❌ ما عندك صلاحية ترقية!")
            return
        rest = content[len(trigger):].strip()
        parts = [p for p in rest.split() if not p.startswith('<@')]
        steps = 1
        if parts:
            try:
                steps = int(parts[0])
            except:
                steps = 1
        bot_member = message.guild.get_member(bot.user.id)
        bot_top_position = bot_member.top_role.position if bot_member else 0
        sorted_roles = sorted(message.guild.roles, key=lambda r: r.position)
        member_top = member.top_role
        
        eligible = [r for r in sorted_roles if r.position > member_top.position and r.position < bot_top_position and not r.managed and r.name != "@everyone"]
        if not eligible:
            await message.channel.send(f"❌ {member.mention} وصل أعلى رتبة ممكنة أو أن رتبة البوت أدنى من الرتب المطلوبة!")
            return
        to_add = eligible[:steps]
        try:
            await member.add_roles(*to_add)
            names = " ← ".join(r.name for r in to_add)
            await message.channel.send(f"⬆️ تمت ترقية {member.mention} بـ {len(to_add)} رتبة: **{names}**")
        except discord.Forbidden:
            await message.channel.send("❌ ما عندي صلاحية أرقي هذا العضو! (يجب أن تكون رتبة البوت أعلى من الرتبة المراد إعطاؤها وعليها صلاحية إدارة الرتب)")
        except Exception as e:
            await message.channel.send(f"❌ خطأ: {e}")
        return

    if content.startswith("رول") or (content.startswith("ر ") or content == "ر"):
        trigger = "رول" if content.startswith("رول") else "ر"
        rest = content[len(trigger):].strip()
        parts = rest.split()
        if message.mentions and len(parts) >= 2:
            member = message.mentions[0]
            role_name = " ".join(parts[1:])
            author_member = message.guild.get_member(message.author.id)
            
            is_allowed_give = (
                author_member.id == OWNER_ID 
                or author_member.guild_permissions.administrator 
                or author_member.guild_permissions.manage_roles
            )
            
            if not is_allowed_give:
                await message.channel.send("❌ ما عندك صلاحية إعطاء رولات!")
                return
                
            role = None
            if role_name.isdigit():
                role = message.guild.get_role(int(role_name))
            if not role:
                role = discord.utils.find(lambda r: role_name.lower() in r.name.lower(), message.guild.roles)
            if not role:
                await message.channel.send(f"❌ ما لقيت رول: **{role_name}**")
                return
            try:
                await member.add_roles(role)
                await message.channel.send(f"✅ تم إعطاء {member.mention} رول **{role.name}**")
            except discord.Forbidden:
                await message.channel.send("❌ ما عندي صلاحية أعطي هذا الرول! (رتبة البوت أدنى من الرول)")
            except Exception as e:
                await message.channel.send(f"❌ خطأ: {e}")
            return

    if content.startswith("نك"):
        rest = content[len("نك"):].strip()
        parts = rest.split()
        if message.mentions and len(parts) >= 2:
            member = message.mentions[0]
            new_nick = " ".join(parts[1:])
            ctx = await bot.get_context(message)
            if not (ctx.author.guild_permissions.manage_nicknames or ctx.author.id == OWNER_ID):
                await message.channel.send("❌ ما عندك صلاحية تغيير النيك نيم بالرول!")
                return
            try:
                await member.edit(nick=new_nick)
                await message.channel.send(f"✅ تم تغيير نيك نيم {member.mention} إلى **{new_nick}**")
            except discord.Forbidden:
                await message.channel.send("❌ ما عندي صلاحية أغير نيك نيم هذا العضو!")
            except Exception as e:
                await message.channel.send(f"❌ خطأ: {e}")
            return

    if content == "فك" or content.startswith("فك ") or content.startswith("فك<"):
        rest = content[len("فك"):].strip()
        parts = rest.split()
        if parts:
            ctx = await bot.get_context(message)
            await do_unban(ctx, parts[0])
            return

    for trigger in TIMEOUT_TRIGGERS:
        if content == trigger or content.startswith(trigger + " ") or content.startswith(trigger + "<"):
            if not message.mentions:
                await message.channel.send("❌ لازم تمنشن العضو! مثال: `تايم @العضو 1m`")
                return
            member = message.mentions[0]
            rest = content[len(trigger):].strip()
            parts = [p for p in rest.split() if not p.startswith('<@')]
            duration = "5m"
            reason = "بدون سبب"
            if parts:
                if parse_duration(parts[0]):
                    duration = parts[0]
                    reason = " ".join(parts[1:]) if len(parts) > 1 else "بدون سبب"
                else:
                    reason = " ".join(parts)
            ctx = await bot.get_context(message)
            await do_timeout(ctx, member, duration, reason)
            return

    for trigger in WARN_TRIGGERS:
        if content == trigger or content.startswith(trigger + " ") or content.startswith(trigger + "<"):
            if not message.mentions:
                await message.channel.send("❌ لازم تمنشن العضو! مثال: `تحذير @العضو السبب`")
                return
            member = message.mentions[0]
            rest = content[len(trigger):].strip()
            parts = [p for p in rest.split() if not p.startswith('<@')]
            reason = " ".join(parts) if parts else "بدون سبب"
            ctx = await bot.get_context(message)
            await do_warn(ctx, member, reason)
            return

    for trigger in BAN_TRIGGERS:
        if content == trigger or content.startswith(trigger + " ") or content.startswith(trigger + "<"):
            if not message.mentions:
                await message.channel.send("❌ لازم تمنشن العضو اللي تبي تبنّه!")
                return
            member = message.mentions[0]
            rest = content[len(trigger):].strip()
            parts = [p for p in rest.split() if not p.startswith('<@')]
            duration = None
            reason = "بدون سبب"
            if parts:
                if parse_duration(parts[0]):
                    duration = parts[0]
                    reason = " ".join(parts[1:]) if len(parts) > 1 else "بدون سبب"
                else:
                    reason = " ".join(parts)
            ctx = await bot.get_context(message)
            await do_temp_ban(ctx, member, duration, reason)
            return

    await bot.process_commands(message)

async def send_dm(member, message, results, rate_limiter):
    payload = f"{message}\n{member.mention}"

    for attempt in range(BROADCAST_MAX_ATTEMPTS):
        try:
            await rate_limiter.wait()
            await member.send(payload)
            results['success'] += 1
            return
        except discord.Forbidden:
            results['failed'].append(member)
            return
        except discord.HTTPException as error:
            retryable = error.status == 429 or error.status >= 500
            if not retryable or attempt == BROADCAST_MAX_ATTEMPTS - 1:
                results['failed'].append(member)
                return

            retry_after = getattr(error, "retry_after", None)
            backoff = 2 ** attempt
            wait_seconds = min(float(retry_after or backoff), 15.0)
            await asyncio.sleep(wait_seconds)
        except (asyncio.TimeoutError, OSError):
            if attempt == BROADCAST_MAX_ATTEMPTS - 1:
                results['failed'].append(member)
                return
            await asyncio.sleep(2 ** attempt)
        except Exception:
            results['failed'].append(member)
            return


class BroadcastRateLimiter:
    def __init__(self, min_interval):
        self.min_interval = min_interval
        self.lock = asyncio.Lock()
        self.next_request_at = 0.0

    async def wait(self):
        async with self.lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait_for = max(0.0, self.next_request_at - now)
            self.next_request_at = max(now, self.next_request_at) + self.min_interval
        if wait_for:
            await asyncio.sleep(wait_for)


async def broadcast_worker(queue, message, results, rate_limiter):
    while True:
        member = await queue.get()
        try:
            if member is None:
                return
            await send_dm(member, message, results, rate_limiter)
        finally:
            queue.task_done()

@bot.command()
async def leaveall(ctx):
    if not is_authorized(ctx):
        return await ctx.send("❌ هذا الامر فقط لصاحب البوت ول @b0pm")
    await ctx.send(f"👋 جاري مغادرة {len(bot.guilds)} سيرفر...")
    for guild in list(bot.guilds):
        try:
            await guild.leave()
        except:
            pass

@bot.command(name="اطلع")
async def leave_current_guild(ctx):
    if not is_authorized(ctx):
        return await ctx.send("❌ هذا الأمر فقط لصاحب البوت ونائبه.")
    if ctx.guild is None:
        return await ctx.send("❌ استخدم هذا الأمر داخل سيرفر.")

    guild = ctx.guild
    await ctx.send(f"👋 بطلع من السيرفر **{guild.name}** الآن.")
    try:
        await guild.leave()
    except discord.Forbidden:
        await ctx.send("❌ ما قدرت أطلع من هذا السيرفر.")
    except discord.HTTPException:
        await ctx.send("❌ صار خطأ مؤقت أثناء مغادرة السيرفر.")

def can_broadcast(ctx):
    return ctx.author.id == OWNER_ID or ctx.author.id == BROADCAST_OWNER_ID

@bot.command(name="يوزر")
async def suggest_usernames(ctx, count: int = 30):
    import random, string
    chars = string.ascii_letters + string.digits
    seps = ['.', '_']
    pool = set()

    for _ in range(3000):
        base = ''.join(random.choices(chars, k=3))
        sep = random.choice(seps)
        pos = random.randint(0, 3)
        name = base[:pos] + sep + base[pos:]
        pool.add(name)

    picked = random.sample(list(pool), min(count, len(pool)))
    picked.sort()

    lines = "\n".join(f"`{s}`" for s in picked)
    await ctx.send(f"💎 **{len(picked)} يوزر شبه ثلاثي:**\n{lines}")

@bot.command(name="بحث")
async def search_three(ctx):
    await ctx.send("🔍 جاري البحث عن يوزرات ثلاثية...")
    results = []
    for member in ctx.guild.members:
        name = member.name
        clean = name.replace('.', '').replace('_', '')
        specials = [c for c in name if c in ('.', '_')]
        if len(clean) == 3 and len(specials) <= 1:
            results.append(f"⭐ `{name}` — {member.mention}")

    if not results:
        return await ctx.send("❌ ما لقيت يوزرات ثلاثية")

    chunks = []
    chunk = ""
    for line in results:
        if len(chunk) + len(line) + 1 > 1900:
            chunks.append(chunk)
            chunk = line + "\n"
        else:
            chunk += line + "\n"
    if chunk:
        chunks.append(chunk)

    await ctx.send(f"📋 وجدت **{len(results)}** يوزر ثلاثي:")
    for c in chunks:
        await ctx.send(c)

@bot.command()
async def bc(ctx, mode: str, *, message):
    if not can_broadcast(ctx):
        return await ctx.send("❌ هذا الأمر مخصص لصاحب البوت ونائبه فقط.")

    message = message.strip()
    if not message:
        return await ctx.send("❌ اكتب الرسالة التي تريد إرسالها.")
    if len(message) > 1900:
        return await ctx.send("❌ الرسالة طويلة جدًا. الحد الأقصى 1900 حرف.")

    mode = mode.lower()

    if mode == "all":
        targets = [m for m in ctx.guild.members if not m.bot and m.name not in BLACKLIST]
        label = "كل الأعضاء (متصل وغير متصل)"
    elif mode == "online":
        targets = [m for m in ctx.guild.members if not m.bot and m.status != discord.Status.offline and m.name not in BLACKLIST]
        label = "الأعضاء المتصلين فقط"
    elif mode == "offline":
        targets = [m for m in ctx.guild.members if not m.bot and m.status == discord.Status.offline and m.name not in BLACKLIST]
        label = "الأعضاء غير المتصلين فقط"
    else:
        return await ctx.send("❌ الوضع غير صحيح! استخدم: `!bc all` أو `!bc online` أو `!bc offline`")

    await ctx.send(f"🚀 جاري الإرسال لـ {len(targets)} عضو ({label})...")

    results = {'success': 0, 'failed': []}
    rate_limiter = BroadcastRateLimiter(BROADCAST_MIN_INTERVAL)
    queue = asyncio.Queue()
    for member in targets:
        await queue.put(member)
    for _ in range(min(BROADCAST_CONCURRENCY, max(1, len(targets)))):
        await queue.put(None)

    workers = [
        asyncio.create_task(broadcast_worker(queue, message, results, rate_limiter))
        for _ in range(min(BROADCAST_CONCURRENCY, max(1, len(targets))))
    ]
    await queue.join()
    await asyncio.gather(*workers)

    await ctx.send(f"✅ تم الانتهاء! وصل لـ {results['success']} عضو. فشل: {len(results['failed'])}.")

    if results['failed']:
        mentions = " ".join(m.mention for m in results['failed'])
        chunks = [mentions[i:i+1900] for i in range(0, len(mentions), 1900)]
        for chunk in chunks:
            await ctx.send(f"❌ الأعضاء اللي ما وصلهم الرسالة:\n{chunk}")

if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if not TOKEN:
        raise ValueError("❌ DISCORD_TOKEN environment variable is not set!")
    bot.run(TOKEN)
