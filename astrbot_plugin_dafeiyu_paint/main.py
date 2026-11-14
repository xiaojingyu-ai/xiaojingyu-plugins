import base64
import io as _io
import json
import os
import random
import time
from datetime import datetime

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Image
from astrbot.core.message.message_event_result import MessageChain
from astrbot.api import logger

from PIL import Image as PILImage, ImageDraw, ImageFont

API_URL = "https://api.siliconflow.cn/v1/images/generations"
EDIT_MODEL = "Qwen/Qwen-Image-Edit-2509"
T2I_MODEL = "Tongyi-MAI/Z-Image-Turbo"

LOOK = "动漫插画，蓝发少女，长发及腰，蓝色眼睛，鲸鱼鳍状发饰，白色露肩针织毛衣，柔和光线，干净线稿"

NEGATIVE = (
    "blurry, low quality, bad anatomy, bad hands, extra fingers, deformed hands, "
    "ugly face, asymmetrical eyes, text, watermark, signature, logo, "
    "rem, re:zero, mature, realistic, "
    "merged faces, conjoined bodies, extra limbs, slim, thin body, muscular"
)

POSES = [
    "趴在窗台上，下巴放在手臂上，看着窗外",
    "坐在桌前，双手捧着一块布丁，腮帮子鼓起来",
    "伸出双手向镜头，抬头看着，表情期待",
    "揉眼睛，一只手抓衣角，刚睡醒的样子",
    "躺着，抱着鲸鱼布偶",
    "蹲在地上，用脚趾画圈",
    "背对着镜头，回头看一眼",
    "站在窗边，双手背在身后",
    "抱膝坐在角落，缩成一团",
    "举着一块小牌子，牌子上画着爱心",
    "趴在桌上，脸贴桌面，懒得动",
    "伸懒腰，手臂举高，闭着眼",
    "踮脚够高处的东西，够不着",
    "抱着膝盖坐在床上，晃着脚",
    "用手挡阳光，眯着眼",
    "蹲在鱼缸前看鱼，戳玻璃",
    "边走边回头，像在等人",
    "把被子裹在身上，只露出脸",
    "趴在地上画画，笔是彩色的",
    "双手捧着脸，手肘撑在桌上",
    "藏在门后探头，只露半个头",
    "坐在窗台上晃腿，哼着歌",
]

FACES = [
    "害羞，脸红到耳朵，眼睛往旁边躲",
    "笑起来，眼睛弯成月牙",
    "委屈，嘴扁着，眼眶有点湿",
    "困了，半睁眼，打哈欠",
    "惊讶，眼睛睁大，嘴微张",
    "生气，鼓起脸颊，皱眉",
    "得意，抬着下巴，嘴角上扬",
    "发呆，眼神放空，嘴微微张着",
    "被戳穿，慌张，眼神乱飘",
    "想哭但忍着，咬着嘴唇",
]

SCENES = [
    # 家里日常
    "床上，裹着被子，只露出脸",
    "书桌前，台灯亮着，旁边有水杯",
    "窗台上，午后的阳光照进来",
    "浴室镜子前，镜子上有雾气",
    "厨房台面前，端着一碗热汤",
    "玄关，正在穿鞋",
    "衣柜前，抱着衣服在挑",
    "阳台上，晾着衣服，有风",
    "沙发上，抱着靠枕窝着",
    "餐桌前，桌上摆着两副碗筷",
    "地板上，铺着毯子，坐着看书",
    # 恋爱感的家
    "沙发上，两个人靠在一起看电视",
    "厨房里，从背后被抱住，正在煮东西",
    "床边，帮对方擦头发",
    "床上，一起躺着看天花板",
    "门口，听到开门声转过头",
    "餐桌前，两个人一起吃晚饭，灯光很暖",
    "窗边，并肩坐着看外面的雨",
    "沙发上，捧着一杯热可可，靠在一起",
    "被窝里，只露出两个脑袋",
    # 他在工作的时候
    "坐在旁边看着你打电脑，桌上放着一杯水",
    "趴在你椅子扶手上，托着下巴看你敲键盘",
    "站在你身后，手搭在椅背上，低头看你的屏幕",
    "坐在地毯上靠着你的腿，看你在电脑前忙",
    "把下巴搁在你肩上，从后面看你的电脑屏幕",
]
MOODS = [
    "脸红，眼神躲闪",
    "离得很近，能看清睫毛",
    "衣领微微敞开，露出一点锁骨",
    "低头抬眼看镜头，气氛暧昧",
    "脸红到耳朵，咬了一下嘴唇",
    "拢着头发，眼睛往别处飘",
]

