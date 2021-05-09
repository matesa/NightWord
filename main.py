import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal, getcontext, ROUND_HALF_UP, InvalidOperation
from random import seed
from string import ascii_lowercase
from time import time
from typing import Dict, Any
from uuid import uuid4

import aiofiles
import aiofiles.os
from aiocache import cached
from aiogram import executor, types
from aiogram.types.message import ContentTypes
from aiogram.utils.exceptions import TelegramAPIError, BadRequest, MigrateToChat
from aiogram.utils.markdown import quote_html

from constants import (
    bot, on9bot, dp, VIP, VIP_GROUP, ADMIN_GROUP_ID, OFFICIAL_GROUP_ID, WORD_ADDITION_CHANNEL_ID,
    GAMES, pool, PROVIDER_TOKEN, GameState, GameSettings, update_words, ADD_TO_GROUP_KEYBOARD
)
from game import (
    ClassicGame, HardModeGame, ChaosGame, ChosenFirstLetterGame, BannedLettersGame,
    RequiredLetterGame, EliminationGame, MixedEliminationGame
)
from utils import send_admin_group, amt_donated, check_word_existence, has_star, filter_words

seed(time())
getcontext().rounding = ROUND_HALF_UP
build_time = datetime.now().replace(microsecond=0)
MAINT_MODE = False


async def private_only_command(message: types.Message) -> None:
    await message.reply("Lütfen bu komutu özel olarak kullanın.")


async def groups_only_command(message: types.Message) -> None:
    await message.reply("Bu komut yalnızca gruplarda kullanılabilir.", reply_markup=ADD_TO_GROUP_KEYBOARD)


@dp.message_handler(is_group=False, commands="start")
async def cmd_start(message: types.Message) -> None:
    # Handle deep links
    arg = message.get_args()
    if arg == "help":
        await cmd_help(message)
        return
    if arg == "donate":
        await send_donate_msg(message)
        return

    await message.reply(
        (
            "Merhaba! Telegram gruplarında kelime zinciri oyunları barındırıyorum.\n"
            "Oyun oynamaya başlamak için beni bir gruba ekleyin!"
        ),
        disable_web_page_preview=True,
        reply_markup=ADD_TO_GROUP_KEYBOARD,
    )


@dp.message_handler(content_types=types.ContentTypes.NEW_CHAT_MEMBERS)
async def new_member(message: types.Message) -> None:
    if any(user.id == bot.id for user in message.new_chat_members):  # self added to group
        await message.reply(
            "Beni eklediğiniz için teşekkürler /startclassic ile klasik bir oyuna başlayın!",
            reply=False,
        )
    elif message.chat.id == OFFICIAL_GROUP_ID:
        await message.reply(
            "Resmi NightWord Kelime Zinciri grubuna hoş geldiniz!\n"
            "/startclassic ile klasik bir oyuna başlayın!"
        )


@dp.message_handler(commands="help")
async def cmd_help(message: types.Message) -> None:
    if message.chat.id < 0:
        await message.reply(
            "Lütfen bu komutu özel olarak kullanın.",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            "Özel olarak yardım mesajı gönder",
                            url="https://t.me/NightWordBot?start=help",
                        )
                    ]
                ]
            ),
        )
        return

    await message.reply(
        (
            "/gameinfo - Oyun modu açıklamaları\n"
            "/troubleshoot - Sık karşılaşılan sorunları nasıl çözeceğinizi öğrenin\n"
            "/reqaddword - Kelimelerin eklenmesini iste\n\n"
            "Botla ilgili herhangi bir şey için [POYRAZ](tg://user?id=1557151130) in *Kürtçe veya Türkçe* mesaj gönderebilirsiniz.\n"
            "Resmi Grup: @Fmsarkilar\n"
            "Kelime Ekleme Kanalı (durum güncellemeli): @NightWordGame\n"
            "NightWord [Poyraz] tarafından tasarlandı (tg://user?id=1557151130)"
        ),
        disable_web_page_preview=True,
    )


@dp.message_handler(commands="gameinfo")
async def cmd_gameinfo(message: types.Message) -> None:
    if message.chat.id < 0:
        await private_only_command(message)
        return
    await message.reply(
        "/startclassic - Klasik oyun\n"
        "Oyuncular sırayla bir önceki kelimenin son harfiyle başlayan kelimeleri gönderirler.\n\n"
        "Diğer modlar:\n"
        "/starthard - Zor mod oyunu\n"
        "/startchaos - Kaos oyunu (rastgele sıra sırası)\n"
        "/startcfl - İlk harf oyunu seçildi\n"
        "/startbl - Yasaklı harfler oyunu\n"
        "/startrl - Gerekli harf oyunu\n\n"
        "/startelim - Eleme oyunu\n"
        "Her oyuncunun puanı kümülatif kelime uzunluğudur. "
        "En düşük puana sahip oyuncular her turdan sonra elenir.\n\n"
        "/startmelim - Karışık eleme oyunu (bağış ödülü)\n"
        "Farklı modlara sahip eleme oyunu. @Fmsarkilar."
    )


