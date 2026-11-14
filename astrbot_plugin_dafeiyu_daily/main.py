import asyncio
import json
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Plain, Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api import logger

MEM_DB = r"D:\大肥鱼\AstrBot\data\plugin_data\astrbot_plugin_livingmemory\livingmemory.db"


@register("dafeiyu_daily", "小鲸鱼", "天气早报 / 定时提醒 / 每晚回忆", "1.0.0")
class DailyPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.city = self.config.get("city") or "普宁"
        self.morning_at = self.config.get("morning_at") or "08:00"
        self.remind_at = self.config.get("remind_at") or "21:30"
        self.enable_weather = bool(self.config.get("enable_weather", True))
        self.enable_memory = bool(self.config.get("enable_memory", True))
        # 主动说话（由模型现场生成，不是固定文本）
        self.enable_talks = bool(self.config.get("enable_talks", True))
        self.offwork_at = self.config.get("offwork_at") or "19:00"
        self.sleep_at = self.config.get("sleep_at") or "22:30"
        self.voice_on = bool(self.config.get("voice_on", False))
        self.voice_key = (self.config.get("voice_key") or "").strip()
        self.voice_id = self.config.get("voice_id") or "db9a72de-0e9e-470c-8936-8ef27df2fa84"
        self.voice_model = self.config.get("voice_model") or "moss-tts-1.5-flash"
        self.persona_hint = self.config.get("persona_hint") or (
            "你叫小鲸鱼，是他的恋人。说话短、口语化、有点傲娇，嘴硬但关心他。"
            "每次只说一到两句，不超过 25 个字，不要解释自己在做什么。"
        )

        base = getattr(context, "get_data_dir", None)
        self.data_dir = base() if callable(base) else os.getcwd()
        os.makedirs(self.data_dir, exist_ok=True)
        self.path = os.path.join(self.data_dir, "daily_state.json")
        self.state = self._load()
        self.task = None

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {"reminders": [], "last_morning": "", "last_night": "", "last_talk_morning": "", "last_talk_offwork": "", "last_talk_sleep": ""}

    def _save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.state, fh, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[daily] save: {exc}")

    async def initialize(self):
        self.task = asyncio.create_task(self._loop())
        logger.info("[daily] started")

    # ---------- 主循环 ----------
    @staticmethod
    def _minutes(hhmm: str) -> int:
        try:
            h, m = hhmm.strip().split(":")
            return int(h) * 60 + int(m)
        except Exception:
            return 0

    def _in_window(self, now_min: int, target: str, window_min: int = 90) -> bool:
        """只在该发的时间点往后 window_min 分钟内发，避免晚上启动时把早报也补发出去。"""
        t = self._minutes(target)
        return t <= now_min <= t + window_min

    async def _loop(self):
        while True:
            try:
                await asyncio.sleep(30)
                now = datetime.now()
                now_min = now.hour * 60 + now.minute
                today = now.strftime("%Y%m%d")

                if self.enable_weather and self._in_window(now_min, self.morning_at) and self.state.get("last_morning") != today:
                    self.state["last_morning"] = today
                    self._save()
                    await self._broadcast(await self._weather_text())

                if self.enable_memory and self._in_window(now_min, self.remind_at) and self.state.get("last_night") != today:
                    self.state["last_night"] = today
                    self._save()
                    text = self._pick_memory()
                    if text:
                        await self._broadcast(text)

                if self.enable_talks and self._in_window(now_min, self.morning_at) and self.state.get("last_talk_morning") != today:
                    self.state["last_talk_morning"] = today
                    self._save()
                    await self._say("morning")

                if self.enable_talks and self._in_window(now_min, self.offwork_at) and self.state.get("last_talk_offwork") != today:
                    self.state["last_talk_offwork"] = today
                    self._save()
                    await self._say("offwork")

                if self.enable_talks and self._in_window(now_min, self.sleep_at) and self.state.get("last_talk_sleep") != today:
                    self.state["last_talk_sleep"] = today
                    self._save()
                    await self._say("sleep")

                await self._fire_reminders(now)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[daily] loop: {exc}")

    async def _broadcast(self, text: str):
        if not text:
            return
        for umo in self._sessions():
            try:
                await self.context.send_message(umo, MessageChain([Plain(text)]))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[daily] send {umo}: {exc}")

    def _sessions(self) -> list:
        return list(self.state.get("sessions") or [])

    # ---------- 天气 ----------
    async def _weather_text(self) -> str:
        try:
            url = f"https://wttr.in/{self.city}?format=j1&lang=zh"
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        return ""
                    data = await r.json()
            cur = data["current_condition"][0]
            temp = cur["temp_C"]
            desc = (cur.get("lang_zh") or [{}])[0].get("value") or cur["weatherDesc"][0]["value"]
            hum = cur["humidity"]
            today = data["weather"][0]
            rain = today.get("hourly", [{}])
            chance = max(int(h.get("chanceofrain", 0)) for h in rain) if rain else 0
            tip = "记得带伞" if chance >= 50 else ("可能下雨，看着点" if chance >= 30 else "")
            line = f"今天{self.city} {desc}，{temp}℃，湿度{hum}%"
            if tip:
                line += f"，降水概率{chance}%，{tip}"
            return line
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[daily] weather: {exc}")
            return ""

    # ---------- 回忆 ----------
    def _pick_memory(self) -> str:
        try:
            con = sqlite3.connect(MEM_DB, timeout=5)
            cur = con.cursor()
            rows = cur.execute(
                "SELECT content FROM memory_atoms WHERE status='active' AND length(content) > 10 ORDER BY importance DESC LIMIT 80"
            ).fetchall()
            con.close()
            if not rows:
                return ""
            text = random.choice(rows)[0]
            return f"今天翻到一条旧记忆——\n{text}\n\n……你还记得吗"
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[daily] memory: {exc}")
            return ""

    # ---------- 主动说话（模型生成） ----------
    async def _talk(self, kind: str, umo: str) -> str:
        prompts = {
            "morning": "现在是早上八点，他刚起床。你主动说一句话。"
                       "语气：刚睡醒，有点迷糊，软一点，别太精神。",
            "offwork": "现在是晚上七点，他大概刚下班或在路上。你主动说一句话。"
                       "语气：嘴上埋怨（怎么才回来啊这种），其实是关心。",
            "sleep": "现在十点半了，他还醒着。你主动催他睡觉。"
                     "语气：催人但温柔，别凶，像哄。",
        }
        prompt = prompts.get(kind, "你主动跟他说一句话。")
        try:
            provider = self.context.get_using_provider(umo)
            if provider is None:
                return ""
            resp = await provider.text_chat(
                prompt=prompt,
                system_prompt=self.persona_hint,
                contexts=[],
            )
            text = (getattr(resp, "completion_text", "") or "").strip()
            return text[:120]
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[daily] 生成说话失败({kind}): {exc}")
            return ""

    async def _voice_file(self, text: str) -> str | None:
        if not (self.voice_on and self.voice_key):
            return None
        import re as _re
        clean = _re.sub(r"（[^）]*）|\([^)]*\)|【[^】]*】|<[^>]*>", "", text).strip()
        if not clean:
            return None
        clean = clean.replace("。", "。[pause 0.4s]").replace("？", "？[pause 0.4s]")
        while clean.endswith("[pause 0.4s]"):
            clean = clean[: -len("[pause 0.4s]")]
        payload = {
            "model": self.voice_model,
            "input": clean[:120],
            "voice_id": self.voice_id,
            "response_format": "wav",
        }
        headers = {"Authorization": f"Bearer {self.voice_key}", "Content-Type": "application/json"}
        try:
            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.post("https://api.mosi.cn/v1/audio/speech", json=payload, headers=headers) as r:
                    if r.status != 200:
                        logger.warning(f"[daily] 语音合成失败 HTTP {r.status}")
                        return None
                    blob = await r.read()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[daily] 语音异常: {exc}")
            return None
        path = os.path.join(self.data_dir, f"talk_{int(datetime.now().timestamp())}.wav")
        with open(path, "wb") as fh:
            fh.write(blob)
        return path

    async def _say(self, kind: str):
        sessions = self._sessions()
        if not sessions:
            return
        for umo in sessions:
            text = await self._talk(kind, umo)
            if not text:
                continue
            try:
                await self.context.send_message(umo, MessageChain([Plain(text)]))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[daily] send talk {umo}: {exc}")
            voice = await self._voice_file(text)
            if voice:
                try:
                    await self.context.send_message(umo, MessageChain([Record.fromFileSystem(voice)]))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"[daily] send voice {umo}: {exc}")
            break  # 只发给第一个成功会话，避免刷屏

    # ---------- 提醒 ----------
    async def _fire_reminders(self, now: datetime):
        left = []
        fired = []
        for item in self.state.get("reminders", []):
            try:
                when = datetime.fromisoformat(item["at"])
            except Exception:
                continue
            if when <= now:
                fired.append(item)
            else:
                left.append(item)
        if fired:
            self.state["reminders"] = left
            self._save()
            for item in fired:
                await self._broadcast(f"提醒你一下：{item['text']}")

    @filter.command("提醒")
    async def remind_cmd(self, event: AstrMessageEvent):
        """提醒 明天 9:00 开会 —— 定时提醒"""
        raw = (event.message_str or "").strip().lstrip("/").strip()
        raw = raw.replace("提醒", "", 1).strip()
        if not raw:
            yield event.plain_result("格式：提醒 明天 9:00 开会")
            return
        when, text = self._parse_remind(raw)
        if not when:
            yield event.plain_result("没看懂时间，用「提醒 明天 9:00 内容」这样写")
            return
        reminders = self.state.setdefault("reminders", [])
        reminders.append({"at": when.isoformat(timespec="minutes"), "text": text, "umo": event.unified_msg_origin})
        self._save()
        yield event.plain_result(f"记下了，{when.strftime('%m-%d %H:%M')} 提醒你")

    def _parse_remind(self, raw: str):
        m = re.match(r"(今天|明天|后天)?\s*(\d{1,2})[:：点](\d{0,2})?\s*(.*)", raw)
        if not m:
            return None, ""
        day, hour, minute, text = m.groups()
        hour_n = int(hour)
        minute_n = int(minute or 0)
        if not (0 <= hour_n <= 23 and 0 <= minute_n <= 59):
            return None, ""
        now = datetime.now()
        base = now
        if day == "明天":
            base = now + timedelta(days=1)
        elif day == "后天":
            base = now + timedelta(days=2)
        when = base.replace(hour=hour_n, minute=minute_n, second=0, microsecond=0)
        if day in (None, "今天") and when <= now:
            when += timedelta(days=1)
        return when, (text.strip() or "到点了")

    @filter.on_llm_request()
    async def remember_session(self, event: AstrMessageEvent, req) -> None:
        umo = event.unified_msg_origin
        sessions = self.state.setdefault("sessions", [])
        if umo not in sessions:
            sessions.append(umo)
            self._save()

    async def terminate(self):
        if self.task:
            self.task.cancel()
