import json
import os
import random

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Record, Plain
from astrbot.api import logger

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
VOICE_DIR = os.path.join(PLUGIN_DIR, "voice")


@register("dafeiyu_voicepack", "小鲸鱼", "固定语音包：/语音 早安", "1.0.0")
class VoicePackPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.enabled = bool(self.config.get("enable", True))

    def _list(self) -> list[str]:
        if not os.path.isdir(VOICE_DIR):
            return []
        return sorted(f[:-4] for f in os.listdir(VOICE_DIR) if f.lower().endswith(".wav"))

    def _pick(self, key: str) -> str | None:
        files = self._list()
        if not files:
            return None
        if not key:
            return os.path.join(VOICE_DIR, random.choice(files) + ".wav")
        if key in files:
            return os.path.join(VOICE_DIR, key + ".wav")
        hits = [f for f in files if key in f or f in key]
        if hits:
            return os.path.join(VOICE_DIR, hits[0] + ".wav")
        return None

    @filter.command("语音")
    async def voice_cmd(self, event: AstrMessageEvent):
        """语音 [名字] —— 发一条固定语音"""
        if not self.enabled:
            yield event.plain_result("语音包关着呢")
            return
        raw = (event.message_str or "").strip().lstrip("/").strip()
        key = raw.replace("语音", "", 1).strip()

        files = self._list()
        if not files:
            yield event.plain_result("voice 文件夹里没有音频")
            return

        if key in ("列表", "list", "有啥", ""):
            if key:
                yield event.plain_result("可以发：\n" + "、".join(files))
                return

        path = self._pick(key)
        if not path:
            yield event.plain_result("没有这句。可以发：\n" + "、".join(files))
            return
        try:
            yield event.chain_result([Record.fromFileSystem(path)])
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[voicepack] 发送失败: {exc}")
            yield event.plain_result("发不出来，看日志")