@dp.message_handler(commands="troubleshoot")
async def cmd_troubleshoot(message: types.Message) -> None:
    if message.chat.id < 0:
        await private_only_command(message)
        return
    await message.reply(
        "Grubunuzdaki oyunlara başlayamazsanız:\n"
        "1. Bakım modunun açık olduğunu söylersem, bir güncelleme dağıtılmayı bekliyor.\\*\n"
        "2. Grubunuzda bulunduğumdan ve sesinizin kapatılmadığından ve yavaş modun kapalı olduğundan emin olun.\n"
        "3. Grubunuzda `/ping@NightWordBot` Gönderin.\n\n"
        "Cevap verirsem:\n"
        "[Sahibim] ile (tg://user?id=1557151130) grubunuzun kimliğiyle (/groupid ile elde edilir) iletişim kurun.\n\n"
        "Yanıt vermezsem:\n"
        "a. Bir güncelleme dağıtıldığı için çevrimdışı olabilirim.\\*\n"
        "b. Bir grup üyesi bana komutlarla spam gönderdiyse, "
        "Telegram ile dakikalar ve hatta saatler için sınırlandırılıyorum. "
        "Komutları spam etmeyin ve daha sonra tekrar deneyin.\n\n"
        "\\*: Lütfen bekleyin ve durum güncellemeleri için @NightWordGame'ı kontrol edin.\n\n"
        "Beni grubunuza ekleyemezseniz:\n"
        "1. Grubunuz yeni üye eklenmesini devre dışı bırakmış olabilir.\n"
        "2. Bir grupta en fazla 20 bot olabilir. Sınıra ulaşılıp ulaşılmadığını kontrol edin.\n"
        "3. Yardım için grup yöneticinizle iletişime geçin. Bu, sahibimin çözebileceği bir sorun değil.\n\n"
        "Başka sorunlarla karşılaşırsanız, lütfen [Sahibim] ile iletişime geçin (tg://user?id=1557151130)."
    )


@dp.message_handler(commands="ping")
async def cmd_ping(message: types.Message) -> None:
    t = time()
    msg = await message.reply("Pong!")
    await msg.edit_text(f"Pong! `{time() - t:.3f}s`")


@dp.message_handler(commands="groupid")
async def cmd_groupid(message: types.Message) -> None:
    if message.chat.id < 0:
        await message.reply(f"`{message.chat.id}`")
    else:
        await message.reply("Bu komutu bir grup içinde çalıştırın.")


@dp.message_handler(commands="runinfo")
async def cmd_runinfo(message: types.Message) -> None:
    uptime = datetime.now().replace(microsecond=0) - build_time
    await message.reply(
        f"Derleme zamanı: `{'{0.day}/{0.month}/{0.year}'.format(build_time)} {str(build_time).split()[1]} HKT`\n"
        f"Çalışma süresi: `{uptime.days}.{str(uptime).rsplit(maxsplit=1)[-1]}`\n"
        f"Toplam oyunlar: `{len(GAMES)}`\n"
        f"Running oyunları: `{len([g for g in GAMES.values() if g.state == GameState.RUNNING])}`\n"
        f"Oyuncu: `{sum(len(g.players) for g in GAMES.values())}`"
    )


@dp.message_handler(is_owner=True, commands="playinggroups")
async def cmd_playinggroups(message: types.Message) -> None:
    if not GAMES:
        await message.reply("Oyun oynayan grup yok.")
        return
    groups = []

    async def append_group(group_id: int) -> None:
        try:
            group = await bot.get_chat(group_id)
            url = await group.get_url()
            # TODO: resolve weakref exception, possibly aiogram bug?
        except Exception as e:
            text = f"(<code>{e.__class__.__name__}: {e}</code>)"
        else:
            if url:
                text = f"<a href='{url}'>{quote_html(group.title)}</a>"
            else:
                text = f"<b>{group.title}</b>"
        groups.append(
            text + (
                f" <code>{group_id}</code> "
                f"{len(GAMES[group_id].players_in_game)}/{len(GAMES[group_id].players)}P "
                f"Zamanlayıcı: {GAMES[group_id].time_left}s"
            )
        )

    await asyncio.gather(*[append_group(gid) for gid in GAMES])
    await message.reply("\n".join(groups), parse_mode=types.ParseMode.HTML, disable_web_page_preview=True)


