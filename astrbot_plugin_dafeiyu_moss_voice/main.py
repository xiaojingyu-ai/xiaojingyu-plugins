import os
import time

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api import logger

API_URL = "https://api.mosi.cn/v1/audio/speech"
VOICE_16 = "db9a72de-0e9e-470c-8936-8ef27df2fa84"  # 16岁少女


@register("dafeiyu_moss_voice", "小鲸鱼", "用 MOSS TTS 让她出声：/说话 文本", "1.0.0")
class MossVoicePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.api_key = (self.config.get("api_key") or "").strip()
        self.voice_id = self.config.get("voice_id") or VOICE_16
        self.model = self.config.get("model") or "moss-tts-1.5-flash"
        self.auto = bool(self.config.get("auto", False))
        self.pause_ms = int(self.config.get("pause_ms", 500) or 0)
        self.max_chars = int(self.config.get("max_chars", 120) or 120)

        base = getattr(context, "get_data_dir", None)
        self.data_dir = base() if callable(base) else os.path.join(os.getcwd(), "data")
        os.makedirs(self.data_dir, exist_ok=True)

    @staticmethod
    def _strip_stage(text: str) -> str:
        """去掉括号里的动作描写和标签，避免被念出来。"""
        import re
        # 先整段删掉 <style>...</style>（连内容一起），再删其他标签
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
        text = re.sub(r"（[^）]*）", "", text)
        text = re.sub(r"\([^)]*\)", "", text)
        text = re.sub(r"【[^】]*】", "", text)
        text = re.sub(r"<[^>]*>", "", text)
        text = re.sub(r"\[(?!pause\b)[^\]]*\]", "", text)  # 保留 [pause xxs] 标记
        return text.strip()

    def _prepare(self, text: str) -> str:
        text = self._strip_stage(text)
        if len(text) > self.max_chars:
            text = text[: self.max_chars].rstrip("，,、。") + "。"
        if self.pause_ms > 0:
            sec = self.pause_ms / 1000
            marker = f"[pause {sec}s]"
            text = text.replace("。", f"。{marker}").replace("？", f"？{marker}")
            text = text.replace("！", f"！{marker}")
            while text.endswith(marker):
                text = text[: -len(marker)]
        return text

    async def _tts(self, text: str) -> str | None:
        if not self.api_key:
            logger.warning("[moss] 没有 api_key")
            return None
        clean = self._prepare(text)
        if not clean:
            logger.warning("[moss] 清理后没有可念的内容，跳过")
            return None
        payload = {
            "model": self.model,
            "input": clean,
            "voice_id": self.voice_id,
            "response_format": "wav",
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=120)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.post(API_URL, json=payload, headers=headers) as r:
                    if r.status != 200:
                        body = await r.text()
                        logger.warning(f"[moss] HTTP {r.status}: {body[:200]}")
                        return None
                    blob = await r.read()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[moss] 请求异常: {exc}")
            return None
        path = os.path.join(self.data_dir, f"voice_{int(time.time() * 1000)}.wav")
        with open(path, "wb") as fh:
            fh.write(blob)
        return path

    @filter.command("说话")
    async def say_cmd(self, event: AstrMessageEvent):
        """说话 <文本> —— 让她念出来"""
        raw = (event.message_str or "").strip().lstrip("/").strip()
        text = raw.replace("说话", "", 1).strip()
        if not text:
            yield event.plain_result("说什么？")
            return
        yield event.plain_result("等我一下……")
        path = await self._tts(text)
        if not path:
            yield event.plain_result("没合成成功，看日志")
            return
        yield event.chain_result([Record.fromFileSystem(path)])

    @filter.on_llm_response()
    async def auto_voice(self, event: AstrMessageEvent, response) -> None:
        if not self.auto or not self.api_key:
            return
        try:
            text = (getattr(response, "completion_text", None) or "").strip()
            if not text or len(text) > self.max_chars:
                return
            path = await self._tts(text)
            if path:
                await self.context.send_message(
                    event.unified_msg_origin,
                    MessageChain([Record.fromFileSystem(path)]),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[moss] 自动配音失败: {exc}")
