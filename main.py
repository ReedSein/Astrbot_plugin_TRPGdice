import random
import os
import json
import re
import uuid
import asyncio
from typing import Optional, List, Tuple, Dict, Any, Union

import aiofiles
import aiohttp
from collections import deque
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import Plain

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

class TrueRandomManager:
    """
    真随机数管理器 (基于 Random.org)
    策略: 缓存 0-1 之间的小数，适用于任意面值的骰子。
    """
    def __init__(self, buffer_size=100):
        self.buffer = deque()
        self.buffer_size = buffer_size
        self.is_fetching = False
        self.api_url = "https://www.random.org/decimal-fractions/"
        # 保留20位小数以确保精度足够
        self.params = {
            "num": str(buffer_size),
            "dec": "20",
            "col": "1",
            "format": "plain",
            "rnd": "new"
        }

    async def get_fraction(self) -> float:
        """
        获取一个 0-1 之间的随机小数。
        优先从缓存取，缓存不足触发异步补充，缓存为空自动降级。
        """
        # 1. 检查缓存水位，低水位触发补充 (例如少于 20% 时)
        if len(self.buffer) < self.buffer_size * 0.2 and not self.is_fetching:
            asyncio.create_task(self._refill_buffer())

        # 2. 尝试从缓存取值
        if self.buffer:
            return self.buffer.popleft()
        
        # 3. 缓存为空，降级到伪随机
        # logger.debug("TrueRandom buffer empty, fallback to pseudo-random.")
        return random.random()

    async def _refill_buffer(self):
        """异步补充缓存，严禁并发请求"""
        if self.is_fetching:
            return
        
        self.is_fetching = True
        try:
            # logger.debug("Refilling TrueRandom buffer...")
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, params=self.params, timeout=10) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        # 解析返回的纯文本数字
                        numbers = []
                        for line in text.strip().split('\n'):
                            try:
                                if line.strip():
                                    numbers.append(float(line.strip()))
                            except ValueError:
                                pass
                        
                        if numbers:
                            self.buffer.extend(numbers)
                            # logger.info(f"TrueRandom buffer refilled. Current size: {len(self.buffer)}")
                        else:
                            logger.warning("Random.org returned no valid numbers.")
                    else:
                        logger.warning(f"Random.org API failed: {resp.status}")
        except Exception as e:
            logger.warning(f"Failed to connect to Random.org: {e}")
        finally:
            self.is_fetching = False