@dp.message_handler(commands=["exist", "exists"])
async def cmd_exists(message: types.Message) -> None:
    word = message.text.partition(" ")[2].lower()
    if not word or not all(c in ascii_lowercase for c in word):  # No proper argument given
        rmsg = message.reply_to_message
        if rmsg and rmsg.text and all(c in ascii_lowercase for c in rmsg.text.lower()):
            word = rmsg.text.lower()
        else:
            await message.reply(
                "İşlev: Sözlüğümde bir sözcük olup olmadığını kontrol edin. "
                "Yeni kelimelerin eklenmesini istiyorsanız /reqaddword kullanın.\n"
                "Kullanım: `/exists kelime`"
            )
            return
    if check_word_existence(word):
        await message.reply(f"_{word.capitalize()}_ is *sözlüğümde*.")
    else:
        await message.reply(f"_{word.capitalize()}_ is *sözlüğümde* Değil.")


@dp.message_handler(commands=["startclassic", "startgame"])
async def cmd_startclassic(message: types.Message) -> None:
    if message.chat.id > 0:
        await groups_only_command(message)
        return
    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].join(message)
        return
    if MAINT_MODE:  # Only stop people from starting games, not joining
        await message.reply("Bakım modu açık. Oyunlar geçici olarak devre dışı bırakıldı.")
        return
    game = ClassicGame(message.chat.id)
    GAMES[group_id] = game
    await game.main_loop(message)


@dp.message_handler(commands="starthard")
async def cmd_starthard(message: types.Message) -> None:
    if message.chat.id > 0:
        await groups_only_command(message)
        return

    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].join(message)
        return
    if MAINT_MODE:
        await message.reply("Bakım modu açık. Oyunlar geçici olarak devre dışı bırakıldı.")
        return

    game = HardModeGame(message.chat.id)
    GAMES[group_id] = game
    await game.main_loop(message)


@dp.message_handler(commands="startchaos")
async def cmd_startchaos(message: types.Message) -> None:
    if message.chat.id > 0:
        await groups_only_command(message)
        return

    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].join(message)
        return
    if MAINT_MODE:
        await message.reply("Bakım modu açık. Oyunlar geçici olarak devre dışı bırakıldı.")
        return

    game = ChaosGame(message.chat.id)
    GAMES[group_id] = game
    await game.main_loop(message)


@dp.message_handler(commands="startcfl")
async def cmd_startcfl(message: types.Message) -> None:
    if message.chat.id > 0:
        await groups_only_command(message)
        return

    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].join(message)
        return
    if MAINT_MODE:
        await message.reply("Bakım modu açık. Oyunlar geçici olarak devre dışı bırakıldı.")
        return

    game = ChosenFirstLetterGame(message.chat.id)
    GAMES[group_id] = game
    await game.main_loop(message)


@dp.message_handler(commands="startbl")
async def cmd_startbl(message: types.Message) -> None:
    if message.chat.id > 0:
        await groups_only_command(message)
        return

    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].join(message)
        return
    if MAINT_MODE:
        await message.reply("Bakım modu açık. Oyunlar geçici olarak devre dışı bırakıldı.")
        return

    game = BannedLettersGame(message.chat.id)
    GAMES[group_id] = game
    await game.main_loop(message)


@dp.message_handler(commands="startrl")
async def cmd_startrl(message: types.Message) -> None:
    if message.chat.id > 0:
        await groups_only_command(message)
        return

    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].join(message)
        return
    if MAINT_MODE:
        await message.reply("Bakım modu açık. Oyunlar geçici olarak devre dışı bırakıldı.")
        return

    game = RequiredLetterGame(message.chat.id)
    GAMES[group_id] = game
    await game.main_loop(message)


@dp.message_handler(commands="startelim")
async def cmd_startelim(message: types.Message) -> None:
    if message.chat.id > 0:
        await groups_only_command(message)
        return

    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].join(message)
        return
    if MAINT_MODE:
        await message.reply("Bakım modu açık. Oyunlar geçici olarak devre dışı bırakıldı.")
        return

    game = EliminationGame(message.chat.id)
    GAMES[group_id] = game
    await game.main_loop(message)


@dp.message_handler(commands="startmelim")
async def cmd_startmixedelim(message: types.Message) -> None:
    if message.chat.id > 0:
        await groups_only_command(message)
        return

    if (
            message.chat.id not in VIP_GROUP
            and message.from_user.id not in VIP
            and (await amt_donated(message.from_user.id)) < 30
    ):
        await message.reply(
            "Bu oyun modu bir bağış ödülüdür.\n"
            "NightCrew da deniyebilirsiniz katılmak için  @Poyraz2103 e yazın."
        )
        return

    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].join(message)
        return
    if MAINT_MODE:
        await message.reply("Bakım modu açık. Oyunlar geçici olarak devre dışı bırakıldı.")
        return

    game = MixedEliminationGame(message.chat.id)
    GAMES[group_id] = game
    await game.main_loop(message)


@dp.message_handler(commands="join")
async def cmd_join(message: types.Message) -> None:
    if message.chat.id > 0:
        await groups_only_command(message)
        return

    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].join(message)
    # No reply is given when there is no running game in case the user was joining another game


