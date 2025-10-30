import random
import datetime
import hashlib
import ast

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *

# ======================== #
import json
import re
import os
import uuid

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
        # 如果没有提供任何投骰表达式，则使用默认值
        if dice_expression is None:
            dice_expression = f"1d{DEFAULT_DICE}"

        # 核心逻辑：解析投骰表达式
        total, result_message = self._parse_dice_expression(dice_expression)

        if total is None:
            yield event.plain_result(result_message)
        else:
            # 检查框架是否成功解析出了判定值
            if target_value is not None:
                # 调用判定函数
                success_level = self.get_roll_result(total, target_value)
                # 将判定结果追加到消息中
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

        client = event.bot  # 获取机器人 Client
        payloads = {
            "user_id": sender_id,
            "message": [
                {
                    "type": "text",
                    "data": {
                        "text": private_msg
                    }
                }
            ]
        }

        ret = await client.api.call_action("send_private_msg", **payloads)
        # logger.info(f"send_private_msg: {ret}")


    # ============================================================== #
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
            return 0  # 没有选中角色或技能不存在
        return chara_data["attributes"][skill_name]


    @command_group("st")
    def st(self):
        pass

    @st.command("create")
    async def create_character(self, event: AstrMessageEvent, name: str, attributes: str):
        """创建人物卡"""
        user_id = event.get_sender_id()
        characters = self.get_all_characters(user_id)

        if name in characters:
            yield event.plain_result(f"⚠️ 人物卡 **{name}** 已存在，无法重复创建！")
            return

        chara_id = str(uuid.uuid4())  # 生成唯一 ID

        matches = re.findall(r"([\u4e00-\u9fa5a-zA-Z]+)(\d+)", attributes)
        chara_data = {"id": chara_id, "name": name, "attributes": {attr: int(value) for attr, value in matches}}
        chara_data['attributes']['max_hp'] = chara_data['attributes'].get('hp', 0)
        chara_data['attributes']['max_san'] = chara_data['attributes'].get('san', 0)

        self.save_character(user_id, chara_id, chara_data)

        self.set_current_character(user_id, chara_id)

        yield event.plain_result(f"✅ 人物卡 **{name}** 已成功创建！(ID: {chara_id})\n🔄 已自动切换到 **{name}**！")

    @st.command("show")
    async def show_character(self, event: AstrMessageEvent):
        """显示当前选中的人物卡"""
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
        """列出所有人物卡"""
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
        """切换当前使用的人物卡"""
        user_id = event.get_sender_id()
        characters = self.get_all_characters(user_id)

        if name not in characters:
            yield event.plain_result(f"⚠️ 人物卡 **{name}** 不存在！")
            return

        self.set_current_character(user_id, characters[name])
        yield event.plain_result(f"✅ 你已切换到人物卡 **{name}**！")

    @st.command("update")
    async def update_character(self, event: AstrMessageEvent, attribute: str, value: str):
        """更新当前选中的人物卡，支持公式和掷骰计算"""
        user_id = event.get_sender_id()
        chara_id = self.get_current_character_id(user_id)

        if not chara_id:
            yield event.plain_result("⚠️ 你当前没有选中的人物卡，请使用 `.st change 角色名称` 先切换！")
            return

        chara_data = self.load_character(user_id, chara_id)

        if attribute not in chara_data["attributes"]:
            yield event.plain_result(f"⚠️ 属性 `{attribute}` 不存在！请检查拼写。")
            return

        current_value = chara_data["attributes"][attribute]

        match = re.match(r"([+\-*]?)(\d*)d?(\d*)", value)
        if not match:
            yield event.plain_result(f"⚠️ `{value}` 格式错误！请使用 `.st 属性+数值` 或 `.st 属性-1d6`")
            return

        operator = match.group(1)  # `+` / `-` / `*`
        dice_count = int(match.group(2)) if match.group(2) else 1
        dice_faces = int(match.group(3)) if match.group(3) else 0

        if dice_faces > 0:
            rolls = [random.randint(1, dice_faces) for _ in range(dice_count)]
            value_num = sum(rolls)
            roll_detail = f"🎲 掷骰结果: [{' + '.join(map(str, rolls))}] = {value_num}"
        else:
            value_num = int(match.group(2)) if match.group(2) else 0
            roll_detail = ""

        if operator == "+":
            new_value = current_value + value_num
        elif operator == "-":
            new_value = current_value - value_num
        elif operator == "*":
            new_value = current_value * value_num
        else:
            new_value = value_num

        chara_data["attributes"][attribute] = max(0, new_value)
        self.save_character(user_id, chara_id, chara_data)

        response = f"✅ `{attribute}` 变更: {current_value} → {new_value}"
        if roll_detail:
            response += f"\n{roll_detail}"
        yield event.plain_result(response)

    @st.command("delete")
    async def delete_character(self, event: AstrMessageEvent, name: str):
        """删除指定人物卡"""
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
        """修改群成员名片"""
        if event.get_platform_name() == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            assert isinstance(event, AiocqhttpMessageEvent)

            client = event.bot
            user_id = event.get_sender_id()
            group_id = event.get_group_id()

            chara_id = self.get_current_character_id(user_id)
            chara_data = self.load_character(user_id, chara_id)
            
            if not chara_data:
                yield event.plain_result(f"⚠️ 人物卡 (ID: {chara_id}) 不存在！")
                return

            name, hp, max_hp, san, max_san = chara_data['name'], chara_data['attributes'].get('hp', 0), chara_data['attributes'].get('max_hp', 0), chara_data['attributes'].get('san', 0), chara_data['attributes'].get('max_san', 0)
            new_card = f"{name} HP:{hp}/{max_hp} SAN:{san}/{max_san}"

            payloads = {
                "group_id": group_id,
                "user_id": user_id,
                "card": new_card
            }

            ret = await client.api.call_action("set_group_card", **payloads)
            yield event.plain_result(f"已修改人物名！")
            # logger.info(f"set_group_card: {ret}")
    
    # ========================================================= #
    @filter.command("ra")
    async def roll_attribute(self, event: AstrMessageEvent, skill_name: str, skill_value: str = None):
        """.ra 技能名 [x]"""
        user_id = event.get_sender_id()

        if skill_value is None:
            skill_value = self.get_skill_value(user_id, skill_name)

        try:
            skill_value = int(skill_value)
        except ValueError:
            yield event.plain_result("技能点数必须是整数！")
            return

        tens_digit = random.randint(0, 9)  # 0-9
        ones_digit = random.randint(0, 9)  # 0-9
        roll_result = 100 if (tens_digit == 0 and ones_digit == 0) else (tens_digit * 10 + ones_digit)

        result = self.get_roll_result(roll_result, skill_value)
        yield event.plain_result(f"🎲【{skill_name}】的投掷结果 {roll_result}/{skill_value} : {result}")

    @filter.command("rap")
    async def roll_attribute_penalty(self, event: AstrMessageEvent, dice_count: str = "1", skill_name: str = "", skill_value: str = None):
        """带技能点惩罚骰"""
        user_id = event.get_sender_id()

        if skill_value is None:
            skill_value = self.get_skill_value(user_id, skill_name)

        try:
            dice_count = int(dice_count)
            skill_value = int(skill_value)
        except ValueError:
            yield event.plain_result("骰子个数和技能点数必须是整数！")
            return

        ones_digit = random.randint(0, 9)
        new_tens_digits = [random.randint(0, 9) for _ in range(dice_count)]
        new_tens_digits.append(random.randint(0, 9))

        if 0 in new_tens_digits and ones_digit == 0:
            final_y = 100
        else:
            final_tens = max(new_tens_digits)
            final_y = final_tens * 10 + ones_digit

        result = self.get_roll_result(final_y, skill_value)
        yield event.plain_result(
            f"🎲【{skill_name}】的投掷结果 → 惩罚骰结果 {new_tens_digits} → 最终 {final_y}/{skill_value} : {result}"
        )

    @filter.command("rab")
    async def roll_attribute_bonus(self, event: AstrMessageEvent, dice_count: str = "1", skill_name: str = "", skill_value: str = None):
        """带技能点奖励骰"""
        user_id = event.get_sender_id()

        if skill_value is None:
            skill_value = self.get_skill_value(user_id, skill_name)

        try:
            dice_count = int(dice_count)
            skill_value = int(skill_value)
        except ValueError:
            yield event.plain_result("骰子个数和技能点数必须是整数！")
            return

        ones_digit = random.randint(0, 9)
        new_tens_digits = [random.randint(0, 9) for _ in range(dice_count)]
        new_tens_digits.append(random.randint(0, 9))

        filtered_tens = [tens for tens in new_tens_digits if not (tens == 0 and ones_digit == 0)]
        if not filtered_tens:
            final_tens = 0
        else:
            final_tens = min(filtered_tens)

        final_y = final_tens * 10 + ones_digit

        result = self.get_roll_result(final_y, skill_value)
        yield event.plain_result(
            f"🎲【{skill_name}】的投掷结果 → 奖励骰结果 {new_tens_digits} → 最终 {final_y}/{skill_value} : {result}"
        )

    def get_roll_result(self, roll_result: int, skill_value: int):
        """根据掷骰结果和技能值计算判定，并附上氛围评语"""
        FLAVOR_TEXTS = {
            "🎉 大成功": "干涸的石头裂开一道缝隙，在那一瞬间，你听见了水的声响。",
            "✨ 极难成功": "你在这堆石头瓦砾下，找到了一把尚未完全锈蚀的钥匙。",
            "✔ 困难成功": "走廊尽头的门应声而开，露出的不过是另一段一模一样的走廊。",
            "✅ 成功": "走廊尽头的门应声而开，露出的不过是另一段一模一样的走廊。",
            "❌ 失败": "你的影子落在墙上，如同用粉笔画的，一动不动。",
            "💀 大失败": "你听见了一声干涩的、像是老鼠在碎玻璃上跑过的笑声，但房间里空无一人。"
        }
        
        result_string = ""
        if skill_value > 50 and roll_result < 5:
            result_string = "🎉 大成功"
        elif 5 < skill_value < 50 and roll_result == 1:
            result_string = "🎉 大成功"
        elif roll_result <= skill_value / 5:
            result_string = "✨ 极难成功"
        elif roll_result <= skill_value / 2:
            result_string = "✔ 困难成功"
        elif roll_result <= skill_value:
            result_string = "✅ 成功"
        elif (skill_value <= 50 and roll_result >= 96) or (skill_value > 50 and roll_result == 100):
            result_string = "💀 大失败"
        else:
            result_string = "❌ 失败"
            
        flavor_text = FLAVOR_TEXTS.get(result_string, "")
        
        # 返回时，在判定结果和评语之间加上换行符
        return f"{result_string}\n{flavor_text}"
        
    # ========================================================= #
    # san check
    @filter.command("sc")
    async def san_check(self, event: AstrMessageEvent, loss_formula: str):
        user_id = event.get_sender_id()
        chara_data = self.get_current_character(user_id)

        if not chara_data:
            yield event.plain_result("⚠️ 你当前没有选中的人物卡，请使用 `.st change 角色名称` 先切换！")
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

        yield event.plain_result(
            f"🧠 SAN 检定 {roll_result}/{san_value} : {result_msg}\n"
            f"💀 SAN 值减少 **{loss}**，当前 SAN: {new_san}"
        )

    def parse_san_loss_formula(self, formula: str):
        """解析 SAN 损失公式"""
        parts = formula.split("/")
        success_part = parts[0]
        failure_part = parts[1] if len(parts) > 1 else parts[0]

        return success_part, failure_part

    def roll_loss(self, loss_expr: str):
        """计算损失值"""
        match = re.fullmatch(r"(\d+)d(\d+)", loss_expr)
        if match:
            num_dice, dice_size = map(int, match.groups())
            return sum(random.randint(1, dice_size) for _ in range(num_dice))
        elif loss_expr.isdigit():
            return int(loss_expr)
        return 0
    
    # ========================================================= #
    # 疯狂
    
    @filter.command("ti")
    async def temporary_insanity_command(self, event: AstrMessageEvent):
        """随机生成临时疯狂症状"""
        temporary_insanity = {
        1: "失忆：调查员只记得最后身处的安全地点，却没有任何来到这里的记忆。这将会持续 1D10 轮。",
        2: "假性残疾：调查员陷入心理性的失明、失聪或躯体缺失感，持续 1D10 轮。",
        3: "暴力倾向：调查员对周围所有人（敌人和同伴）展开攻击，持续 1D10 轮。",
        4: "偏执：调查员陷入严重的偏执妄想（所有人都想伤害他），持续 1D10 轮。",
        5: "人际依赖：调查员误认为某人是他的重要之人，并据此行动，持续 1D10 轮。",
        6: "昏厥：调查员当场昏倒，1D10 轮后苏醒。",
        7: "逃避行为：调查员试图用任何方式逃离当前场所，持续 1D10 轮。",
        8: "歇斯底里：调查员陷入极端情绪（大笑、哭泣、尖叫等），持续 1D10 轮。",
        9: "恐惧：骰 1D100 或由守秘人选择一个恐惧症，调查员会想象它存在，持续 1D10 轮。",
        10: "躁狂：骰 1D100 或由守秘人选择一个躁狂症，调查员会沉溺其中，持续 1D10 轮。"
        }
        roll = random.randint(1, 10)
        result = temporary_insanity[roll].replace("1D10", str(random.randint(1, 10)))

        if roll == 9:
            fear_roll = random.randint(1, 100)
            result += f"\n→ 具体恐惧症：{phobias[str(fear_roll)]}（骰值 {fear_roll}）"

        if roll == 10:
            mania_roll = random.randint(1, 100)
            result += f"\n→ 具体躁狂症：{manias[str(mania_roll)]}（骰值 {mania_roll}）"

        yield event.plain_result(f"🎲 **疯狂发作 - 临时症状（1D10={roll}）**\n{result}")

    @filter.command("li")
    async def long_term_insanity_command(self, event: AstrMessageEvent):
        long_term_insanity = {
        1: "失忆：调查员发现自己身处陌生地方，并忘记自己是谁。记忆会缓慢恢复。",
        2: "被窃：调查员 1D10 小时后清醒，发现自己身上贵重物品丢失。",
        3: "遍体鳞伤：调查员 1D10 小时后清醒，身体有严重伤痕（生命值剩一半）。",
        4: "暴力倾向：调查员可能在疯狂期间杀人或造成重大破坏。",
        5: "极端信念：调查员疯狂地执行某个信仰（如宗教狂热、政治极端），并采取极端行动。",
        6: "重要之人：调查员疯狂追求某个他在意的人，不顾一切地接近该人。",
        7: "被收容：调查员在精神病院或警察局醒来，完全不记得发生了什么。",
        8: "逃避行为：调查员在远离原地点的地方醒来，可能在荒郊野外或陌生城市。",
        9: "恐惧：调查员患上一种新的恐惧症（骰 1D100 或由守秘人选择）。",
        10: "躁狂：调查员患上一种新的躁狂症（骰 1D100 或由守秘人选择）。"
        }
        """随机生成长期疯狂症状"""
        roll = random.randint(1, 10)
        result = long_term_insanity[roll].replace("1D10", str(random.randint(1, 10)))

        if roll == 9:
            fear_roll = random.randint(1, 100)
            result += f"\n→ 具体恐惧症：{phobias[str(fear_roll)]}（骰值 {fear_roll}）"

        if roll == 10:
            mania_roll = random.randint(1, 100)
            result += f"\n→ 具体躁狂症：{manias[str(mania_roll)]}（骰值 {mania_roll}）"

        yield event.plain_result(f"🎲 **疯狂发作 - 总结症状（1D10={roll}）**\n{result}")
    
    # ========================================================= #

    def get_db_build(self, str_val, siz_val):
        DB_BUILD_TABLE = [
        (64, "-2D6", -2),
        (84, "-1D6", -1),
        (124, "+0", 0),
        (164, "+1D4", 1),
        (204, "+1D6", 2),
        (999, "+2D6", 3)
        ]
        total = str_val + siz_val
        for limit, db, build in DB_BUILD_TABLE:
            if total <= limit:
                return db, build
        return "+0", 0


    def roll_character(self):
        STR = random.randint(3, 18) * 5
        CON = random.randint(3, 18) * 5
        SIZ = (random.randint(2, 12) + 6) * 5
        DEX = random.randint(3, 18) * 5
        APP = random.randint(3, 18) * 5
        INT = (random.randint(2, 12) + 6) * 5
        POW = random.randint(3, 18) * 5
        EDU = (random.randint(2, 12) + 6) * 5

        HP = (SIZ + CON) // 10
        MP = POW // 5
        SAN = POW
        LUCK = (random.randint(3, 18) * 5)
        DB, BUILD = self.get_db_build(STR, SIZ)
        
        TOTAL = STR + CON + SIZ + DEX + APP + INT + POW + EDU

        return {
            "STR": STR, "CON": CON, "SIZ": SIZ, "DEX": DEX, 
            "APP": APP, "INT": INT, "POW": POW, "EDU": EDU,
            "HP": HP, "MP": MP, "SAN": SAN, "LUCK": LUCK,
            "DB": DB, "BUILD": BUILD, "TOTAL" : TOTAL
        }

    def format_character(self, data, index=1):
        return (
            f"第 {index} 号调查员\n"
            f"力量: {data['STR']}  体质: {data['CON']}  体型: {data['SIZ']}\n"
            f"敏捷: {data['DEX']}  外貌: {data['APP']}  智力: {data['INT']}\n"
            f"意志: {data['POW']}  教育: {data['EDU']}\n"
            f"生命: {data['HP']}  魔力: {data['MP']}  理智: {data['SAN']}  幸运: {data['LUCK']}\n"
            f"DB: {data['DB']}  总和 : {data['TOTAL']} / {data['TOTAL'] + data['LUCK']}"
        )
    
    def roll_4d6_drop_lowest(self):
        rolls = [random.randint(1, 6) for _ in range(4)]
        return sum(sorted(rolls)[1:])

    def roll_dnd_character(self):
        return [
            self.roll_4d6_drop_lowest(),
            self.roll_4d6_drop_lowest(),
            self.roll_4d6_drop_lowest(),
            self.roll_4d6_drop_lowest(),
            self.roll_4d6_drop_lowest(),
            self.roll_4d6_drop_lowest(),
        ]

    def format_dnd_character(self, data, index=1):
        data = sorted(data, reverse=True)
        return (
        f"第 {index} 位冒险者\n"
        f"[{data[0]}, {data[1]}, {data[2]}, {data[3]}, {data[4]}, {data[5]}] → 共计 {sum(data)}"
        )
    
    @filter.command("coc")
    async def generate_coc_character(self, event: AstrMessageEvent, x: int = 1):
        """生成 x 个 CoC 角色数据"""
        characters = [self.roll_character() for _ in range(x)]
        result = "\n\n".join(self.format_character(characters[i], i+1) for i in range(x))
        yield event.plain_result(result)
        
    @filter.command("dnd")
    async def generate_dnd_character(self, event: AstrMessageEvent, x: int = 1):
        """生成 x 个 DnD 角色属性"""
        characters = [self.roll_dnd_character() for _ in range(x)]
        result = "\n\n".join(self.format_dnd_character(characters[i], i+1) for i in range(x))
        yield event.plain_result(result)
        
    # ========================================================= #
    # 注册指令 /dicehelp
    @filter.command("dicehelp")
    async def help ( self , event: AstrMessageEvent):
        help_text = (
"""---

🎲 RosaのTRPG 骰子帮助菜单 🎲
——关于这场掷骨游戏的备忘录

“我们走吧，你和我，当黄昏铺满天空，像一个上了乙醚的病人躺在手术台上。你以为这些指令是通往胜利的阶梯？不，它们只是在寂静中，为意志的瘫痪所做的、一次又一次的徒劳占卜。”

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

---
就这样吧。快点吧，时间到了。"""
        )

        yield event.plain_result(help_text)
        
    @filter.command("fireball")
    async def fireball(self, event: AstrMessageEvent, ring : int = 3):
        """投掷 n 环火球术伤害"""
        if ring < 3 :
            yield event.plain_result("请不要试图使用降环火球术！")
        rolls = [random.randint(1, 6) for _ in range(8 + (ring - 3))]
        total_sum = sum(rolls)

        damage_breakdown = " + ".join(map(str, rolls))
        result_message = (
            f"明亮的闪光从你的指间飞驰向施法距离内你指定的一点，并随着一声低吼迸成一片烈焰。\n"
            f"{ring} 环火球术的伤害投掷: {damage_breakdown} = 🔥{total_sum}🔥 点伤害！\n"
        )

        yield event.plain_result(result_message)