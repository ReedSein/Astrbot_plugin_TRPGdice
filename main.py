import random
import os
import json
import re
import uuid
import asyncio
import aiofiles
from typing import Optional, List, Tuple, Dict, Any

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

# ================= 古典风格帮助菜单模版 (高清重制版) =================
HELP_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700&display=swap');

        body {
            margin: 0;
            padding: 40px; /* 增加留白 */
            background-color: transparent;
            font-family: 'Noto Serif SC', 'Songti SC', serif;
        }

        .parchment {
            background-color: #f3e5ce;
            /* 更加细腻的纸张纹理效果 */
            background-image: 
                radial-gradient(circle at center, #f8f1e0 0%, #f3e5ce 80%, #e6d2b0 100%);
            padding: 60px; /* 增加内边距 */
            border: 12px double #5c4033; /* 加粗边框 */
            border-radius: 6px;
            box-shadow: 15px 15px 30px rgba(0,0,0,0.4);
            
            /* 关键修改：增加宽度以提高清晰度 */
            width: 900px; 
            
            color: #43302b;
            position: relative;
        }

        /* 装饰性内边框 */
        .parchment::before {
            content: "";
            position: absolute;
            top: 15px; left: 15px; right: 15px; bottom: 15px;
            border: 3px solid #a89f91;
            pointer-events: none;
        }

        .header {
            text-align: center;
            margin-bottom: 50px;
            border-bottom: 3px solid #5c4033;
            padding-bottom: 25px;
        }

        .title {
            font-size: 56px; /* 增大标题 */
            font-weight: bold;
            letter-spacing: 10px;
            margin: 0;
            text-shadow: 2px 2px 0px rgba(255,255,255,0.6);
            color: #2c1e1a;
        }

        .subtitle {
            font-size: 24px; /* 增大副标题 */
            font-style: italic;
            color: #7a6256;
            margin-top: 10px;
            font-family: 'Times New Roman', serif;
        }

        .section {
            margin-bottom: 40px;
        }

        .section-title {
            font-size: 28px; /* 增大章节标题 */
            font-weight: bold;
            background-color: #5c4033;
            color: #f3e5ce;
            padding: 8px 20px;
            display: inline-block;
            border-radius: 4px;
            margin-bottom: 20px;
            box-shadow: 3px 3px 6px rgba(0,0,0,0.25);
        }

        .command-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }

        .command-item {
            margin-bottom: 12px;
            display: flex;
            align-items: baseline;
            border-bottom: 2px dashed #d1c0a5; /* 加粗虚线 */
            padding-bottom: 8px;
        }

        .cmd {
            font-family: 'Consolas', 'Courier New', monospace;
            font-weight: bold;
            color: #8b0000;
            margin-right: 20px;
            font-size: 26px; /* 增大指令字体 */
            white-space: nowrap;
        }

        .desc {
            font-size: 22px; /* 增大描述字体 */
            color: #43302b;
            line-height: 1.5;
        }

        .footer {
            text-align: center;
            margin-top: 50px;
            font-size: 18px; /* 增大页脚 */
            color: #8c7b70;
            font-style: italic;
            border-top: 2px solid #a89f91;
            padding-top: 20px;
            font-family: 'Times New Roman', serif;
        }
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
                    <span class="cmd">{{ cmd.syntax }}</span>
                    <span class="desc">{{ cmd.desc }}</span>
                </li>
                {% endfor %}
            </ul>
        </div>
        {% endfor %}

        <div class="footer">
            Designed for TRPG Players · RosaのTRPG<br>
            "May the dice be ever in your favor."
        </div>
    </div>
