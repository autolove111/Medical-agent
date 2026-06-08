"""
饮食运动顾问：基于异常指标生成饮食和运动建议

设计原则：
- 建议来自两个来源：内置循证规则（优先） + RAG 检索（补充）
- 不可推荐具体药品，仅科普层面的大类原则
- 每条建议标记来源（内置规则 or RAG 文档名）
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DietaryAdvice:
    """单条饮食/运动建议"""
    title: str                              # 简短标题，如 "控制蛋白质摄入"
    detail: str                             # 详细说明
    target_indicators: list[str] = field(default_factory=list)  # 针对的异常指标
    category: str = "diet"                  # diet / exercise
    source: str = "内置循证规则"             # 来源标识


# ---- 循证饮食建议规则库 ----
# 格式：{indicator_key: [{title, detail, category}]}
_DIET_RULES: dict[str, list[dict]] = {
    # ===== 肾功能相关 =====
    "creatinine": [
        {
            "title": "优质低蛋白饮食",
            "detail": (
                "肾功能下降时，建议适当限制蛋白质总量，优先选择鸡蛋、牛奶、鱼肉等优质蛋白。"
                "每日蛋白质摄入量建议 0.6-0.8 g/kg 体重，避免红肉和加工肉制品。"
            ),
            "category": "diet",
        },
        {
            "title": "控制盐分摄入",
            "detail": (
                "每日食盐摄入量控制在 5g 以下，避免咸菜、腊肉、加工食品等高钠食物。"
                "肾功能受损时钠排泄能力下降，高盐饮食会加重水肿和高血压。"
            ),
            "category": "diet",
        },
        {
            "title": "低强度有氧运动",
            "detail": (
                "建议每周进行 3-5 次低强度有氧运动，如散步、太极拳、瑜伽，每次 30 分钟左右。"
                "避免剧烈运动和力量训练，以免加重肾脏负担。运动前后注意补充水分。"
            ),
            "category": "exercise",
        },
    ],
    "uric_acid": [
        {
            "title": "低嘌呤饮食",
            "detail": (
                "限制高嘌呤食物：动物内脏、海鲜（贝类/虾蟹）、浓肉汤、火锅汤底。"
                "适量选择中嘌呤食物：瘦肉、豆制品、蘑菇。鼓励低嘌呤食物：蔬菜、水果、全谷物。"
            ),
            "category": "diet",
        },
        {
            "title": "充足饮水",
            "detail": (
                "每日饮水量建议 2000-3000 mL，促进尿酸排泄。推荐白开水或淡茶水，"
                "避免含糖饮料和酒精（尤其是啤酒，嘌呤含量高）。"
            ),
            "category": "diet",
        },
    ],
    "bun": [
        {
            "title": "限制蛋白质总量 + 充足热量",
            "detail": (
                "尿素氮升高提示蛋白质代谢产物蓄积，应限制蛋白质摄入量，同时保证足够的热量摄入"
                "（30-35 kcal/kg/天），避免自身蛋白质分解。"
            ),
            "category": "diet",
        },
    ],

    # ===== 血糖相关 =====
    "glucose": [
        {
            "title": "低GI饮食，控制碳水化合物",
            "detail": (
                "选择低血糖生成指数(GI)食物：全麦面包、燕麦、糙米、荞麦面代替精白米饭/馒头。"
                "每餐碳水化合物摄入量均匀分配，避免一餐大量摄入。"
            ),
            "category": "diet",
        },
        {
            "title": "增加膳食纤维",
            "detail": (
                "每日蔬菜摄入量 500g 以上，优先选择绿叶蔬菜。适量水果（200g/天），"
                "选择低糖水果如苹果、柚子、草莓，避免香蕉、荔枝等。"
            ),
            "category": "diet",
        },
        {
            "title": "规律有氧 + 抗阻运动",
            "detail": (
                "每周至少 150 分钟中等强度有氧运动（快走、骑车、游泳），"
                "每周 2-3 次抗阻训练（深蹲、弹力带）。饭后 1 小时运动效果最佳，注意预防低血糖。"
            ),
            "category": "exercise",
        },
    ],

    # ===== 血脂相关 =====
    "cholesterol": [
        {
            "title": "低饱和脂肪饮食",
            "detail": (
                "减少饱和脂肪摄入：肥肉、黄油、奶油、椰子油。"
                "增加不饱和脂肪：橄榄油、坚果（每日一小把）、深海鱼。"
            ),
            "category": "diet",
        },
        {
            "title": "增加可溶性膳食纤维",
            "detail": (
                "燕麦、豆类、苹果、柑橘类水果富含可溶性纤维，有助降低胆固醇。"
                "每日膳食纤维总量建议 25-30g。"
            ),
            "category": "diet",
        },
    ],
    "triglyceride": [
        {
            "title": "严格限糖 + 限酒",
            "detail": (
                "高甘油三酯与糖分和酒精摄入密切相关。严格限制添加糖：含糖饮料、甜点、糖果。"
                "完全戒酒至少 2-4 周后复查，酒精是甘油三酯升高最常见诱因。"
            ),
            "category": "diet",
        },
        {
            "title": "有氧运动降甘油三酯",
            "detail": (
                "有氧运动对降低甘油三酯效果显著。建议每周 5 次、每次 40 分钟以上的中等强度有氧运动"
                "（慢跑、游泳、跳操），运动消耗直接利用血液中的甘油三酯。"
            ),
            "category": "exercise",
        },
    ],

    # ===== 肝功能相关 =====
    "alt": [
        {
            "title": "严格戒酒",
            "detail": (
                "转氨酶升高期间必须完全戒酒，酒精代谢产物直接损伤肝细胞。"
                "戒酒 2-4 周后复查肝功能。"
            ),
            "category": "diet",
        },
        {
            "title": "避免肝毒性食物与药物",
            "detail": (
                "避免霉变食物（含黄曲霉素）、生腌海鲜。慎用可能伤肝的保健品和中草药。"
                "多摄入富含抗氧化物质的食物：西兰花、菠菜、蓝莓。"
            ),
            "category": "diet",
        },
    ],

    # ===== 贫血相关 =====
    "hemoglobin": [
        {
            "title": "补铁饮食",
            "detail": (
                "增加血红素铁食物：动物肝脏（每周 1-2 次，每次 50g）、瘦红肉、鸭血。"
                "搭配维生素C促进铁吸收：餐后吃橙子/猕猴桃，或蔬菜配柠檬汁。"
            ),
            "category": "diet",
        },
        {
            "title": "避免抑制铁吸收的食物",
            "detail": (
                "餐后 1 小时内避免喝浓茶和咖啡（鞣酸抑制铁吸收）。"
                "钙片和铁剂分开服用，间隔至少 2 小时。"
            ),
            "category": "diet",
        },
    ],

    # ===== 电解质相关 =====
    "potassium": [
        {
            "title": "调整钾摄入（依据高低方向）",
            "detail": (
                "血钾偏低：增加香蕉、土豆、菠菜、番茄、牛油果等富钾食物。"
                "血钾偏高（尤其肾病患者）：限制上述食物，蔬菜焯水后再烹饪以去除部分钾。"
            ),
            "category": "diet",
        },
    ],
    "sodium": [
        {
            "title": "调整钠摄入",
            "detail": (
                "血钠偏低（除外稀释性低钠）：适当增加盐摄入，喝淡盐水。"
                "血钠偏高：严格限盐（<5g/天），多饮水促进排泄。"
            ),
            "category": "diet",
        },
    ],

    # ===== 炎症相关 =====
    "crp": [
        {
            "title": "抗炎饮食模式",
            "detail": (
                "增加 Omega-3 脂肪酸：深海鱼（三文鱼、沙丁鱼）每周 3 次。"
                "多吃彩色蔬果（富含多酚）、姜黄、大蒜。减少精加工食品和反式脂肪。"
            ),
            "category": "diet",
        },
    ],
}


class DietaryAdvisor:
    """饮食运动顾问"""

    def __init__(self):
        self._rules = _DIET_RULES

    def get_advice_for_indicators(
        self,
        abnormal_keys: list[str],
    ) -> list[DietaryAdvice]:
        """
        根据异常指标列表，返回匹配的饮食运动建议

        参数：
            abnormal_keys: 异常指标 key 列表（已解析为标准 key，如 "Cr", "GLU"）

        返回：去重后的建议列表
        """
        advice_map: dict[str, DietaryAdvice] = {}  # title → advice，用于去重

        for key in abnormal_keys:
            # 尝试直接匹配和别名匹配
            candidates = [key, key.lower(), key.upper()]
            for c in candidates:
                if c in self._rules:
                    for rule in self._rules[c]:
                        if rule["title"] not in advice_map:
                            advice_map[rule["title"]] = DietaryAdvice(
                                title=rule["title"],
                                detail=rule["detail"],
                                target_indicators=[c],
                                category=rule["category"],
                            )
                        else:
                            # 合并目标指标
                            existing = advice_map[rule["title"]]
                            if c not in existing.target_indicators:
                                existing.target_indicators.append(c)

        return list(advice_map.values())

    def generate_diet_section(self, abnormal_keys: list[str]) -> str:
        """生成饮食部分的 prompt 文本"""
        diet_advice = [a for a in self.get_advice_for_indicators(abnormal_keys) if a.category == "diet"]
        if not diet_advice:
            return ""

        lines = ["## 🍽️ 饮食建议"]
        for a in diet_advice:
            indicators = ", ".join(a.target_indicators)
            lines.append(f"\n### {a.title}")
            lines.append(f"针对指标：{indicators}")
            lines.append(f"{a.detail}")
            lines.append(f"（来源：{a.source}）")

        return "\n".join(lines)

    def generate_exercise_section(self, abnormal_keys: list[str]) -> str:
        """生成运动部分的 prompt 文本"""
        exercise_advice = [a for a in self.get_advice_for_indicators(abnormal_keys) if a.category == "exercise"]
        if not exercise_advice:
            return ""

        lines = ["## 🏃 运动建议"]
        for a in exercise_advice:
            indicators = ", ".join(a.target_indicators)
            lines.append(f"\n### {a.title}")
            lines.append(f"针对指标：{indicators}")
            lines.append(f"{a.detail}")
            lines.append(f"（来源：{a.source}）")

        return "\n".join(lines)
