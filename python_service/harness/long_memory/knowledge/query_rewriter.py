"""
query_rewriter
~~~~~~~~~~~~~~
医学查询改写：将用户口语化问题扩展为更适合检索的结构化查询。

三层策略：
1. 指标缩写映射：GLU→血糖, Cr→肌酐, WBC→白细胞...
2. 症状/指标关键词提取 + 医学术语补全
3. 模板拼接：指标名 + 临床意义 + 参考范围 + 建议
"""

import re
from typing import List, Tuple

# ---- 医学指标缩写 → 中文全称 ----
INDICATOR_ALIASES: dict = {
    # 肾功能
    "cr": "血肌酐 肾功能", "creatinine": "血肌酐 肾功能",
    "bun": "血尿素氮 肾功能", "urea": "尿素 肾功能",
    "egfr": "估算肾小球滤过率 肾功能", "ua": "血尿酸 尿酸",
    "cysc": "胱抑素C 肾功能",
    # 血液系统
    "wbc": "白细胞计数 白细胞", "rbc": "红细胞计数 红细胞",
    "hb": "血红蛋白 贫血", "hgb": "血红蛋白 贫血",
    "hct": "血细胞比容 红细胞", "plt": "血小板计数 血小板",
    "mcv": "平均红细胞体积 贫血", "mch": "平均红细胞血红蛋白含量 贫血",
    "rdw": "红细胞分布宽度 贫血",
    # 肝功能
    "alt": "丙氨酸氨基转移酶 肝功能 转氨酶",
    "ast": "天冬氨酸氨基转移酶 肝功能 转氨酶",
    "ggt": "γ-谷氨酰转肽酶 肝功能 胆道",
    "alp": "碱性磷酸酶 肝功能 骨骼",
    "tbil": "总胆红素 肝功能 黄疸", "dbil": "直接胆红素 肝功能 黄疸",
    "tp": "总蛋白 肝功能", "alb": "白蛋白 肝功能",
    "tba": "总胆汁酸 肝功能",
    "che": "胆碱酯酶 肝功能",
    # 代谢
    "glu": "空腹血糖 糖尿病", "glucose": "血糖 糖尿病",
    "hba1c": "糖化血红蛋白 糖尿病 血糖控制",
    "tsh": "促甲状腺激素 甲状腺功能 甲减 甲亢",
    "t3": "三碘甲状腺原氨酸 甲状腺功能",
    "t4": "甲状腺素 甲状腺功能",
    "crp": "C反应蛋白 炎症 感染",
    # 脂质
    "chol": "总胆固醇 血脂 心血管",
    "cho": "总胆固醇 血脂 心血管",
    "tg": "甘油三酯 血脂 代谢综合征",
    "hdl": "高密度脂蛋白 血脂 心血管保护",
    "ldl": "低密度脂蛋白 血脂 动脉粥样硬化",
    # 电解质
    "na": "钠离子 电解质 脱水 水肿",
    "k": "钾离子 电解质 心律 心脏",
    "cl": "氯离子 电解质 酸碱平衡",
    "ca": "血钙 电解质 骨骼 甲状旁腺",
    "mg": "血镁 电解质 神经肌肉",
    "p": "血磷 电解质 骨骼 肾脏",
    # 心肌
    "ck": "肌酸激酶 心肌 肌肉",
    "ck-mb": "肌酸激酶MB同工体 心肌梗死",
    "ckmb": "肌酸激酶MB同工体 心肌梗死",
    "troponin": "肌钙蛋白 心肌梗死 心肌损伤",
    "bnp": "B型脑利钠肽 心力衰竭 心脏功能",
    "ldh": "乳酸脱氢酶 细胞坏死 溶血",
    # 白细胞分类
    "ne": "中性粒细胞 细菌感染 炎症",
    "ly": "淋巴细胞 病毒感染 免疫",
    "mo": "单核细胞 感染 结核 白血病",
    "eo": "嗜酸粒细胞 过敏 寄生虫",
    "ba": "嗜碱粒细胞 过敏 白血病",
    # 血小板
    "mpv": "平均血小板体积 血小板功能",
    "pct": "血小板比容 血小板",
    "pdw": "血小板分布宽度 血小板",
    # 其他
    "trop": "肌钙蛋白 心肌标志物",
    "glb": "球蛋白 免疫 肝功能",
    "glo": "球蛋白 免疫 肝功能",
    "a/g": "白球比 肝功能",
}

