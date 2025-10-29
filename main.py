import random
import datetime
import hashlib
import ast

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *

# --- NEW IMPORTS START ---
# 为Markdown转图片功能引入必要的库
import json
import re
import os
import uuid
import asyncio
import tempfile

try:
    import pillowmd
except ImportError:
    pillowmd = None
# --- NEW IMPORTS END ---


# ======================== #

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER = PLUGIN_DIR + "/chara_data/"  # 存储人物卡的文件夹

DEFAULT_DICE = 100

# 恐惧
with open(PLUGIN_DIR + "/phobias.json", "r", encoding="utf-8") as f:
    phobias = json.load(f)["phobias"]

# 躁狂
with open(PLUGIN_DIR + "/mania.json", "r", encoding="utf-8") as f:
    manias = json.load(f)["manias"]
    
@register("astrbot_plugin_TRPG", "shiroling", "TRPG玩家用骰", "1.0.3")
class DicePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # --- NEW INIT LOGIC START ---
        if pillowmd is None:
            logger.error("pillowmd 库未安装，帮助菜单将无法转为图片。请执行: pip install pillowmd")
        # --- NEW INIT LOGIC END ---

    # --- NEW HELPER METHODS START ---
    async def _render_markdown_to_image(self, text: str):
        """使用 pillowmd 将 Markdown 文本渲染为图片"""
        if pillowmd is None:
            raise RuntimeError("pillowmd 库未安装，无法渲染图片。")
        
        # pillowmd.MdToImage 是一个异步函数，直接 await 即可
        img = await pillowmd.MdToImage(text)
        return img

    async def _save_temp_image(self, img_obj):
        """将 PIL 图像对象保存到临时文件，并返回路径"""
        loop = asyncio.get_running_loop()
        def save():
            # img_obj.image 是 pillowmd 返回结果中的 PIL.Image 对象
            pil_image = getattr(img_obj, "image", None)
            if pil_image is None:
                raise RuntimeError("渲染结果中未找到有效的图像对象。")

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_path = f.name
            pil_image.save(temp_path)
            return temp_path
        
        # 在线程池中执行同步的IO操作，避免阻塞事件循环
        path = await loop.run_in_executor(None, save)
        return path

    async def _delete_temp_file(self, path: str, delay: int = 10):
        """延迟删除临时文件"""
        await asyncio.sleep(delay)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.warning(f"删除临时文件 {path} 失败: {e}")
    # --- NEW HELPER METHODS END ---


    def _roll_dice(self, dice_count, dice_faces):
        """掷 `dice_count` 个 `dice_faces` 面骰"""
        return [random.randint(1, dice_faces) for _ in range(dice_count)]

    def _roll_coc_bonus_penalty(self, base_roll, bonus_dice=0, penalty_dice=0):
        """奖励骰 / 惩罚骰"""
        tens_digit = base_roll // 10
        ones_digit = base_roll % 10
        if ones_digit == 0:
            ones_digit = 10

        alternatives = []
        for _ in range(max(bonus_dice, penalty_dice)):
            new_tens = random.randint(0, 9)
            alternatives.append(new_tens * 10 + ones_digit)

        if bonus_dice > 0:
            return min([base_roll] + alternatives)
        elif penalty_dice > 0:
            return max([base_roll] + alternatives)
        return base_roll

    def _parse_dice_expression(self, expression):
        """解析骰子表达式，支持常数加减乘"""
        expression = str(expression) # 确保是字符串
        expression = expression.replace("x", "*").replace("X", "*")

        match_repeat = re.match(r"(\d+)?#(.+)", expression)
        roll_times = 1
        bonus_dice = 0
        penalty_dice = 0

        if match_repeat:
            roll_times = int(match_repeat.group(1)) if match_repeat.group(1) else 1
            expression = match_repeat.group(2)

            if expression == "p":
                penalty_dice = 1
                expression = "1d100"
            elif expression == "b":
                bonus_dice = 1
                expression = "1d100"

        results = []

        for _ in range(roll_times):
            parts = re.split(r"([+\-*])", expression)
            total = None 
            part_results = []
            calculation_expression = ""

            for i in range(0, len(parts), 2):
                expr = parts[i].strip()
                operator = parts[i - 1] if i > 0 else "+"

                if expr.isdigit():
                    subtotal = int(expr)
                    rolls = [subtotal]
                else:
                    match = re.match(r"(\d*)d(\d+)(k\d+)?([+\-*]\d+)?", expr)
                    if not match:
                        return None, f"格式错误 `{expr}`"

                    dice_count = int(match.group(1)) if match.group(1) else 1
                    dice_faces = int(match.group(2))
                    keep_highest = int(match.group(3)[1:]) if match.group(3) else dice_count
                    modifier = match.group(4)

                    if not (1 <= dice_count <= 100 and 1 <= dice_faces <= 1000):
                        return None, "骰子个数范围 1-100，面数范围 1-1000，否则非法！"

                    rolls = self._roll_dice(dice_count, dice_faces)
                    sorted_rolls = sorted(rolls, reverse=True)
                    selected_rolls = sorted_rolls[:keep_highest]

                    subtotal = sum(selected_rolls)

                    if modifier:
                        try:
                            subtotal = eval(f"{subtotal}{modifier}")
                        except:
                            return None, f"修正值 `{modifier}` 无效！"

                if total is None:
                    total = subtotal
                    calculation_expression = f"{subtotal}"
                else:
                    calculation_expression += f" {operator} {subtotal}"
                    if operator == "+":
                        total += subtotal
                    elif operator == "-":
                        total -= subtotal
                    elif operator == "*":
                        total *= subtotal
                if i == 0:
                    part_results.append(f"[{' + '.join(map(str, rolls))}]")
                else:
                    part_results.append(f" {operator} [{' + '.join(map(str, rolls))}]")

            if bonus_dice > 0 or penalty_dice > 0:
                base_roll = random.randint(1, 100)
                final_roll = self._roll_coc_bonus_penalty(base_roll, bonus_dice, penalty_dice)
                results.append(f"🎲 [**{final_roll}**] (原始: {base_roll})")
            else:
                results.append(f"🎲 {' '.join(part_results)} = {total}")

        return total, "\n".join(results)

    @filter.command("r")
    async def handle_roll_dice(self, event: AstrMessageEvent, dice_expression: str = None, target_value: int = None):
        """普通掷骰，支持添加判定值"""
        if dice_expression is None:
            dice_expression = f"1d{DEFAULT_DICE}"

        total, result_message = self._parse_dice_expression(dice_expression)

        if total is None:
            yield event.plain_result(result_message)
        else:
            if target_value is not None:
                success_level = self.get_roll_result(total, target_value)
                result_message += f" / {target_value} : {success_level}"

            yield event.plain_result(result_message)
            
    @filter.command("rh")
    async def roll_hidden(self, event: AstrMessageEvent, message : str = None):
        """私聊发送掷骰结果"""
        sender_id = event.get_sender_id()
        message = message.strip() if message else f"1d{DEFAULT_DICE}"

        total, result_message = self._parse_dice_expression(message)
        if total is None:
            private_msg = f"⚠️ {result_message}"
        else:
            private_msg = f"🎲 私骰结果: {result_message}"

        client = event.bot
        payloads = {
            "user_id": sender_id,
            "message": MessageChain().message(message=private_msg).chain
        }

        await client.api.call_action("send_private_msg", **payloads)

    def get_user_folder(self, user_id: str):
        """获取用户的存储文件夹"""
        folder = os.path.join(DATA_FOLDER, str(user_id))
        os.makedirs(folder, exist_ok=True)
        return folder

    def get_all_characters(self, user_id: str):
        """获取用户的所有人物卡"""
        folder = self.get_user_folder(user_id)
        characters = {}

        for filename in os.listdir(folder):
            if filename.endswith(".json"):
                path = os.path.join(folder, filename)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    characters[data["name"]] = data["id"]

        return characters

    def get_character_file(self, user_id: str, chara_id: str):
        """获取指定人物卡的文件路径"""
        return os.path.join(self.get_user_folder(user_id), f"{chara_id}.json")

    def get_current_character_file(self, user_id: str):
        """获取当前选中的人物卡的文件路径"""
        return os.path.join(self.get_user_folder(user_id), "current.txt")

    def get_current_character_id(self, user_id: str):
        """获取用户当前选中的人物卡 ID"""
        path = self.get_current_character_file(user_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return None
    
    def get_current_character(self, user_id: str):
        """获取当前选中人物卡的信息"""
        chara_id = self.get_current_character_id(user_id)
        if not chara_id:
            return None

        return self.load_character(user_id, chara_id)

    def set_current_character(self, user_id: str, chara_id: str):
        """设置用户当前选中的人物卡"""
        with open(self.get_current_character_file(user_id), "w", encoding="utf-8") as f:
            f.write(chara_id)

    def load_character(self, user_id: str, chara_id: str):
        """加载指定的角色数据"""
        path = self.get_character_file(user_id, chara_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def save_character(self, user_id: str, chara_id: str, data: dict):
        """保存人物卡"""
        path = self.get_character_file(user_id, chara_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
    def get_skill_value(self, user_id: str, skill_name: str):
        """获取当前选中角色的技能值"""
        chara_data = self.get_current_character(user_id)
        if not chara_data or skill_name not in chara_data["attributes"]:
            return 0
        return chara_data["attributes"][skill_name]

    @command_group("st")
    def st(self):
        pass

    @st.command("create")
    async def create_character(self, event: AstrMessageEvent, name: str, attributes: str):
        user_id = event.get_sender_id()
        characters = self.get_all_characters(user_id)

        if name in characters:
            yield event.plain_result(f"⚠️ 人物卡 **{name}** 已存在，无法重复创建！")
            return

        chara_id = str(uuid.uuid4())
        matches = re.findall(r"([\u4e00-\u9fa5a-zA-Z]+)(\d+)", attributes)
        chara_data = {"id": chara_id, "name": name, "attributes": {attr: int(value) for attr, value in matches}}
        chara_data['attributes']['max_hp'] = chara_data['attributes'].get('hp', 0)
        chara_data['attributes']['max_san'] = chara_data['attributes'].get('san', 0)

        self.save_character(user_id, chara_id, chara_data)
        self.set_current_character(user_id, chara_id)
        yield event.plain_result(f"✅ 人物卡 **{name}** 已成功创建！(ID: {chara_id})\n🔄 已自动切换到 **{name}**！")

    @st.command("show")
    async def show_character(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        chara_id = self.get_current_character_id(user_id)

        if not chara_id:
            yield event.plain_result("⚠️ 你当前没有选中的人物卡，请使用 `.st change 角色名称` 切换！")
            return

        chara_data = self.load_character(user_id, chara_id)
        if not chara_data:
            yield event.plain_result(f"⚠️ 人物卡 (ID: {chara_id}) 不存在！")
            return

        attributes = "\n".join([f"{key}: {value}" for key, value in chara_data["attributes"].items()])
        yield event.plain_result(f"📜 当前人物卡: **{chara_data['name']}**\n{attributes}")

    @st.command("list")
    async def list_characters(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        characters = self.get_all_characters(user_id)

        if not characters:
            yield event.plain_result("⚠️ 你没有创建任何人物卡！请使用 `.st create` 创建。")
            return

        current = self.get_current_character_id(user_id)
        chara_list = "\n".join([f"- {name} (ID: {ch}) {'(当前)' if ch == current else ''}" for name, ch in characters.items()])
        yield event.plain_result(f"📜 你的所有人物卡:\n{chara_list}")

    @st.command("change")
    async def change_character(self, event: AstrMessageEvent, name: str):
        user_id = event.get_sender_id()
        characters = self.get_all_characters(user_id)

        if name not in characters:
            yield event.plain_result(f"⚠️ 人物卡 **{name}** 不存在！")
            return

        self.set_current_character(user_id, characters[name])
        yield event.plain_result(f"✅ 你已切换到人物卡 **{name}**！")

    @st.command("update")
    async def update_character(self, event: AstrMessageEvent, attribute: str, value: str):
        user_id = event.get_sender_id()
        chara_id = self.get_current_character_id(user_id)

        if not chara_id:
            yield event.plain_result("⚠️ 你当前没有选中的人物卡！")
            return

        chara_data = self.load_character(user_id, chara_id)
        if attribute not in chara_data["attributes"]:
            yield event.plain_result(f"⚠️ 属性 `{attribute}` 不存在！")
            return

        current_value = chara_data["attributes"][attribute]
        match = re.match(r"([+\-*]?)(\d*)d?(\d*)", value)
        if not match:
            yield event.plain_result(f"⚠️ `{value}` 格式错误！")
            return

        operator = match.group(1)
        dice_count = int(match.group(2)) if match.group(2) else 1
        dice_faces = int(match.group(3)) if match.group(3) else 0

        if dice_faces > 0:
            rolls = [random.randint(1, dice_faces) for _ in range(dice_count)]
            value_num = sum(rolls)
            roll_detail = f"🎲 掷骰结果: [{' + '.join(map(str, rolls))}] = {value_num}"
        else:
            value_num = int(match.group(2)) if match.group(2) else 0
            roll_detail = ""

        if operator == "+": new_value = current_value + value_num
        elif operator == "-": new_value = current_value - value_num
        elif operator == "*": new_value = current_value * value_num
        else: new_value = value_num

        chara_data["attributes"][attribute] = max(0, new_value)
        self.save_character(user_id, chara_id, chara_data)
        response = f"✅ `{attribute}` 变更: {current_value} → {new_value}"
        if roll_detail:
            response += f"\n{roll_detail}"
        yield event.plain_result(response)

    @st.command("delete")
    async def delete_character(self, event: AstrMessageEvent, name: str):
        user_id = event.get_sender_id()
        characters = self.get_all_characters(user_id)

        if name not in characters:
            yield event.plain_result(f"⚠️ 人物卡 **{name}** 不存在！")
            return

        path = self.get_character_file(user_id, characters[name])
        os.remove(path)
        yield event.plain_result(f"🗑️ 人物卡 **{name}** 已删除！")
        
    @filter.command("sn")
    async def set_nickname(self, event: AstrMessageEvent):
        if event.get_platform_name() == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            assert isinstance(event, AiocqhttpMessageEvent)

            client = event.bot
            user_id = event.get_sender_id()
            group_id = event.get_group_id()

            chara_data = self.get_current_character(user_id)
            if not chara_data:
                yield event.plain_result(f"⚠️ 你当前没有人物卡！")
                return

            name = chara_data.get('name', '未知')
            hp = chara_data['attributes'].get('hp', 0)
            max_hp = chara_data['attributes'].get('max_hp', 0)
            san = chara_data['attributes'].get('san', 0)
            max_san = chara_data['attributes'].get('max_san', 0)
            new_card = f"{name} HP:{hp}/{max_hp} SAN:{san}/{max_san}"

            payloads = {"group_id": group_id, "user_id": user_id, "card": new_card}
            await client.api.call_action("set_group_card", **payloads)
            yield event.plain_result(f"已修改群名片！")
    
    @filter.command("ra")
    async def roll_attribute(self, event: AstrMessageEvent, skill_name: str, skill_value: str = None):
        user_id = event.get_sender_id()
        if skill_value is None:
            skill_value = self.get_skill_value(user_id, skill_name)

        try: skill_value = int(skill_value)
        except ValueError:
            yield event.plain_result("技能点数必须是整数！")
            return

        roll_result = random.randint(1, 100)
        result = self.get_roll_result(roll_result, skill_value)
        yield event.plain_result(f"🎲【{skill_name}】的投掷结果 {roll_result}/{skill_value} : {result}")

    @filter.command("rap")
    async def roll_attribute_penalty(self, event: AstrMessageEvent, dice_count: str = "1", skill_name: str = "", skill_value: str = None):
        user_id = event.get_sender_id()
        if skill_value is None:
            skill_value = self.get_skill_value(user_id, skill_name)
        try:
            dice_count = int(dice_count)
            skill_value = int(skill_value)
        except ValueError:
            yield event.plain_result("骰子个数和技能点数必须是整数！")
            return

        ones_digit = random.randint(1, 10)
        tens_digits = [random.randint(0, 9) for _ in range(dice_count + 1)]
        
        rolls = [d * 10 + ones_digit if d != 0 or ones_digit != 10 else 100 for d in tens_digits]
        final_roll = max(rolls)
        
        result = self.get_roll_result(final_roll, skill_value)
        yield event.plain_result(f"🎲【{skill_name}】惩罚骰: {rolls} → 最终 {final_roll}/{skill_value} : {result}")

    @filter.command("rab")
    async def roll_attribute_bonus(self, event: AstrMessageEvent, dice_count: str = "1", skill_name: str = "", skill_value: str = None):
        user_id = event.get_sender_id()
        if skill_value is None:
            skill_value = self.get_skill_value(user_id, skill_name)
        try:
            dice_count = int(dice_count)
            skill_value = int(skill_value)
        except ValueError:
            yield event.plain_result("骰子个数和技能点数必须是整数！")
            return
            
        ones_digit = random.randint(1, 10)
        tens_digits = [random.randint(0, 9) for _ in range(dice_count + 1)]
        
        rolls = [d * 10 + ones_digit if d != 0 or ones_digit != 10 else 100 for d in tens_digits]
        final_roll = min(rolls)

        result = self.get_roll_result(final_roll, skill_value)
        yield event.plain_result(f"🎲【{skill_name}】奖励骰: {rolls} → 最终 {final_roll}/{skill_value} : {result}")

    def get_roll_result(self, roll_result: int, skill_value: int):
        FLAVOR_TEXTS = {
            "🎉 大成功": "干涸的石头裂开一道缝隙，在那一瞬间，你听见了水的声响。",
            "✨ 极难成功": "你在这堆石头瓦砾下，找到了一把尚未完全锈蚀的钥匙。",
            "✔ 困难成功": "走廊尽头的门应声而开，露出的不过是另一段一模一样的走廊。",
            "✅ 成功": "走廊尽头的门应声而开，露出的不过是另一段一模一样的走廊。",
            "❌ 失败": "你的影子落在墙上，如同用粉笔画的，一动不动。",
            "💀 大失败": "你听见了一声干涩的、像是老鼠在碎玻璃上跑过的笑声，但房间里空无一人。"
        }
        
        result_string = ""
        if roll_result <= 1 or (roll_result <= 5 and skill_value >= 50):
             result_string = "🎉 大成功"
        elif roll_result >= 100 or (roll_result >= 96 and skill_value < 50):
             result_string = "💀 大失败"
        elif roll_result <= skill_value / 5:
            result_string = "✨ 极难成功"
        elif roll_result <= skill_value / 2:
            result_string = "✔ 困难成功"
        elif roll_result <= skill_value:
            result_string = "✅ 成功"
        else:
            result_string = "❌ 失败"
            
        flavor_text = FLAVOR_TEXTS.get(result_string, "")
        return f"{result_string}\n{flavor_text}"
        
    @filter.command("sc")
    async def san_check(self, event: AstrMessageEvent, loss_formula: str):
        user_id = event.get_sender_id()
        chara_data = self.get_current_character(user_id)
        if not chara_data:
            yield event.plain_result("⚠️ 你当前没有选中的人物卡！")
            return

        san_value = chara_data["attributes"].get("san", 0)
        roll_result = random.randint(1, 100)
        success_loss, failure_loss = self.parse_san_loss_formula(loss_formula)

        if roll_result <= san_value:
            loss = self.roll_loss(success_loss)
            result_msg = "✅ 成功"
        else:
            loss = self.roll_loss(failure_loss)
            result_msg = "❌ 失败"

        new_san = max(0, san_value - loss)
        chara_data["attributes"]["san"] = new_san
        self.save_character(user_id, chara_data["id"], chara_data)
        yield event.plain_result(f"🧠 SAN 检定 {roll_result}/{san_value} : {result_msg}\n💀 SAN 值减少 **{loss}**，当前 SAN: {new_san}")

    def parse_san_loss_formula(self, formula: str):
        parts = formula.split("/")
        return parts[0], parts[1] if len(parts) > 1 else parts[0]

    def roll_loss(self, loss_expr: str):
        if 'd' in loss_expr:
            num, face = map(int, loss_expr.split('d'))
            return sum(random.randint(1, face) for _ in range(num))
        return int(loss_expr)
    
    @filter.command("ti")
    async def temporary_insanity_command(self, event: AstrMessageEvent):
        temporary_insanity = {1: "失忆1D10轮", 2: "假性残疾1D10轮", 3: "暴力倾向1D10轮", 4: "偏执1D10轮", 5: "人际依赖1D10轮", 6: "昏厥1D10轮", 7: "逃避1D10轮", 8: "歇斯底里1D10轮", 9: "恐惧症1D10轮", 10: "躁狂症1D10轮"}
        roll = random.randint(1, 10)
        duration = random.randint(1, 10)
        result = temporary_insanity[roll].replace("1D10", str(duration))
        if roll == 9: result += f"\n→ 具体恐惧症：{phobias[str(random.randint(1, 100))]}"
        if roll == 10: result += f"\n→ 具体躁狂症：{manias[str(random.randint(1, 100))]}"
        yield event.plain_result(f"🎲 **疯狂发作 - 临时症状（1D10={roll}）**\n{result}")

    @filter.command("li")
    async def long_term_insanity_command(self, event: AstrMessageEvent):
        long_term_insanity = {1: "失忆", 2: "被窃", 3: "遍体鳞伤", 4: "暴力倾向", 5: "极端信念", 6: "重要之人", 7: "被收容", 8: "逃避行为", 9: "新恐惧症", 10: "新躁狂症"}
        roll = random.randint(1, 10)
        result = long_term_insanity[roll]
        if roll == 9: result += f"\n→ 具体恐惧症：{phobias[str(random.randint(1, 100))]}"
        if roll == 10: result += f"\n→ 具体躁狂症：{manias[str(random.randint(1, 100))]}"
        yield event.plain_result(f"🎲 **疯狂发作 - 总结症状（1D10={roll}）**\n{result}")
    
    def get_db_build(self, str_val, siz_val):
        total = str_val + siz_val
        if total <= 64: return "-2D6", -2
        if total <= 84: return "-1D6", -1
        if total <= 124: return "+0", 0
        if total <= 164: return "+1D4", 1
        if total <= 204: return "+1D6", 2
        return "+2D6", 3

    def roll_character(self):
        attrs = {
            "STR": sum(random.randint(1, 6) for _ in range(3)) * 5,
            "CON": sum(random.randint(1, 6) for _ in range(3)) * 5,
            "SIZ": (sum(random.randint(1, 6) for _ in range(2)) + 6) * 5,
            "DEX": sum(random.randint(1, 6) for _ in range(3)) * 5,
            "APP": sum(random.randint(1, 6) for _ in range(3)) * 5,
            "INT": (sum(random.randint(1, 6) for _ in range(2)) + 6) * 5,
            "POW": sum(random.randint(1, 6) for _ in range(3)) * 5,
            "EDU": (sum(random.randint(1, 6) for _ in range(2)) + 6) * 5,
            "LUCK": sum(random.randint(1, 6) for _ in range(3)) * 5,
        }
        attrs["HP"] = (attrs["SIZ"] + attrs["CON"]) // 10
        attrs["MP"] = attrs["POW"] // 5
        attrs["SAN"] = attrs["POW"]
        attrs["DB"], attrs["BUILD"] = self.get_db_build(attrs["STR"], attrs["SIZ"])
        attrs["TOTAL"] = sum(v for k, v in attrs.items() if k in ["STR", "CON", "SIZ", "DEX", "APP", "INT", "POW", "EDU"])
        return attrs

    def format_character(self, data, index=1):
        return (f"第 {index} 号调查员\n"
                f"力量: {data['STR']}  体质: {data['CON']}  体型: {data['SIZ']}\n"
                f"敏捷: {data['DEX']}  外貌: {data['APP']}  智力: {data['INT']}\n"
                f"意志: {data['POW']}  教育: {data['EDU']}\n"
                f"生命: {data['HP']}  魔力: {data['MP']}  理智: {data['SAN']}  幸运: {data['LUCK']}\n"
                f"DB: {data['DB']}  总和 : {data['TOTAL']} / {data['TOTAL'] + data['LUCK']}")
    
    def roll_4d6_drop_lowest(self):
        rolls = sorted([random.randint(1, 6) for _ in range(4)])
        return sum(rolls[1:])

    def roll_dnd_character(self):
        return [self.roll_4d6_drop_lowest() for _ in range(6)]

    def format_dnd_character(self, data, index=1):
        data = sorted(data, reverse=True)
        return (f"第 {index} 位冒险者\n"
                f"[{', '.join(map(str, data))}] → 共计 {sum(data)}")
    
    @filter.command("coc")
    async def generate_coc_character(self, event: AstrMessageEvent, x: int = 1):
        characters = [self.roll_character() for _ in range(x)]
        result = "\n\n".join(self.format_character(c, i + 1) for i, c in enumerate(characters))
        yield event.plain_result(result)
        
    @filter.command("dnd")
    async def generate_dnd_character(self, event: AstrMessageEvent, x: int = 1):
        characters = [self.roll_dnd_character() for _ in range(x)]
        result = "\n\n".join(self.format_dnd_character(c, i + 1) for i, c in enumerate(characters))
        yield event.plain_result(result)
        
    # --- MODIFIED HELP COMMAND START ---
    @filter.command("dicehelp")
    async def help ( self , event: AstrMessageEvent):
        help_text = (
"""---

🎲 RosaのTRPG 骰子帮助菜单 🎲
——关于这场掷骨游戏的备忘录

“我们走吧，你和我，当黄昏铺满天空，像一个上了乙醚的病人躺在手术台上。或许你觉得这些指令是通往胜利的阶梯？不，它们只是在寂静中，为意志的瘫痪所做的、一次又一次的徒劳占卜。”

---
**第一章：搅动虚空 (基础掷骰)**

`/r 1d100` - 掷 1 个 100 面骰
> “从虚空中撬落一块碎片。”

`/r 1d100 75` - 投掷1d100，并对75进行成功判定
> “将那碎片与你可怜的意志相衡量。”

`/r 3d6+2d4-1d8` - 掷 3 个 6 面骰 + 2 个 4 面骰 - 1 个 8 面骰
> “将不同的命运残片缝合、撕裂。”

`/r 3#1d20` - 掷 1d20 骰 3 次
> “向同一个深渊，徒劳地叩问三次。”

---
**第二章：标本编目 (人物卡管理)**

`/st create 名称 属性值` - 创建人物卡
> “为一只新的空心人钉上标签。”

`/st show` - 显示当前人物卡
> “审视当前这具皮囊的解剖图。”

`/st list` - 列出所有人物卡
> “清点陈列室里的所有标本。”

`/st change 名称` - 切换当前人物卡
> “换上另一件戏服。”

`/st update 属性 值/公式` - 更新人物卡属性
> “在标签上划掉旧词，添上新的病症。”

`/st delete 名称` - 删除人物卡
> “将一份失败的草稿投入壁炉。”

---
**第三章：精神的荒原 (CoC 相关)**

`/coc x` - 生成 x 个 CoC 角色数据
> “催生几具可供观察的、意志瘫痪的躯壳。”

`/ra 技能名` - 进行技能骰
> “检阅一项技艺的成色。”

`/rap n 技能名` - 带 n 个惩罚骰的技能骰
> “为天平的一端，添上几颗惩戒的石子。”

`/rab n 技能名` - 带 n 个奖励骰的技能骰
> “从天平的另一端，取走几粒恩赐的尘埃。”

`/sc 1d6/1d10` - 进行 San Check
> “直视深渊，并记录下瞳孔的震颤。”

`/ti` - 生成临时疯狂症状
> “记录一次短暂的精神痉挛。”

`/li` - 生成长期疯狂症状
> “为一处无法愈合的内伤，撰写病历。”

---
**第四章：庸俗的奇观 (DnD 相关)**

`/dnd x` - 生成 x 个 DnD 角色属性
> “拼凑几个适合上演英雄闹剧的演员。”

`/fireball n` - 施放 n 环火球术，计算伤害
> “在这片灰烬中，点燃一朵短暂的、橙色的花。”

---"""
        )
        try:
            # 渲染、保存、发送、清理
            img_obj = await self._render_markdown_to_image(help_text)
            image_path = await self._save_temp_image(img_obj)
            yield event.image_result(image_path)
            # 创建一个后台任务来延迟删除文件
            asyncio.create_task(self._delete_temp_file(image_path))
        except Exception as e:
            logger.error(f"帮助菜单转图片失败，将发送纯文本: {e}")
            yield event.plain_result(help_text)
    # --- MODIFIED HELP COMMAND END ---
        
    @filter.command("fireball")
    async def fireball(self, event: AstrMessageEvent, ring : int = 3):
        """投掷 n 环火球术伤害"""
        if ring < 3 :
            yield event.plain_result("请不要试图使用降环火球术！")
            return
        
        dice_count = 8 + (ring - 3)
        rolls = [random.randint(1, 6) for _ in range(dice_count)]
        total_sum = sum(rolls)

        damage_breakdown = " + ".join(map(str, rolls))
        result_message = (
            f"明亮的闪光从你的指间飞驰向施法距离内你指定的一点，并随着一声低吼迸成一片烈焰。\n"
            f"{ring} 环火球术的伤害投掷: {damage_breakdown} = 🔥{total_sum}🔥 点伤害！\n"
        )

        yield event.plain_result(result_message)