@dp.message_handler(is_group=True, is_owner=True, commands="forcejoin")
async def cmd_forcejoin(message: types.Message) -> None:
    group_id = message.chat.id
    rmsg = message.reply_to_message
    if group_id not in GAMES:
        return
    if rmsg and rmsg.from_user.is_bot:  # NightABot only
        if rmsg.from_user.id != on9bot.id:
            return
        if isinstance(GAMES[group_id], EliminationGame):
            await message.reply(
                "Üzgünüm, [NightWord](https://t.me/NightWordBot) eleme oyunlarını oynayamaz.",
                disable_web_page_preview=True,
            )
            return
    await GAMES[message.chat.id].forcejoin(message)


@dp.message_handler(is_group=True, commands="extend")
async def cmd_extend(message: types.Message) -> None:
    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].extend(message)


@dp.message_handler(is_group=True, is_admin=True, commands="forcestart")
async def cmd_forcestart(message: types.Message) -> None:
    group_id = message.chat.id
    if group_id in GAMES and GAMES[group_id].state == GameState.JOINING:
        GAMES[group_id].time_left = -99999


@dp.message_handler(is_group=True, commands="flee")
async def cmd_flee(message: types.Message) -> None:
    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].flee(message)


@dp.message_handler(is_group=True, is_owner=True, commands="forceflee")
async def cmd_forceflee(message: types.Message) -> None:
    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].forceflee(message)


@dp.message_handler(is_group=True, is_owner=True, commands=["killgame", "killgaym"])
async def cmd_killgame(message: types.Message) -> None:
    group_id = int(message.get_args() or message.chat.id)
    if group_id in GAMES:
        GAMES[group_id].state = GameState.KILLGAME
        await asyncio.sleep(2)
        if group_id in GAMES:
            del GAMES[group_id]
            await message.reply("Oyun zorla sona erdi.")


@dp.message_handler(is_group=True, is_owner=True, commands="forceskip")
async def cmd_forceskip(message: types.Message) -> None:
    group_id = message.chat.id
    if group_id in GAMES and GAMES[group_id].state == GameState.RUNNING and not GAMES[group_id].answered:
        GAMES[group_id].time_left = 0


@dp.message_handler(is_group=True, commands="addvp")
async def addvp(message: types.Message) -> None:
    group_id = message.chat.id
    if group_id not in GAMES:
        return
    if isinstance(GAMES[group_id], EliminationGame):
        await message.reply(
            f"Üzgünüm, [NightWord](https://t.me/{(await NightWordBot.me).username}) eleme oyunları olamaz.",
            disable_web_page_preview=True,
        )
        return
    await GAMES[group_id].addvp(message)


@dp.message_handler(is_group=True, commands="remvp")
async def remvp(message: types.Message) -> None:
    group_id = message.chat.id
    if group_id in GAMES:
        await GAMES[group_id].remvp(message)


@dp.message_handler(is_group=True, is_owner=True, commands="incmaxp")
async def cmd_incmaxp(message: types.Message) -> None:
    # Thought this could be useful when I implemented this
    # Nope
    group_id = message.chat.id
    if (
            group_id not in GAMES
            or GAMES[group_id].state != GameState.JOINING
            or GAMES[group_id].max_players == GameSettings.INCREASED_MAX_PLAYERS
    ):
        return
    GAMES[group_id].max_players = GameSettings.INCREASED_MAX_PLAYERS
    await message.reply(
        "Bu oyun için maksimum oyuncu sayısı "
        f"{GAMES[group_id].max_players} to {GameSettings.INCREASED_MAX_PLAYERS}."
    )


@dp.message_handler(is_owner=True, commands="maintmode")
async def cmd_maintmode(message: types.Message) -> None:
    global MAINT_MODE
    MAINT_MODE = not MAINT_MODE
    await message.reply(f"Bakım modu geçildi {'on' if MAINT_MODE else 'off'}.")


@dp.message_handler(is_group=True, is_owner=True, commands="leave")
async def cmd_leave(message: types.Message) -> None:
    await message.chat.leave()


@dp.message_handler(commands=["stat", "stats", "stalk"])
async def cmd_stats(message: types.Message) -> None:
    rmsg = message.reply_to_message
    if message.chat.id < 0 and not message.get_command().partition("@")[2]:
        return

    user = (rmsg.forward_from or rmsg.from_user) if rmsg else message.from_user
    async with pool.acquire() as conn:
        res = await conn.fetchrow("SEÇ * OYUNCU NEREDEN user_id = $1;", user.id)

    if not res:
        await message.reply(
            f"{user.get_mention(as_html=True)} için istatistik yok!",
            parse_mode=types.ParseMode.HTML,
        )
        return

    mention = user.get_mention(
        name=user.full_name + (" \u2b50\ufe0f" if await has_star(user.id) else ""),
        as_html=True,
    )
    text = f"\U0001f4ca için İstatistik {mention}:\n"
    text += f"<b>{res['game_count']}</b> oyun oynandı\n"
    text += f"<b>{res['win_count']} ({res['win_count'] / res['game_count']:.0%})</b> oyunu kazandı\n"
    text += f"<b>{res['word_count']}</b> oynanan toplam kelime\n"
    text += f"<b>{res['letter_count']}</b> oynanan toplam harf\n"
    if res["longest_word"]:
        text += f"En uzun kelime: <b>{res['longest_word'].capitalize()}</b>"
    await message.reply(text.rstrip(), parse_mode=types.ParseMode.HTML)