# ================= 古典风格帮助菜单模版 (去联网稳定版) =================
HELP_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <style>
        body {
            margin: 0; padding: 40px; background-color: transparent;
            font-family: 'Songti SC', 'SimSun', 'Times New Roman', 'Noto Serif SC', serif;
            display: flex; justify-content: center; align-items: flex-start;
            width: fit-content; min-width: 100%;
        }
        .parchment {
            background-color: #f3e5ce;
            background-image: radial-gradient(circle at center, #f8f1e0 0%, #f3e5ce 80%, #e6d2b0 100%);
            padding: 60px; border: 12px double #5c4033; border-radius: 6px;
            box-shadow: 15px 15px 30px rgba(0,0,0,0.4); width: 1000px; color: #43302b;
            position: relative; margin: 0 auto;
        }
        .parchment::before {
            content: ""; position: absolute; top: 15px; left: 15px; right: 15px; bottom: 15px;
            border: 3px solid #a89f91; pointer-events: none;
        }
        .header { text-align: center; margin-bottom: 50px; border-bottom: 3px solid #5c4033; padding-bottom: 25px; }
        .title { font-size: 56px; font-weight: bold; letter-spacing: 10px; margin: 0; text-shadow: 2px 2px 0px rgba(255,255,255,0.6); color: #2c1e1a; }
        .subtitle { font-size: 24px; font-style: italic; color: #7a6256; margin-top: 10px; font-family: 'Times New Roman', serif; }
        .section { margin-bottom: 40px; }
        .section-title { font-size: 28px; font-weight: bold; background-color: #5c4033; color: #f3e5ce; padding: 8px 20px; display: inline-block; border-radius: 4px; margin-bottom: 20px; box-shadow: 3px 3px 6px rgba(0,0,0,0.25); }
        .command-list { list-style: none; padding: 0; margin: 0; }
        .command-item { margin-bottom: 15px; display: flex; flex-direction: column; border-bottom: 1px dashed #d1c0a5; padding-bottom: 12px; }
        .cmd-row { display: flex; align-items: baseline; margin-bottom: 6px; }
        .cmd { font-family: 'Consolas', 'Courier New', monospace; font-weight: bold; color: #8b0000; margin-right: 15px; font-size: 24px; white-space: nowrap; }
        .desc { font-size: 20px; color: #43302b; font-weight: bold; }
        .example { font-size: 18px; color: #6d5848; font-style: italic; margin-left: 20px; display: block; }
        .true-random-badge {
            text-align: center; margin-top: 30px; padding: 15px;
            background: rgba(92, 64, 51, 0.1); border-radius: 8px;
            border: 1px solid #a89f91;
        }
        .true-random-title { font-weight: bold; font-size: 20px; color: #8b0000; margin-bottom: 5px; }
        .true-random-desc { font-size: 16px; color: #5c4033; }
        .footer { text-align: center; margin-top: 30px; font-size: 18px; color: #8c7b70; font-style: italic; border-top: 2px solid #a89f91; padding-top: 20px; font-family: 'Times New Roman', serif; }
    </style>
</head>
<body>
    <div class="parchment">
        <div class="header">
            <h1 class="title">调查员指南</h1>
            <div class="subtitle">Investigator's Handbook</div>
        </div>
        {% for section in sections %}
        <div class="section">
            <div class="section-title">{{ section.title }}</div>
            <ul class="command-list">
                {% for cmd in section.commands %}
                <li class="command-item">
                    <div class="cmd-row">
                        <span class="cmd">{{ cmd.syntax }}</span>
                        <span class="desc">{{ cmd.desc }}</span>
                    </div>
                    <span class="example">示例: {{ cmd.example }}</span>
                </li>
                {% endfor %}
            </ul>
        </div>
        {% endfor %}
        
        <div class="true-random-badge">
            <div class="true-random-title">⚛ True Randomness Powered by Random.org</div>
            <div class="true-random-desc">
                本插件核心掷骰逻辑集成了大气噪声真随机源。
                <br>每一次命运的判定，都来自宇宙深处的混沌涨落，而非伪随机算法的平庸重复。
                <br>(当网络连接不稳定时，将自动降级至标准伪随机模式)
            </div>
        </div>

        <div class="footer">Designed for TRPG Players · RosaのTRPG<br>"May the dice be ever in your favor."</div>
    </div>
</body>
</html>
"""

@register("astrbot_plugin_TRPG", "shiroling", "TRPG玩家用骰 (Refactored)", "1.2.7")
class DicePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        self.data_root = os.path.join(os.getcwd(), "data", "astrbot_plugin_TRPG")
        self.chara_data_dir = os.path.join(self.data_root, "chara_data")
        os.makedirs(self.chara_data_dir, exist_ok=True)
        
        self.phobias: Dict[str, str] = {}
        self.manias: Dict[str, str] = {}
        self._load_static_resources()
        
        # 初始化真随机管理器
        self.rng_manager = None
        if self.config.get("enable_true_random", True):
            buffer_size = self.config.get("true_random_buffer_size", 100)
            self.rng_manager = TrueRandomManager(buffer_size=buffer_size)

    def _load_static_resources(self):
        """加载静态资源文件"""
        try:
            phobia_path = os.path.join(PLUGIN_DIR, "phobias.json")
            if os.path.exists(phobia_path):
                with open(phobia_path, "r", encoding="utf-8") as f:
                    self.phobias = json.load(f).get("phobias", {})
            
            mania_path = os.path.join(PLUGIN_DIR, "mania.json")
            if os.path.exists(mania_path):
                with open(mania_path, "r", encoding="utf-8") as f:
                    self.manias = json.load(f).get("manias", {})
            
            logger.info(f"TRPG Resources Loaded: {len(self.phobias)} phobias, {len(self.manias)} manias.")
        except Exception as e:
            logger.error(f"Failed to load TRPG static resources: {e}")

    # ================= 异步文件操作 =================
    
    def _get_user_folder(self, user_id: str) -> str:
        folder = os.path.join(self.chara_data_dir, str(user_id))
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        return folder

    def _get_character_path(self, user_id: str, chara_id: str) -> str:
        return os.path.join(self._get_user_folder(user_id), f"{chara_id}.json")

    def _get_current_ref_path(self, user_id: str) -> str:
        return os.path.join(self._get_user_folder(user_id), "current.txt")

    async def _get_all_characters(self, user_id: str) -> Dict[str, str]:
        """获取用户所有人物卡 {name: id}"""
        folder = self._get_user_folder(user_id)
        characters = {}
        try:
            for filename in os.listdir(folder):
                if filename.endswith(".json"):
                    path = os.path.join(folder, filename)
                    try:
                        async with aiofiles.open(path, "r", encoding="utf-8") as f:
                            content = await f.read()
                            data = json.loads(content)
                            if "name" in data and "id" in data:
                                characters[data["name"]] = data["id"]
                    except json.JSONDecodeError:
                        logger.warning(f"Corrupted character file: {filename}")
                        continue
        except Exception as e:
            logger.error(f"Error listing characters for {user_id}: {e}")
        return characters

    async def _get_current_character_id(self, user_id: str) -> Optional[str]:
        path = self._get_current_ref_path(user_id)
        if os.path.exists(path):
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                return content.strip()
        return None

    async def _set_current_character_id(self, user_id: str, chara_id: str):
        path = self._get_current_ref_path(user_id)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(str(chara_id))

    async def _load_character_data(self, user_id: str, chara_id: str) -> Optional[dict]:
        path = self._get_character_path(user_id, chara_id)
        if os.path.exists(path):
            try:
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    return json.loads(content)
            except Exception as e:
                logger.error(f"Error loading character {chara_id}: {e}")
                return None
        return None

    async def _save_character_data(self, user_id: str, chara_id: str, data: dict):
        path = self._get_character_path(user_id, chara_id)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=4, ensure_ascii=False))

    async def _get_current_character(self, user_id: str) -> Optional[dict]:
        cid = await self._get_current_character_id(user_id)
        if cid:
            return await self._load_character_data(user_id, cid)
        return None

    # ================= 核心骰子逻辑 =================

    async def _roll_single(self, faces: int) -> int:
        """
        掷单个骰子，使用真随机源。
        公式: floor(fraction * faces) + 1
        """
        if self.rng_manager:
            fraction = await self.rng_manager.get_fraction()
            return int(fraction * faces) + 1
        else:
            return random.randint(1, faces)

    async def _roll_multi(self, count: int, faces: int) -> List[int]:
        max_dice = self.config.get("max_dice_count", 50)
        # 限制最大骰子数，防止 DoS
        count = min(count, max_dice)
        # 串行获取随机数（因为 get_fraction 内部是非阻塞的）
        return [await self._roll_single(faces) for _ in range(count)]

    async def _safe_parse_dice(self, expression: str) -> Tuple[Optional[int], str]:
        """
        解析并执行简单的骰子表达式。
        支持: NdM, +, -, *, 纯数字, k(Keep)
        """
        expression = expression.lower().replace(" ", "")
        if not re.match(r"^[0-9d+\-*k]+$", expression):
            return None, "表达式含有非法字符"
        
        safe_expr = expression.replace("-", "+-")
        parts = safe_expr.split("+")
        
        total = 0
        details = []
        
        try:
            for part in parts:
                if not part: continue
                
                sign = 1
                if part.startswith("-"):
                    sign = -1
                    part = part[1:]
                
                if "d" in part:
                    match = re.match(r"^(\d*)d(\d+)(?:k(\d+))?$", part)
                    if not match: 
                        return None, f"无法解析骰子部分: {part}"
                    
                    count_str, faces_str, keep_str = match.groups()
                    count = int(count_str) if count_str else 1
                    faces = int(faces_str)
                    
                    if count > self.config.get("max_dice_count", 50):
                        return None, f"骰子数量过多 (上限 {self.config.get('max_dice_count', 50)})"
                    
                    rolls = await self._roll_multi(count, faces)
                    
                    if keep_str:
                        keep = int(keep_str)
                        selected = sorted(rolls, reverse=True)[:keep]
                        subtotal = sum(selected)
                        details.append(f"({' + '.join(map(str, rolls))})选{keep}")
                    else:
                        subtotal = sum(rolls)
                        if len(rolls) == 1:
                             details.append(f"{subtotal}")
                        else:
                             details.append(f"({' + '.join(map(str, rolls))})")
                    
                    total += subtotal * sign
                
                elif "*" in part:
                    factors = part.split("*")
                    sub_prod = 1
                    for f in factors:
                        sub_prod *= int(f)
                    total += sub_prod * sign
                    details.append(str(sub_prod))
                    
                else:
                    val = int(part)
                    total += val * sign
                    details.append(str(val))
                    
        except Exception as e:
            return None, f"计算错误: {str(e)}"
        
        if not details:
            return 0, "0"
        
        expr_str = " + ".join(details).replace("+ -", "- ")
        if expr_str == str(total):
            return total, str(total)
            
        return total, f"{expr_str} = {total}"

    def _get_flavor_text(self, result_type: str) -> str:
        if not self.config.get("enable_flavor_text", True): return ""
        
        key_map = {
            "🎉 大成功": "flavor_critical_success",
            "✨ 极难成功": "flavor_extreme_success",
            "✔ 困难成功": "flavor_hard_success",
            "✅ 成功": "flavor_success",
            "❌ 失败": "flavor_failure",
            "💀 大失败": "flavor_fumble"
        }
        
        config_key = key_map.get(result_type)
        if not config_key: return ""
        
        texts = self.config.get(config_key, [])
        if not texts: return ""
        
        return random.choice(texts)

    def _check_result(self, total: int, target: int) -> str:
        if target <= 0: return "未知"
        
        result_str = ""
        if total == 1:
            result_str = "🎉 大成功"
        elif total <= target // 5:
            result_str = "✨ 极难成功"
        elif total <= target // 2:
            result_str = "✔ 困难成功"
        elif total <= target:
            result_str = "✅ 成功"
        elif total == 100:
            result_str = "💀 大失败"
        elif total >= 96 and target < 50:
            result_str = "💀 大失败"
        else:
            result_str = "❌ 失败"
            
        flavor = self._get_flavor_text(result_str)
        if flavor:
            return f"{result_str}\n> {flavor}"
        return result_str

    # ================= 指令处理 Handlers =================

    @filter.command("roll", alias={"r", "掷骰"})
    async def roll_dice(self, event: AstrMessageEvent, expression: str = None, target: int = None):
        """普通掷骰，支持 /r 1d100 50 或 /r 3#1d20"""
        default_faces = self.config.get("default_dice_faces", 100)
        if expression is None:
            expression = f"1d{default_faces}"
        
        if "#" in expression:
            try:
                parts = expression.split("#", 1)
                count_str = parts[0].strip()
                expr_part = parts[1].strip()
                count = int(count_str) if count_str else 1
                
                if count > 10:
                    yield event.plain_result("⚠️ 既然是复读，那就不要超过 10 次哦。 সন")
                    return
                if count < 1:
                    yield event.plain_result("⚠️ 至少要掷 1 次吧？")
                    return
                
                results = []
                for i in range(count):
                    total, desc = await self._safe_parse_dice(expr_part)
                    if total is None:
                        yield event.plain_result(f"⚠️ 第 {i+1} 次解析失败: {desc}")
                        return
                    
                    line = f"🎲{i+1}: {desc}"
                    if target is not None:
                        check_res = self._check_result(total, target)
                        simple_check = check_res.split('\n')[0]
                        line += f" ({simple_check})"
                    results.append(line)
                
                yield event.plain_result("\n".join(results))
                return

            except ValueError:
                yield event.plain_result("⚠️ 复读格式错误，应为 3#1d20")
                return
        
        total, desc = await self._safe_parse_dice(expression)
        if total is None:
            yield event.plain_result(f"⚠️ {desc}")
            return
            
        msg = f"🎲 掷骰: {expression}\n结果: {desc}"
        if target is not None:
            check_res = self._check_result(total, target)
            msg += f"\n判定 ({target}): {check_res}"
        yield event.plain_result(msg)

    @filter.command("rd")
    async def roll_d100(self, event: AstrMessageEvent):
        """1d100 快捷掷骰"""
        roll = await self._roll_single(100)
        yield event.plain_result(f"{event.get_sender_name()} 进行了 1d100 投掷: {roll}")

    @filter.command("rh", alias={"暗骰"})
    async def roll_hidden(self, event: AstrMessageEvent, expression: str = None):
        """私聊发送掷骰结果 (支持复读)"""
        default_faces = self.config.get("default_dice_faces", 100)
        if expression is None:
            expression = f"1d{default_faces}"

        result_msg = ""
        if "#" in expression:
            try:
                parts = expression.split("#", 1)
                count = int(parts[0].strip()) if parts[0].strip() else 1
                expr_part = parts[1].strip()
                
                if count > 10:
                    yield event.plain_result("⚠️ 暗骰复读次数太多啦 (上限10)。")
                    return
                    
                lines = []
                for i in range(count):
                    total, desc = await self._safe_parse_dice(expr_part)
                    if total is None:
                        yield event.plain_result(f"⚠️ 格式错误: {desc}")
                        return
                    lines.append(f"🎲{i+1}: {desc}")
                result_msg = f"🎲 暗骰复读 ({count}次):\n" + "\n".join(lines)
            except ValueError:
                yield event.plain_result("⚠️ 格式错误。")
                return
        else:
            total, desc = await self._safe_parse_dice(expression)
            if total is None:
                 yield event.plain_result(f"⚠️ 暗骰格式错误: {desc}")
                 return
            result_msg = f"🎲 暗骰结果: {expression} = {total}"

        try:
            await self.context.send_message(
                target=event.unified_msg_origin,
                message_chain=[Plain(result_msg)],
            )
            yield event.plain_result(f"🎲 {event.get_sender_name()} 进行了一次暗骰。")
            
            if event.get_platform_name() == "aiocqhttp" and event.message_obj.group_id:
                 user_id = event.get_sender_id()
                 try:
                    await event.bot.api.call_action("send_private_msg", user_id=user_id, message=result_msg)
                 except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"Hidden roll failed: {e}")
            yield event.plain_result("⚠️ 暗骰发送失败，请确保你已添加机器人好友。")

    @filter.command_group("st")
    def st_group(self):
        pass

    @st_group.command("create")
    async def st_create(self, event: AstrMessageEvent, name: str, attributes: str):
        """创建人物卡: /st create 名字 力量50体质60..."""
        user_id = event.get_sender_id()
        chars = await self._get_all_characters(user_id)
        if name in chars:
            yield event.plain_result(f"⚠️ 人物卡 **{name}** 已存在！")
            return
            
        matches = re.findall(r"([\u4e00-\u9fa5a-zA-Z_]+)\s*(\d+)", attributes)
        
        if not matches:
             yield event.plain_result("⚠️ 未识别到属性数据，请使用格式：力量50 敏捷60")
             return
             
        attr_dict = {k: int(v) for k, v in matches}
        
        if "hp" in attr_dict and "max_hp" not in attr_dict: attr_dict["max_hp"] = attr_dict["hp"]
        if "san" in attr_dict and "max_san" not in attr_dict: attr_dict["max_san"] = attr_dict["san"]
        if "mp" in attr_dict and "max_mp" not in attr_dict: attr_dict["max_mp"] = attr_dict["mp"]
        
        chara_id = str(uuid.uuid4())
        data = { "id": chara_id, "name": name, "attributes": attr_dict }
        
        await self._save_character_data(user_id, chara_id, data)
        await self._set_current_character_id(user_id, chara_id)
        yield event.plain_result(f"✅ 人物卡 **{name}** 创建成功并已选中！")

    @st_group.command("show")
    async def st_show(self, event: AstrMessageEvent, ignore_arg: str = ""):
        """显示当前人物卡"""
        user_id = event.get_sender_id()
        data = await self._get_current_character(user_id)
        if not data:
            yield event.plain_result("⚠️ 当前未选中人物卡，请先使用 `/st create` 或 `/st change`。")
            return
            
        lines = [f"📜 **{data['name']}** (ID: ...{data['id'][-4:]})"]
        lines.append("-" * 20)
        
        attrs = data.get("attributes", {})
        sorted_keys = sorted(attrs.keys())
        
        chunk_size = 3
        for i in range(0, len(sorted_keys), chunk_size):
            chunk = sorted_keys[i:i+chunk_size]
            line_parts = [f"{k}:{attrs[k]}" for k in chunk]
            lines.append("  ".join(line_parts))
            
        yield event.plain_result("\n".join(lines))

    @st_group.command("list")
    async def st_list(self, event: AstrMessageEvent, ignore_arg: str = ""):
        """列出所有人物卡"""
        user_id = event.get_sender_id()
        chars = await self._get_all_characters(user_id)
        curr_id = await self._get_current_character_id(user_id)
        
        if not chars:
            yield event.plain_result("📭 你还没有创建过人物卡。")
            return
            
        msg = ["📂 **你的人物卡列表**："]
        for name, cid in chars.items():
            mark = "👈 (当前)" if cid == curr_id else ""
            msg.append(f"- {name} {mark}")
        yield event.plain_result("\n".join(msg))

    @st_group.command("change")
    async def st_change(self, event: AstrMessageEvent, name: str):
        user_id = event.get_sender_id()
        chars = await self._get_all_characters(user_id)
        if name not in chars:
            yield event.plain_result(f"⚠️ 找不到名为 **{name}** 的人物卡。")
            return
        await self._set_current_character_id(user_id, chars[name])
        yield event.plain_result(f"🔄 已切换至 **{name}**。")

    @st_group.command("update")
    async def st_update(self, event: AstrMessageEvent, attr: str, value_expr: str):
        """更新属性: /st update hp -1d6"""
        user_id = event.get_sender_id()
        data = await self._get_current_character(user_id)
        if not data:
            yield event.plain_result("⚠️ 未选中人物卡。")
            return
            
        attrs = data["attributes"]
        current_val = attrs.get(attr, 0)
        
        operator = None
        calc_part = value_expr
        
        if value_expr.startswith(("+", "-", "*")):
            operator = value_expr[0]
            calc_part = value_expr[1:]
        
        change_val, change_desc = await self._safe_parse_dice(calc_part)
        
        if change_val is None:
            yield event.plain_result(f"⚠️ 数值解析错误: {change_desc}")
            return
            
        old_val = current_val
        new_val = 0
        
        if operator == "+": new_val = current_val + change_val
        elif operator == "-": new_val = current_val - change_val
        elif operator == "*": new_val = int(current_val * change_val)
        else: new_val = change_val
        
        attrs[attr] = new_val
        await self._save_character_data(user_id, data["id"], data)
        
        msg = f"📝 **{data['name']}** 的 {attr} 更新:\n"
        if operator:
            msg += f"{old_val} {operator} {change_desc} = **{new_val}**"
        else:
            msg += f"{old_val} → **{new_val}**"
        yield event.plain_result(msg)

    @filter.command("ra")
    async def roll_check(self, event: AstrMessageEvent, attr_or_target: str = None, target_val: int = None):
        """技能检定 /ra [技能名] [目标值] 或 /ra [目标值]"""
        user_name = event.get_sender_name()
        
        # 1. 处理无参数情况: 仅投掷 1d100
        if attr_or_target is None:
            roll = await self._roll_single(100)
            yield event.plain_result(f"{user_name} 进行了 1d100 投掷: {roll}")
            return

        target = None
        skill_name = "检定"

        # 2. 尝试解析参数
        # 情况 A: /ra 50 (单参数且为数字)
        if attr_or_target.isdigit() and target_val is None:
            target = int(attr_or_target)
            skill_name = "数值"
        
        # 情况 B: /ra 侦查 (单参数且为属性名)
        elif target_val is None:
            skill_name = attr_or_target
            card = self._get_current_card(event)
            if not card:
                yield event.plain_result(f"错误: 当前未选中人物卡，请使用 /ra [属性] [数值] 或直接输入数值。")
                return
            target = card.get(skill_name)
            if target is None:
                yield event.plain_result(f"错误: 人物卡中未找到属性 '{skill_name}'")
                return
        
        # 情况 C: /ra 侦查 60 (双参数)
        else:
            skill_name = attr_or_target
            target = target_val

        # 3. 执行投掷
        roll = await self._roll_single(100)
        
        # 4. 判定结果
        res_type = ""
        if roll == 1: res_type = "critical_success"
        elif roll == 100: res_type = "fumble"
        elif roll <= 5 and roll <= target // 5: res_type = "critical_success" # 兼容规则：1-5且小于1/5
        elif roll > 95 and target < 50: res_type = "fumble" # 目标值<50时, 96-100为大失败
        elif roll <= target // 5: res_type = "extreme_success"
        elif roll <= target // 2: res_type = "hard_success"
        elif roll <= target: res_type = "success"
        else: res_type = "failure"

        # 修正大失败/大成功的边界逻辑 (简化版)
        if roll == 1: res_type = "critical_success"
        if roll == 100: res_type = "fumble"

        # 获取描述
        res_map = {
            "critical_success": "大成功",
            "extreme_success": "极难成功",
            "hard_success": "困难成功",
            "success": "成功",
            "failure": "失败",
            "fumble": "大失败"
        }
        res_text = res_map.get(res_type, "未知")
        
        # 插入风味文本
        flavor = ""
        if self.config.get("enable_flavor_text", True):
            flavor_list = self.config.get(f"flavor_{res_type}", [])
            if flavor_list:
                flavor = f"\n「{random.choice(flavor_list)}」"

        yield event.plain_result(f"{user_name} 进行了 {skill_name} 检定: 1d100={roll}/{target} {res_text}{flavor}")

    @filter.command("sanc", alias={"san"}) 
    async def san_check(self, event: AstrMessageEvent, expr: str):
        """SC: /sanc 1/1d3"""
        user_id = event.get_sender_id()
        data = await self._get_current_character(user_id)
        if not data:
             yield event.plain_result("⚠️ 请先加载人物卡 (/st change)")
             return
             
        san = data["attributes"].get("san")
        if san is None:
             yield event.plain_result("⚠️ 当前人物卡没有 san 属性。")
             return
             
        if "/" not in expr:
            yield event.plain_result("⚠️ 格式错误，应为：成功扣除/失败扣除 (例: /sanc 1/1d6)")
            return
            
        success_expr, fail_expr = expr.split("/", 1)
        
        roll = random.randint(1, 100)
        is_success = roll <= san
        
        loss_expr = success_expr if is_success else fail_expr
        loss, loss_desc = await self._safe_parse_dice(loss_expr)
        if loss is None: loss = 0 
        
        new_san = max(0, san - loss)
        data["attributes"]["san"] = new_san
        await self._save_character_data(user_id, data["id"], data)
        
        res_str = "✅ 成功" if is_success else "❌ 失败"
        msg = (
            f"🧠 **San Check**\n"
            f"掷骰: {roll}/{san} ({res_str})\n"
            f"扣除: {loss_desc} 点\n"
            f"当前 San: {san} → **{new_san}**"
        )
        yield event.plain_result(msg)

    @filter.command("ti", alias={"临时疯狂"})
    async def temp_insanity(self, event: AstrMessageEvent, ignore_arg: str = ""):
        """抽取临时疯狂"""
        roll = random.randint(1, 10)
        insanities = [
            "失忆：只记得最后身处的安全地点。",
            "假性残疾：心理性失明、失聪或肢体缺失。",
            "暴力倾向：对周围所有人展开攻击。",
            "偏执：认为所有人都在图谋不轨。",
            "人际依赖：将某人视为唯一的依靠。",
            "昏厥：当场昏倒。",
            "逃避行为：不顾一切地试图逃离。",
            "歇斯底里：大笑、哭泣或尖叫。",
            "恐惧：产生一种特定的恐惧症。",
            "躁狂：产生一种特定的躁狂症。"
        ]
        
        result = insanities[roll-1]
        extra_msg = ""
        
        if "恐惧" in result and self.phobias:
            idx = str(random.randint(1, 100))
            extra_msg = f"\n症状: {self.phobias.get(idx, '未知恐惧')}"
        elif "躁狂" in result and self.manias:
            idx = str(random.randint(1, 100))
            extra_msg = f"\n症状: {self.manias.get(idx, '未知躁狂')}"
            
        yield event.plain_result(f"🤪 **临时疯狂 (1d10={roll})**\n{result}{extra_msg}")

    # ================= 帮助指令 =================
    @filter.command("dicehelp", alias={"subrosa_dice"})
    async def dice_help(self, event: AstrMessageEvent, ignore_arg: str = ""):
        """显示帮助菜单"""
        data = {
            "sections": [
                {
                    "title": "🎲 基础仪轨 (Basic)",
                    "commands": [
                        {"syntax": "/rd", "desc": "快捷进行一次 1d100 投掷", "example": "/rd (直接出结果)"},
                        {"syntax": "/r [表达式]", "desc": "投掷指定骰子表达式", "example": "/r 2d10+5"},
                        {"syntax": "/r [次数]#[表达式]", "desc": "重复投掷多次表达式", "example": "/r 3#4d6k3 (投3次，每次4d6取前3)"},
                        {"syntax": "/r [表达式] [判定值]", "desc": "投掷并与目标值对比判定", "example": "/r 1d100 60"},
                        {"syntax": "/rh [表达式]", "desc": "暗骰模式，结果私聊发送给指令者", "example": "/rh 1d100 (仅你自己可见)"},
                    ]
                },
                {
                    "title": "📜 调查员档案 (Profile)",
                    "commands": [
                        {"syntax": "/st create [名] [属性]", "desc": "创建一张新的人物卡", "example": "/st create 洛萨 力量60 敏捷70 智力80"},
                        {"syntax": "/st show", "desc": "查看当前选中的人物卡详情", "example": "/st show"},
                        {"syntax": "/st list", "desc": "查看所有已保存的人物卡", "example": "/st list"},
                        {"syntax": "/st change [名]", "desc": "切换当前激活的人物卡", "example": "/st change 洛萨"},
                        {"syntax": "/st update [属性] [值]", "desc": "修改当前卡属性 (支持加减公式)", "example": "/st update hp -1d3 (扣除1d3点血量)"},
                    ]
                },
                {
                    "title": "🧠 理智与检定 (Check)",
                    "commands": [
                        {"syntax": "/ra [数值]", "desc": "以指定数值为目标进行快捷检定", "example": "/ra 60 (以60为目标进行检定)"},
                        {"syntax": "/ra [属性名]", "desc": "自动读取当前卡属性进行检定", "example": "/ra 侦查 (自动读取侦查数值)"},
                        {"syntax": "/ra [属性] [数值]", "desc": "指定属性和数值进行检定", "example": "/ra 射击 80"},
                        {"syntax": "/sanc [成功]/[失败]", "desc": "San Check，自动计算并扣除理智", "example": "/sanc 1/1d6 (成功扣1，失败扣1d6)"},
                        {"syntax": "/ti", "desc": "抽取临时疯狂症状 (含恐惧/躁狂)", "example": "/ti"},
                    ]
                }
            ]
        }
        url = await self.html_render(HELP_HTML_TEMPLATE, data, options={"full_page": True})
        yield event.image_result(url)