# ---- 常见口语表述 → 医学术语 ----
QUERY_EXPANSIONS: dict = {
    "偏高": "升高 高于正常 参考范围 异常原因",
    "偏低": "降低 低于正常 参考范围 异常原因",
    "高": "升高 参考范围 临床意义",
    "低": "降低 参考范围 临床意义",
    "怎么办": "处理建议 治疗方案 注意事项",
    "注意什么": "注意事项 饮食建议 生活方式",
    "什么意思": "临床意义 定义 解读",
    "严重吗": "严重程度 风险评估 预后",
    "吃什么": "饮食建议 食疗 营养",
    "头晕": "头晕 贫血 血压异常 低血糖 颈椎病",
    "头疼": "头痛 偏头痛 紧张性头痛 高血压",
    "没劲": "乏力 疲劳 贫血 甲状腺功能减退 电解质紊乱",
    "发烧": "发热 感染 炎症 白细胞升高 CRP升高",
    "水肿": "水肿 肾功能异常 心力衰竭 低蛋白血症",
    "心慌": "心悸 心律失常 甲状腺功能亢进 贫血",
    "恶心": "恶心 肝功能异常 胃肠道疾病 肾功能异常",
    "黄疸": "黄疸 胆红素升高 肝功能异常 肝炎",
    "腰疼": "腰痛 肾脏疾病 肾结石 腰椎病变",
}


def _extract_indicators(text: str) -> List[str]:
    """从用户输入中提取医学指标（缩写或中文）"""
    found: List[str] = []
    lower = text.lower()

    # 匹配英文缩写：使用前后边界替代 \b（\b 在 CJK 字符旁行为不一致）
    # 前缀：行首/空白/标点；后缀：行尾/空白/标点/CJK字符
    boundary_prefix = r"(?:^|[\s,，。、；;：:\(\)（）])"
    boundary_suffix = r"(?:$|[\s,，。、；;：:\(\)（）]|[一-鿿])"

    for abbr in INDICATOR_ALIASES:
        pattern = boundary_prefix + re.escape(abbr) + boundary_suffix
        if re.search(pattern, lower):
            found.append(abbr)

    # 匹配中文指标名
    cn_indicators = {
        "肌酐": "cr", "尿酸": "ua", "尿素": "urea", "尿素氮": "bun",
        "血糖": "glu", "血红蛋白": "hb", "白细胞": "wbc", "红细胞": "rbc",
        "血小板": "plt", "转氨酶": "alt", "胆红素": "tbil",
        "胆固醇": "chol", "甘油三酯": "tg", "高密度": "hdl", "低密度": "ldl",
        "钠": "na", "钾": "k", "钙": "ca", "氯": "cl",
        "肌酸激酶": "ck", "肌钙蛋白": "troponin", "白蛋白": "alb",
        "总蛋白": "tp", "球蛋白": "glb", "C反应蛋白": "crp",
    }
    for cn_name, abbr in cn_indicators.items():
        if cn_name in text and abbr not in found:
            found.append(abbr)

    return found


def rewrite_query(user_input: str) -> str:
    """
    将用户口语化输入改写为检索优化的查询字符串。

    输入: "我最近血糖偏高，怎么办？"
    输出: "我最近血糖偏高怎么办 血糖 空腹血糖 糖尿病 升高 高于正常 参考范围 异常原因 处理建议 治疗方案 注意事项"
    """
    parts = [user_input.strip()]

    # Step 1: 提取指标缩写 → 补全中文医学术语
    indicators = _extract_indicators(user_input)
    for abbr in indicators:
        expansion = INDICATOR_ALIASES.get(abbr, "")
        if expansion:
            parts.append(expansion)

    # Step 2: 口语词 → 医学术语扩展
    for keyword, expansion in QUERY_EXPANSIONS.items():
        if keyword in user_input:
            parts.append(expansion)

    # 去重并拼接
    seen = set()
    result_parts = []
    for part in parts:
        for word in part.split():
            if word not in seen:
                seen.add(word)
                result_parts.append(word)

    return " ".join(result_parts)


def extract_keywords(user_input: str) -> List[str]:
    """
    从用户输入中提取关键词列表，供重排序使用。
    提取：指标名、症状词、数值。
    """
    keywords = []

    # 提取数值
    numbers = re.findall(r"\d+\.?\d*", user_input)
    keywords.extend(numbers)

    # 提取指标
    keywords.extend(_extract_indicators(user_input))

    # 提取症状关键词
    symptom_words = [
        "偏高", "偏低", "高", "低", "正常", "异常",
        "头晕", "头疼", "心慌", "恶心", "发烧", "水肿", "黄疸",
        "乏力", "疲劳", "酸痛", "刺痛", "麻木",
        "怎么办", "注意", "严重", "建议", "治疗", "检查",
    ]
    for w in symptom_words:
        if w in user_input:
            keywords.append(w)

    return list(dict.fromkeys(keywords))  # 去重保序