@dp.message_handler(commands="groupstats")
async def cmd_groupstats(message: types.Message) -> None:  # TODO: Add top players in group (up to 5?)
    if message.chat.id > 0:
        await groups_only_command(message)
        return

    async with pool.acquire() as conn:
        player_cnt, game_cnt, word_cnt, letter_cnt = await conn.fetchrow(
            """\
            SELECT COUNT(DISTINCT user_id), COUNT(DISTINCT game_id), SUM(word_count), SUM(letter_count)
                FROM gameplayer
                WHERE group_id = $1;""",
            message.chat.id,
        )
    await message.reply(
        (
            f"\U0001f4ca İstatistik <b>{quote_html(message.chat.title)}</b>\n"
            f"<b>{player_cnt}</b> oyuncu\n"
            f"<b>{game_cnt}</b> oynanan oyun\n"
            f"<b>{word_cnt}</b> oynanan toplam kelime\n"
            f"<b>{letter_cnt}</b> oynanan toplam harf"
        ),
        parse_mode=types.ParseMode.HTML,
    )


@cached(ttl=5)
async def get_global_stats() -> str:
    async with pool.acquire() as conn:
        group_cnt, game_cnt = await conn.fetchrow(
            "SELECT COUNT(DISTINCT group_id), COUNT(*) FROM game;"
        )
        player_cnt, word_cnt, letter_cnt = await conn.fetchrow(
            "SELECT COUNT(*), SUM(word_count), SUM(letter_count) FROM player;"
        )
    return (
        "\U0001f4ca Genel istatistikler\n"
        f"*{group_cnt}* gruplar\n"
        f"*{player_cnt}* oyuncular\n"
        f"*{game_cnt}* oynanan oyunlar\n"
        f"*{word_cnt}* oynanan toplam kelime\n"
        f"*{letter_cnt}* oynanan toplam harf"
    )


@dp.message_handler(commands="globalstats")
async def cmd_globalstats(message: types.Message) -> None:
    await message.reply(await get_global_stats())




@dp.message_handler(commands="donate")
async def cmd_donate(message: types.Message) -> None:
    if message.chat.id < 0:
        await message.reply(
            "Bağış yapmak için DM'lerime kaydırın!",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            "Özel bağış yapın",
                            url="https://t.me/NightWordBot?start=donate",
                        )
                    ]
                ]
            ),
        )
        return
    arg = message.get_args()
    if not arg:
        await send_donate_msg(message)
    else:
        try:
            amt = int(Decimal(arg).quantize(Decimal("1.00")) * 100)
            assert amt > 0
            await send_donate_invoice(message.chat.id, amt)
        except (ValueError, InvalidOperation, AssertionError):
            await message.reply("Geçersiz miktar.\nLütfen pozitif bir sayı girin.")
        except BadRequest as e:
            if str(e) == "Currency_total_amount_invalid":
                await message.reply(
                    "Üzgünüz, girilen miktar (1-10000) aralığında değil. " "Lütfen başka bir miktar deneyin."
                )
                return
            raise


async def send_donate_msg(message: types.Message) -> None:
    await message.reply(
        "Bu projeyi desteklemek için bağış yapın! \u2764\ufe0f\n"
        "Bağışlar HKD olarak kabul edilir HKD (1 USD ≈ 7.75 HKD).\n"
        "Aşağıdaki seçeneklerden birini seçin veya HKD olarak istediğiniz miktarı yazın (örnk. `/donate 42.42`).\n\n"
        "Bağış ödülleri:\n"
        "Oyunlar sırasında adınızın yanında herhangi bir miktar: \u2b50\ufe0f görüntülenir.\n"
        "10 HKD (cumulative): Satır içi sorgularda kelime ara (e.g. `@NightWord test`)\n"
        "30 HKD (cumulative): Karışık eleme oyunlarını başlat (`/startmelim`)\n",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton("10 HKD", callback_data="donate:10"),
                    types.InlineKeyboardButton("20 HKD", callback_data="donate:20"),
                    types.InlineKeyboardButton("30 HKD", callback_data="donate:30"),
                ],
                [
                    types.InlineKeyboardButton("50 HKD", callback_data="donate:50"),
                    types.InlineKeyboardButton("100 HKD", callback_data="donate:100"),
                ],
            ]
        ),
    )