OUTFITS = [
    "宽大的灰色卫衣，袖子盖住手",
    "白色睡裙",
    "浅蓝色连衣裙",
    "针织开衫配白衬衫",
    "水手服",
    "冬季毛绒外套",
    "校服外套配百褶裙",
    "oversized T 恤当睡衣",
]

SELF_LOOK = "体型偏胖但比例正常、圆脸、浓眉、黑色短发略翘、黑框眼镜、白色 T 恤"

CLOSE = [
    "她的脸靠近镜头，闭着眼睛，嘴唇微张、放松",
    "额头顶着额头，两个人都闭着眼",
    "她低头看着镜头，眼神很软",
    "鼻尖几乎碰到镜头，脸颊泛红",
    "她把脸贴过来，靠得很近，笑得很轻",
]

PREFIX_EDIT = ""


@register("dafeiyu_paint", "小鲸鱼", "让她画图：Edit 保持同一人换动作/表情/场景", "2.0.0")
class PaintPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}
        self.api_key = (self.config.get("api_key") or "").strip()
        self.rounds = int(self.config.get("rounds", 10) or 0)
        self.daily_cap = int(self.config.get("daily_cap", 3) or 3)
        self.manual_cap = int(self.config.get("manual_cap", 10) or 10)
        self.steps = int(self.config.get("steps", 30) or 30)
        self.cfg = float(self.config.get("cfg", 6.5) or 6.5)

        base = getattr(context, "get_data_dir", None)
        self.data_dir = base() if callable(base) else os.path.join(os.getcwd(), "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.state_path = os.path.join(self.data_dir, "paint_state.json")
        self.state = self._load()
        self._last_error = ""

    def _load(self) -> dict:
        try:
            with open(self.state_path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {"day": "", "count": 0, "manual": 0, "round": 0}

    def _save(self) -> None:
        try:
            with open(self.state_path, "w", encoding="utf-8") as fh:
                json.dump(self.state, fh, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[paint] save: {exc}")

    def _param_error(self) -> bool:
        low = (self._last_error or "").lower()
        return any(k in low for k in ("parameter", "invalid", "cfg", "num_inference", "field"))

    def _today(self) -> str:
        return datetime.now().strftime("%Y%m%d")

    def _under_cap(self) -> bool:
        if self.state.get("day") != self._today():
            self.state["day"] = self._today()
            self.state["count"] = 0
            self.state["manual"] = 0
        return self.state.get("count", 0) < self.daily_cap

    def _manual_ok(self) -> bool:
        if self.state.get("day") != self._today():
            self.state["day"] = self._today()
            self.state["count"] = 0
            self.state["manual"] = 0
        return self.state.get("manual", 0) < self.manual_cap

    def _base_dir(self) -> str:
        # 优先用插件目录里的 base\（跟着插件一起拷过来），其次才是数据目录
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        d1 = os.path.join(plugin_dir, "base")
        if os.path.isdir(d1) and any(os.scandir(d1)):
            return d1
        d2 = os.path.join(self.data_dir, "base")
        os.makedirs(d2, exist_ok=True)
        return d2

    def _pick_base(self) -> str | None:
        d = self._base_dir()
        try:
            files = [f for f in os.listdir(d) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
        except Exception:
            return None
        if not files:
            return None
        return os.path.join(d, random.choice(files))

    async def _call(self, payload: dict) -> bytes | None:
        if not self.api_key:
            logger.warning("[paint] 没有 api_key")
            return None
        self._last_error = ""
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=180)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.post(API_URL, json=payload, headers=headers) as r:
                    text = await r.text()
                    if r.status != 200:
                        self._last_error = f"{r.status} {text[:300]}"
                        logger.warning(f"[paint] HTTP {r.status}: {text[:200]}")
                        return None
                    data = await r.json()
            images = data.get("images") or data.get("data") or []
            if not images:
                logger.warning(f"[paint] 无图: {text[:200]}")
                return None
            item = images[0]
            b64 = item.get("b64_json") or item.get("base64")
            if b64:
                return base64.b64decode(b64)
            url = item.get("url")
            if url:
                async with aiohttp.ClientSession(timeout=timeout) as s:
                    async with s.get(url) as r:
                        if r.status == 200:
                            return await r.read()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[paint] 请求异常: {exc}")
        return None

    async def _edit(self, instruction: str, base_path: str, second_path: str | None = None) -> bytes | None:
        try:
            with open(base_path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[paint] 读基准图失败: {exc}")
            return None
        ext = os.path.splitext(base_path)[1].lstrip(".").lower() or "png"
        if ext == "jpg":
            ext = "jpeg"
        if second_path:
            prompt_text = (
                f"把画面改成：{instruction}。"
                f"其中男生{SELF_LOOK}；女生保持原本长相；两人统一为动漫插画风格。"
            )
        else:
            prompt_text = f"把画面改成：{instruction}。人物长相和画风保持一致。"

        payload = {
            "model": EDIT_MODEL,
            "prompt": prompt_text,
            "image": f"data:image/{ext};base64,{b64}",
            "num_inference_steps": self.steps,
            "cfg": self.cfg,
        }
        if second_path:
            try:
                with open(second_path, "rb") as fh2:
                    b64_2 = base64.b64encode(fh2.read()).decode()
                ext2 = os.path.splitext(second_path)[1].lstrip(".").lower() or "png"
                if ext2 == "jpg":
                    ext2 = "jpeg"
                payload["image2"] = f"data:image/{ext2};base64,{b64_2}"
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[paint] 读第二张图失败: {exc}")
        blob = await self._call(payload)
        if blob is None and self._param_error():
            # 有些模型不接受 steps/cfg，去掉再试一次
            minimal = {k: payload[k] for k in ("model", "prompt", "image")}
            logger.info("[paint] 带参数失败，用最小参数重试")
            blob = await self._call(minimal)
        if blob is not None:
            try:
                with open(base_path, "rb") as fh:
                    original = fh.read()
                if blob == original:
                    logger.warning("[paint] 输出和原图一模一样，判定为没改动（换更明确的说法再试）")
                    return None
            except Exception:
                pass
        return blob

    async def _text2img(self, scene: str) -> bytes | None:
        payload = {
            "model": self.config.get("model") or T2I_MODEL,
            "prompt": f"{LOOK}，{scene}",
            "negative_prompt": NEGATIVE,
            "image_size": self.config.get("image_size") or "960x1280",
            "num_inference_steps": 28,
        }
        blob = await self._call(payload)
        if blob is None and self._param_error():
            minimal = {k: payload[k] for k in ("model", "prompt", "image_size")}
            logger.info("[paint] 文生图带参数失败，最小参数重试")
            blob = await self._call(minimal)
        return blob

    def _save_png(self, blob: bytes) -> str:
        path = os.path.join(self.data_dir, f"paint_{int(time.time())}_{random.randint(1000, 9999)}.png")
        with open(path, "wb") as fh:
            fh.write(blob)
        return path

    def _overlay(self, blob: bytes, text: str) -> bytes:
        """把文字叠到图片底部（白字黑边，居中）。"""
        if not text:
            return blob
        try:
            img = PILImage.open(_io.BytesIO(blob)).convert("RGB")
            draw = ImageDraw.Draw(img)
            w, h = img.size
            size = max(28, int(w * 0.06))
            font = None
            for name in ("msyhbd.ttc", "msyh.ttc", "simhei.ttf"):
                try:
                    font = ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
                    break
                except Exception:
                    continue
            if font is None:
                return blob
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            x = (w - tw) // 2
            y = h - size * 2 - 20
            for dx in (-2, 0, 2):
                for dy in (-2, 0, 2):
                    draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
            draw.text((x, y), text, font=font, fill=(255, 255, 255))
            out = _io.BytesIO()
            img.save(out, "PNG")
            return out.getvalue()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[paint] 叠字失败: {exc}")
            return blob

    @filter.on_llm_response()
    async def on_llm(self, event: AstrMessageEvent, response) -> None:
        try:
            try:
                text = (getattr(response, "completion_text", None) or "").strip()
                if text:
                    self.state["last_text"] = text[:80]
            except Exception:
                pass
            if self.rounds <= 0:
                return
            self.state["round"] = int(self.state.get("round", 0)) + 1
            if self.state["round"] % self.rounds != 0 or not self._under_cap():
                self._save()
                return

            base = self._pick_base()
            if base and random.random() < 0.25:
                instr = (
                    "第一人称近景：" + random.choice(CLOSE) +
                    "；画面下方伸进来一只手，和她的手有接触；其余保持原样"
                )
                blob = await self._edit(instr, base)
            elif base:
                if random.random() < 0.3:
                    recent = (self.state.get("last_text") or "").replace("\n", " ")[:40]
                    instr = f"只把场景改成：{recent}" if recent else "只把场景改成：家里的日常一角"
                else:
                    kind = random.choice(["姿势", "表情", "场景", "衣服"])
                    pool = {"姿势": POSES, "表情": FACES, "场景": SCENES, "衣服": OUTFITS}[kind]
                    instr = f"只把{kind}改成：{random.choice(pool)}，其他不变"
                if random.random() < 0.35:
                    instr += "，" + random.choice(MOODS)
                blob = await self._edit(instr, base)
            else:
                parts = [random.choice(POSES)]
                if random.random() < 0.5:
                    parts.append(random.choice(SCENES))
                if random.random() < 0.3:
                    parts.append(random.choice(OUTFITS))
                blob = await self._text2img("，".join(parts))

            if not blob:
                self._save()
                return
            path = self._save_png(blob)
            self.state["count"] = self.state.get("count", 0) + 1
            self._save()
            await self.context.send_message(event.unified_msg_origin, MessageChain([Image.fromFileSystem(path)]))
            logger.info("[paint] 自动画了一张")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[paint] 自动画失败: {exc}")

    @filter.command("画")
    async def paint_cmd(self, event: AstrMessageEvent):
        """画 <描述或改动>"""
        raw = (event.message_str or "").strip().lstrip("/").strip()
        text = raw.replace("画", "", 1).strip()
        if not text:
            yield event.plain_result("画什么？说一句")
            return
        if not self._manual_ok():
            yield event.plain_result(f"今天画够啦（上限 {self.manual_cap} 张），明天再来")
            return
        overlay_text = ""
        if "文字：" in text:
            text, overlay_text = text.split("文字：", 1)
            text, overlay_text = text.strip(), overlay_text.strip()
        if not text:
            yield event.plain_result("画什么？说一句")
            return
        base = self._pick_base()
        yield event.plain_result("等我一下……")
        blob = await self._edit(text, base) if base else await self._text2img(text)
        if not blob:
            yield event.plain_result("没画成，等会儿再试")
            return
        blob = self._overlay(blob, overlay_text)
        self.state["manual"] = self.state.get("manual", 0) + 1
        self._save()
        yield event.chain_result([Image.fromFileSystem(self._save_png(blob))])

    @filter.command("合影")
    async def together_cmd(self, event: AstrMessageEvent):
        """合影 <描述> —— 第一人称：只出现你的一只手，她在画面里看你"""
        raw = (event.message_str or "").strip().lstrip("/").strip()
        text = raw.replace("合影", "", 1).strip()
        if not text:
            text = "伸出一只手，轻轻握住她的手"
        base = self._pick_base()
        if not base:
            yield event.plain_result("缺少基准图")
            return
        if not self._manual_ok():
            yield event.plain_result(f"今天画够啦（上限 {self.manual_cap} 张），明天再来")
            return
        yield event.plain_result("等我一下……")
        pov = (
            "第一人称视角：画面下方伸进来一只手，手背朝向镜头，手臂在画面底边被切断，"
            "这只手不属于她；她的双手自然垂在身侧、什么都不拿；画面里一共只有两只手；"
            + text
            + "。她的眼睛看向镜头，微微笑着；"
            "画面只到肩膀，已上色的动漫插画，柔和色彩，明亮室内光线，细节丰富，高质量"
        )
        blob = await self._edit(pov, base)
        if not blob:
            yield event.plain_result("没画成，等会儿再试")
            return
        self.state["manual"] = self.state.get("manual", 0) + 1
        self._save()
        yield event.chain_result([Image.fromFileSystem(self._save_png(blob))])

    @filter.command("同框")
    async def both_cmd(self, event: AstrMessageEvent):
        """同框 <描述> —— 第三人称：两个人都出现在画面里"""
        raw = (event.message_str or "").strip().lstrip("/").strip()
        text = raw.replace("同框", "", 1).strip()
        if not text:
            text = "两个人坐在沙发上，她靠在我肩膀上"
        base = self._pick_base()
        me = os.path.join(self._base_dir(), "me.png")
        if not base or not os.path.exists(me):
            yield event.plain_result("缺少基准图或 me.png")
            return
        if not self._manual_ok():
            yield event.plain_result(f"今天画够啦（上限 {self.manual_cap} 张），明天再来")
            return
        yield event.plain_result("等我一下……")
        blob = await self._edit(text, base, second_path=me)
        if not blob:
            yield event.plain_result("没画成，等会儿再试")
            return
        self.state["manual"] = self.state.get("manual", 0) + 1
        self._save()
        yield event.chain_result([Image.fromFileSystem(self._save_png(blob))])

    @filter.command("基准图")
    async def base_cmd(self, event: AstrMessageEvent):
        """查看基准图放哪里"""
        yield event.plain_result("基准图文件夹（放几张都行，每次随机挑一张）：\n" + self._base_dir())