</body>
</html>
"""

@register("astrbot_plugin_TRPG", "shiroling", "TRPG玩家用骰 (Refactored)", "1.2.3")
class DicePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # ================= 数据路径配置 =================
        self.data_root = os.path.join(os.getcwd(), "data", "astrbot_plugin_TRPG")
        self.chara_data_dir = os.path.join(self.data_root, "chara_data")
        os.makedirs(self.chara_data_dir, exist_ok=True)
        
        # ================= 加载静态资源 =================
        self.phobias = {}
        self.manias = {}
        self._load_static_resources()

    def _load_static_resources(self):
        try:
            with open(os.path.join(PLUGIN_DIR, "phobias.json"), "r", encoding="utf-8") as f:
                self.phobias = json.load(f).get("phobias", {})
            with open(os.path.join(PLUGIN_DIR, "mania.json"), "r", encoding="utf-8") as f:
                self.manias = json.load(f).get("manias", {})
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
        folder = self._get_user_folder(user_id)
        characters = {}
        try:
            for filename in os.listdir(folder):
                if filename.endswith(".json"):
                    path = os.path.join(folder, filename)
                    async with aiofiles.open(path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        data = json.loads(content)
                        characters[data["name"]] = data["id"]
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
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        return None

    async def _save_character_data(self, user_id: str, chara_id: str, data: dict):
        path = self._get_character_path(user_id, chara_id)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=4, ensure_ascii=False))

    async def _delete_character_file(self, user_id: str, chara_id: str):
        path = self._get_character_path(user_id, chara_id)
        if os.path.exists(path):
            os.remove(path)

    async def _get_current_character(self, user_id: str) -> Optional[dict]:
        cid = await self._get_current_character_id(user_id)
        if cid:
            return await self._load_character_data(user_id, cid)
        return None

    # ================= 核心骰子逻辑 =================

    def _roll_single(self, faces: int) -> int:
        return random.randint(1, faces)

    def _roll_multi(self, count: int, faces: int) -> List[int]:
        max_dice = self.config.get("max_dice_count", 50)
        if count > max_dice:
            count = max_dice
        return [self._roll_single(faces) for _ in range(count)]

    def _roll_coc_bonus_penalty(self, base_roll, bonus_dice=0, penalty_dice=0):
        tens = base_roll // 10
        ones = base_roll % 10
        if ones == 0: ones = 10 
        extra_dice_count = max(bonus_dice, penalty_dice)
        if extra_dice_count == 0: return base_roll
        results = [base_roll]
        current_ones = (base_roll - 1) % 10 + 1 
        for _ in range(extra_dice_count):
            new_tens = random.randint(0, 9)
            new_val = new_tens * 10 + current_ones
            if new_val == 0: new_val = 100 
            results.append(new_val)
        if bonus_dice > 0: return min(results)
        else: return max(results)

    def _safe_parse_dice(self, expression: str) -> Tuple[Optional[int], str]:
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
                    if not match: return None, f"无法解析骰子部分: {part}"
                    count_str, faces_str, keep_str = match.groups()
                    count = int(count_str) if count_str else 1
                    faces = int(faces_str)
                    if count > self.config.get("max_dice_count", 50):
                        return None, f"骰子数量过多 (上限 {self.config.get('max_dice_count', 50)})"
                    rolls = self._roll_multi(count, faces)
                    if keep_str:
                        keep = int(keep_str)
                        selected = sorted(rolls, reverse=True)[:keep]
                        subtotal = sum(selected)
                        details.append(f"[{','.join(map(str, rolls))}选{keep}]")
                    else:
                        subtotal = sum(rolls)
                        details.append(f"[{'+'.join(map(str, rolls))}]")
                    total += subtotal * sign
                else:
                    if "*" in part:
                        factors = part.split("*")
                        sub_prod = 1
                        for f in factors: sub_prod *= int(f)
                        total += sub_prod * sign
                        details.append(str(sub_prod))
                    else:
                        val = int(part)
                        total += val * sign
                        details.append(str(val))
        except Exception as e: return None, f"计算错误: {str(e)}"
        expr_str = " + ".join(details).replace("+ -", "- ")
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
        if total == 1: result_str = "🎉 大成功"
        elif total <= target // 5: result_str = "✨ 极难成功"
        elif total <= target // 2: result_str = "✔ 困难成功"
        elif total <= target: result_str = "✅ 成功"
        elif total == 100: result_str = "💀 大失败"
        elif total >= 96 and target < 50: result_str = "💀 大失败"
        else: result_str = "❌ 失败"
        flavor = self._get_flavor_text(result_str)
        if flavor: return f"{result_str}\n> {flavor}"
        return result_str

    # ================= 指令处理 Handlers =================

    @filter.command("roll", alias={"r", "掷骰"})
    async def roll_dice(self, event: AstrMessageEvent, expression: str = None, target: int = None):
        """普通掷骰，支持 .r 1d100 50"""
        default_faces = self.config.get("default_dice_faces", 100)
        if expression is None: expression = f"1d{default_faces}"
        total, desc = self._safe_parse_dice(expression)
        if total is None:
            yield event.plain_result(f"⚠️ {desc}")
            return
        msg = f"🎲 掷骰: {expression}\n结果: {desc}"
        if target is not None:
            check_res = self._check_result(total, target)
            msg += f"\n判定 ({target}): {check_res}"
        yield event.plain_result(msg)

    @filter.command("rh", alias={"暗骰"})
    async def roll_hidden(self, event: AstrMessageEvent, expression: str = None):
        """私聊发送掷骰结果"""
        default_faces = self.config.get("default_dice_faces", 100)
        if expression is None: expression = f"1d{default_faces}"
        total, desc = self._safe_parse_dice(expression)
        if total is None:
             yield event.plain_result(f"⚠️ 暗骰格式错误: {desc}")
             return
        result_msg = f"🎲 暗骰结果: {expression} = {total}"
        user_id = event.get_sender_id()
        try:
            from astrbot.api.message_components import Plain
            await self.context.send_message(
                target=event.unified_msg_origin,
                message_chain=[Plain(result_msg)],
            )
            yield event.plain_result(f"🎲 {event.get_sender_name()} 进行了一次暗骰。")
            if event.get_platform_name() == "aiocqhttp":
                 await event.bot.api.call_action("send_private_msg", user_id=user_id, message=result_msg)
        except Exception as e:
            logger.error(f"Hidden roll failed: {e}")
            yield event.plain_result("⚠️ 暗骰发送失败，请确保你已添加机器人好友。")

    @filter.command_group("st")
    def st_group(self): pass

    @st_group.command("create")
    async def st_create(self, event: AstrMessageEvent, name: str, attributes: str):
        """创建人物卡: .st create 名字 力量50体质60..."""
        user_id = event.get_sender_id()
        chars = await self._get_all_characters(user_id)
        if name in chars:
            yield event.plain_result(f"⚠️ 人物卡 **{name}** 已存在！")
            return
        matches = re.findall(r"([\u4e00-\u9fa5a-zA-Z]+)(\d+)", attributes)
        if not matches:
             yield event.plain_result("⚠️ 未识别到属性数据，请使用格式：力量50敏捷60")
             return
        attr_dict = {k: int(v) for k, v in matches}
        if "hp" in attr_dict: attr_dict["max_hp"] = attr_dict["hp"]
        if "san" in attr_dict: attr_dict["max_san"] = attr_dict["san"]
        if "mp" in attr_dict: attr_dict["max_mp"] = attr_dict["mp"]
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
            yield event.plain_result("⚠️ 当前未选中人物卡，请先使用 `.st create` 或 `.st change`。")
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
        user_id = event.get_sender_id()
        data = await self._get_current_character(user_id)
        if not data:
            yield event.plain_result("⚠️ 未选中人物卡。")
            return
        attrs = data["attributes"]
        current_val = attrs.get(attr, 0)
        operator = None
        if value_expr.startswith(("+", "-", "*")):
            operator = value_expr[0]
            calc_part = value_expr[1:]
        else: calc_part = value_expr 
        change_val, change_desc = self._safe_parse_dice(calc_part)
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
        if operator: msg += f"{old_val} {operator} {change_desc} = **{new_val}**"
        else: msg += f"{old_val} → **{new_val}**"
        yield event.plain_result(msg)

    @filter.command("ra")
    async def roll_attr(self, event: AstrMessageEvent, skill: str, value: int = None):
        user_id = event.get_sender_id()
        if value is None:
            data = await self._get_current_character(user_id)
            if data: value = data["attributes"].get(skill)
        if value is None:
            yield event.plain_result(f"⚠️ 未找到技能 **{skill}** 的数值，请手动指定：`.ra {skill} 50`")
            return
        roll_res = random.randint(1, 100)
        check = self._check_result(roll_res, value)
        name_part = f"({data['name']})" if data else ""
        yield event.plain_result(f"🎲 **{skill}** {name_part}\n结果: {roll_res}/{value} \n{check}")

    @filter.command("sanc", alias={"san"}) 
    async def san_check(self, event: AstrMessageEvent, expr: str):
        user_id = event.get_sender_id()
        data = await self._get_current_character(user_id)
        if not data:
             yield event.plain_result("⚠️ 请先加载人物卡 (.st change)")
             return
        san = data["attributes"].get("san")
        if san is None:
             yield event.plain_result("⚠️ 当前人物卡没有 san 属性。")
             return
        if "/" not in expr:
            yield event.plain_result("⚠️ 格式错误，应为：成功扣除/失败扣除 (例: .sanc 1/1d6)")
            return
        success_expr, fail_expr = expr.split("/", 1)
        roll = random.randint(1, 100)
        is_success = roll <= san
        loss_expr = success_expr if is_success else fail_expr
        loss, loss_desc = self._safe_parse_dice(loss_expr)
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

    # ================= 帮助指令 (Updated) =================
    @filter.command("dicehelp")
    async def dice_help(self, event: AstrMessageEvent, ignore_arg: str = ""):
        """显示帮助菜单 (增加 ignore_arg，防止用户输入 /dicehelp xxxx 报错)"""
        # 数据修正：使用 "/" 前缀
        data = {
            "sections": [
                {
                    "title": "🎲 基础仪轨 (Basic)",
                    "commands": [
                        {"syntax": "/r [表达式]", "desc": "普通掷骰，例 /r 1d100"},
                        {"syntax": "/r [表达式] [值]", "desc": "掷骰并进行检定，例 /r 1d100 50"},
                        {"syntax": "/rh [表达式]", "desc": "暗骰，结果私聊发送"},
                    ]
                },
                {
                    "title": "📜 调查员档案 (Profile)",
                    "commands": [
                        {"syntax": "/st create [名] [属性]", "desc": "创建新人物卡"},
                        {"syntax": "/st show", "desc": "查看当前人物卡详情"},
                        {"syntax": "/st list", "desc": "列出所有已创建的人物卡"},
                        {"syntax": "/st change [名]", "desc": "切换当前使用的人物卡"},
                        {"syntax": "/st update [属性] [值]", "desc": "修改属性，支持公式"},
                    ]
                },
                {
                    "title": "🧠 理智与检定 (Check)",
                    "commands": [
                        {"syntax": "/ra [技能] [值]", "desc": "技能检定，自动读取当前卡"},
                        {"syntax": "/sanc [成功]/[失败]", "desc": "San Check，例 /sanc 1/1d3"},
                        {"syntax": "/ti / .li", "desc": "抽取 临时/总结 疯狂症状"},
                    ]
                }
            ]
        }
        # 使用 options={"full_page": True} 确保截取完整（虽然定宽 div 通常无需此项，但加了更保险）
        url = await self.html_render(HELP_HTML_TEMPLATE, data, options={"full_page": True})
        yield event.image_result(url)