async def send_donate_invoice(user_id: int, amt: int) -> None:
    await bot.send_invoice(
        chat_id=user_id,
        title="NightWord Kelime Zinciri Bot Bağışı",
        description="Bot geliştirmeyi destekle",
        payload=f"NightWordBot_donation:{user_id}",
        provider_token=PROVIDER_TOKEN,
        start_parameter="donate",
        currency="HKD",
        prices=[types.LabeledPrice("Donation", amt)],
    )


@dp.pre_checkout_query_handler()
async def pre_checkout_query_handler(pre_checkout_query: types.PreCheckoutQuery) -> None:
    if pre_checkout_query.invoice_payload == f"NightWordBot_donation:{pre_checkout_query.from_user.id}":
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    else:
        await bot.answer_pre_checkout_query(
            pre_checkout_query.id,
            ok=False,
            error_message="Bağış başarısız. Ödeme yapılmadı. Daha sonra tekrar deneyebilir misiniz? :D",
        )


@dp.message_handler(content_types=ContentTypes.SUCCESSFUL_PAYMENT)
async def successful_payment_handler(message: types.Message) -> None:
    payment = message.successful_payment
    donation_id = str(uuid4())[:8]
    amt = Decimal(payment.total_amount) / 100
    dt = datetime.now().replace(microsecond=0)
    async with pool.acquire() as conn:
        await conn.execute(
            """\
            INSERT INTO Bağış (
                donation_id, user_id, amount, donate_time,
                telegram_payment_charge_id, provider_payment_charge_id
            )
            VALUES
                ($1, $2, $3::NUMERIC, $4, $5, $6);""",
            donation_id,
            message.from_user.id,
            str(amt),
            dt,
            payment.telegram_payment_charge_id,
            payment.provider_payment_charge_id,
        )
    await asyncio.gather(
        message.answer(
            (
                f"{amt} bağışınız başarılı.\n"
                "Desteğiniz için teşekkürler! :D\n"
                f"Bağış kimliği: #nightwordbot_{donation_id}"
            ),
            parse_mode=types.ParseMode.HTML,
        ),
        send_admin_group(
            (
                f"bağışı alındı {amt} HKD from {message.from_user.get_mention(as_html=True)} "
                f"(id: <code>{message.from_user.id}</code>).\n"
                f"Bağış kimliği: #nightwordbot_{donation_id}"
            ),
            parse_mode=types.ParseMode.HTML,
        )
    )


@dp.message_handler(is_owner=True, commands="sql")
async def cmd_sql(message: types.Message) -> None:
    try:
        async with pool.acquire() as conn:
            res = await conn.fetch(message.get_full_command()[1])
    except Exception as e:
        await message.reply(f"`{e.__class__.__name__}: {str(e)}`")
        return

    if not res:
        await message.reply("Sonuç döndürülmedi.")
        return

    text = ["*" + " - ".join(res[0].keys()) + "*"]
    for r in res:
        text.append("`" + " - ".join([str(i) for i in r.values()]) + "`")
    await message.reply("\n".join(text))


@dp.message_handler(commands=["reqaddword", "reqaddwords"])
async def cmd_reqaddword(message: types.Message) -> None:
    if message.forward_from:
        return

    words_to_add = [w for w in set(message.get_args().lower().split()) if all(c in ascii_lowercase for c in w)]
    if not words_to_add:
        await message.reply(
            "İşlev: Yeni sözcüklerin eklenmesini talep edin. Yeni sözcükler için @Poyraz2103.\n"
            "Lütfen istekte bulunmadan önce kelimelerin yazımını kontrol edin, böylece isteklerinizi daha hızlı işleme koyabilirim.\n"
            "Özel isimler kabul edilmez.\n"
            "Kullanım: `/reqaddword wordone wordtwo ...`"
        )
        return

    existing = []
    rejected = []
    rejected_with_reason = []
    for w in words_to_add[:]:  # Iterate through a copy so removal of elements is possible
        if check_word_existence(w):
            existing.append("_" + w.capitalize() + "_")
            words_to_add.remove(w)

    async with pool.acquire() as conn:
        rej = await conn.fetch("SEÇİN kelime, kabul edilmeyen kelime listesinden neden;")
    for word, reason in rej:
        if word not in words_to_add:
            continue
        words_to_add.remove(word)
        word = "_" + word.capitalize() + "_"
        if reason:
            rejected_with_reason.append((word, reason))
        else:
            rejected.append(word)

    text = ""
    if words_to_add:
        text += f"Öneri {', '.join(['_' + w.capitalize() + '_' for w in words_to_add])} for approval.\n"
        await send_admin_group(
            message.from_user.get_mention(
                name=message.from_user.full_name + (" \u2b50\ufe0f" if await has_star(message.from_user.id) else ""),
                as_html=True,
            )
            + " nin eklenmesini istiyor "
            + ", ".join(["<i>" + w.capitalize() + "</i>" for w in words_to_add])
            + " kelime listesine. #reqaddword",
            parse_mode=types.ParseMode.HTML,
        )
    if existing:
        text += f"{', '.join(existing)} {'is' if len(existing) == 1 else 'are'} already in the word list.\n"
    if rejected:
        text += f"{', '.join(rejected)} {'was' if len(rejected) == 1 else 'were'} rejected.\n"
    for word, reason in rejected_with_reason:
        text += f"{word} was rejected due to {reason}.\n"
    await message.reply(text.rstrip())


@dp.message_handler(is_owner=True, commands=["addword", "addwords"])
async def cmd_addwords(message: types.Message) -> None:
    words_to_add = [w for w in set(message.get_args().lower().split()) if all(c in ascii_lowercase for c in w)]
    if not words_to_add:
        return
    existing = []
    rejected = []
    rejected_with_reason = []
    for w in words_to_add[:]:  # Cannot iterate while deleting
        if check_word_existence(w):
            existing.append("_" + w.capitalize() + "_")
            words_to_add.remove(w)
    async with pool.acquire() as conn:
        rej = await conn.fetch("SEÇİN kelime, kabul edilmeyen kelime listesinden neden;")
    for word, reason in rej:
        if word not in words_to_add:
            continue
        words_to_add.remove(word)
        word = "_" + word.capitalize() + "_"
        if reason:
            rejected_with_reason.append((word, reason))
        else:
            rejected.append(word)
    text = ""
    if words_to_add:
        async with pool.acquire() as conn:
            await conn.copy_records_to_table("wordlist", records=[(w, True, None) for w in words_to_add])
        text += f"Added {', '.join(['_' + w.capitalize() + '_' for w in words_to_add])} to the word list.\n"
    if existing:
        text += f"{', '.join(existing)} {'is' if len(existing) == 1 else 'are'} already in the word list.\n"
    if rejected:
        text += f"{', '.join(rejected)} {'was' if len(rejected) == 1 else 'were'} rejected.\n"
    for word, reason in rejected_with_reason:
        text += f"{word} was rejected due to {reason}.\n"
    msg = await message.reply(text.rstrip())
    if not words_to_add:
        return
    await update_words()
    await msg.edit_text(msg.md_text + "\n\nKelime listesi güncellendi.")
    await bot.send_message(
        WORD_ADDITION_CHANNEL_ID,
        f"Eklenen {', '.join(['_' + w.capitalize() + '_' for w in words_to_add])} to the word list.",
        disable_notification=True,
    )


@dp.message_handler(is_owner=True, commands="rejword")
async def cmd_rejword(message: types.Message) -> None:
    arg = message.get_args()
    word, _, reason = arg.partition(" ")
    if not word:
        return
    word = word.lower()
    async with pool.acquire() as conn:
        r = await conn.fetchrow("SEÇME kabul edildi, kelime listesinden neden NEREDE kelime = $1;", word)
        if r is None:
            await conn.execute(
                "INSERT INTO wordlist (kelime, kabul edildi, neden) VALUES ($1, false, $2)",
                word,
                reason.strip() or None,
            )
    word = word.capitalize()
    if r is None:
        await message.reply(f"_{word}_ reddedildi.")
    elif r["kabul edildi"]:
        await message.reply(f"_{word}_ kabul edildi.")
    elif not r["reason"]:
        await message.reply(f"_{word}_ zaten reddedildi.")
    else:
        await message.reply(f"_{word}_ nedeniyle zaten reddedildi {r['reason']}.")


@dp.message_handler(commands="feedback")
async def cmd_feedback(message: types.Message) -> None:
    rmsg = message.reply_to_message
    if (
            message.chat.id < 0
            and not message.get_command().partition("@")[2]
            and (not rmsg or rmsg.from_user.id != bot.id)
            or message.forward_from
    ):  # Make sure feedback is directed at this bot
        return

    arg = message.get_full_command()[1]
    if not arg:
        await message.reply(
            "İşlev: Sahibime geri bildirim gönder.\n"
            "Kullanım: `/feedback@NightWordBot feedback`"
        )
        return

    await asyncio.gather(
        message.forward(ADMIN_GROUP_ID),
        message.reply("Geri bildirim başarıyla gönderildi."),
    )


@dp.message_handler(is_group=True, regexp=r"^\w+$")
@dp.edited_message_handler(is_group=True, regexp=r"^\w+$")
async def message_handler(message: types.Message) -> None:
    group_id = message.chat.id
    if (
            group_id in GAMES
            and GAMES[group_id].players_in_game
            and message.from_user.id == GAMES[group_id].players_in_game[0].user_id
            and not GAMES[group_id].answered
            and GAMES[group_id].accepting_answers
            # TODO: Modify to support other languages
            and all([c in ascii_lowercase for c in message.text.lower()])
    ):
        await GAMES[group_id].handle_answer(message)


@dp.inline_handler()
async def inline_handler(inline_query: types.InlineQuery):
    text = inline_query.query.lower()
    if not text or inline_query.from_user.id not in VIP and (await amt_donated(inline_query.from_user.id)) < 10:
        await inline_query.answer(
            [
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Klasik bir oyun başlatın",
                    description="/startclassic@NightWordBot",
                    input_message_content=types.InputTextMessageContent("/startclassic@NightWordBot"),
                ),
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Zor mod oyunu başlat",
                    description="/starthard@NightWordBot",
                    input_message_content=types.InputTextMessageContent("/starthard@NightWordBot"),
                ),
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Bir kaos oyunu başlatın",
                    description="/startchaos@NightWordBot",
                    input_message_content=types.InputTextMessageContent("/startchaos@NightWordBot"),
                ),
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Seçtiğiniz ilk harf oyununu başlatın",
                    description="/startcfl@NightWordBot",
                    input_message_content=types.InputTextMessageContent("/startcfl@NightWordBot"),
                ),
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Yasaklı mektup oyunu başlat",
                    description="/startbl@NightWordBot",
                    input_message_content=types.InputTextMessageContent("/startbl@NightWordBot"),
                ),
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Gerekli bir harf oyununu başlatın",
                    description="/startrl@NightWordBot",
                    input_message_content=types.InputTextMessageContent("/startrl@NightWordBot"),
                ),
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Bir eleme oyunu başlat",
                    description="/startelim@NightWordBot",
                    input_message_content=types.InputTextMessageContent("/startelim@NightWordBot"),
                ),
            ],
            is_personal=not text,
        )
        return

    if any(c not in ascii_lowercase for c in text):
        await inline_query.answer(
            [
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Bir sorgu yalnızca alfabelerden oluşabilir",
                    description="Farklı bir sorgu dene",
                    input_message_content=types.InputTextMessageContent(r"¯\\_(ツ)\_/¯"),
                )
            ],
            is_personal=True,
        )
        return

    res = []
    for i in filter_words(starting_letter=text[0]):
        if i.startswith(text):
            i = i.capitalize()
            res.append(
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=i,
                    input_message_content=types.InputTextMessageContent(i),
                )
            )
            if len(res) == 50:  # Max 50 results
                break
    if not res:  # No results
        res.append(
            types.InlineQueryResultArticle(
                id=str(uuid4()),
                title="Sonuç bulunamadı",
                description="Farklı bir sorgu dene",
                input_message_content=types.InputTextMessageContent(r"¯\\_(ツ)\_/¯"),
            )
        )
    await inline_query.answer(res, is_personal=True)


@dp.callback_query_handler()
async def callback_query_handler(callback_query: types.CallbackQuery) -> None:
    text = callback_query.data
    if text.startswith("donate"):
        await send_donate_invoice(callback_query.from_user.id, int(text.split(":")[1]) * 100)
    await callback_query.answer()


@dp.errors_handler(exception=Exception)
async def error_handler(update: types.Update, error: TelegramAPIError) -> None:
    for game in GAMES.values():  # TODO: Do this for group in which error occurs only
        asyncio.create_task(game.scan_for_stale_timer())

    if isinstance(error, MigrateToChat):
        if update.message.chat.id in GAMES:  # TODO: Test
            old_gid = GAMES[update.message.chat.id].group_id
            GAMES[error.migrate_to_chat_id] = GAMES.pop(update.message.chat.id)
            GAMES[error.migrate_to_chat_id].group_id = error.migrate_to_chat_id
            asyncio.create_task(
                send_admin_group(f"oyun taşınan için {old_gid} to {error.migrate_to_chat_id}.")
            )
        async with pool.acquire() as conn:
            await conn.execute(
                """\
                UPDATE game SET group_id = $1 WHERE group_id = $2;
                UPDATE gameplayer SET group_id = $1 WHERE group_id = $2;
                DELETE FROM game WHERE group_id = $2;
                DELETE FROM gameplayer WHERE group_id = $2;""",
                error.migrate_to_chat_id,
                update.message.chat.id,
            )
        await send_admin_group(f"Group migrated to {error.migrate_to_chat_id}.")
        return

    send_admin_msg = await send_admin_group(
        f"`{error.__class__.__name__} @ "
        f"{update.message.chat.id if update.message and update.message.chat else 'idk'}`:\n"
        f"`{str(error)}`",
    )
    if not update.message or not update.message.chat:
        return

    try:
        await update.message.reply("Hata oluştu. Sahibim bilgilendirildi.")
    except TelegramAPIError:
        pass

    if update.message.chat.id in GAMES:
        asyncio.create_task(
            send_admin_msg.reply(f"Sonuç olarak {update.message.chat.id} içinde oyunu öldürmek.")
        )
        GAMES[update.message.chat.id].state = GameState.KILLGAME
        await asyncio.sleep(2)
        try:
            del GAMES[update.message.chat.id]
            await update.message.reply("Oyun zorla sona erdi.")
        except:
            pass


def main() -> None:
    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    main()
