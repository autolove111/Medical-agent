"""
检验指标参考范围数据库
提供统一的医学参考值，支持 RAG 系统和患者病历查询
"""

REFERENCE_RANGES = {
    # ===== 肾功能指标 =====
    "Cr": {
        "name": "血肌酐 (Creatinine)",
        "unit": "μmol/L",
        "pediatric": {"min": 15, "max": 40},
        "child": {"min": 15, "max": 40},
        "infant": {"min": 15, "max": 40},
        "adolescent": {"min": 44, "max": 88},
        "teen": {"min": 44, "max": 88},
        "adult": {"min": 60, "max": 115},
        "elderly": {"min": 60, "max": 115},
        "geriatric": {"min": 60, "max": 115},
        "senior": {"min": 60, "max": 115},
        "male": {"min": 80, "max": 115},
        "female": {"min": 60, "max": 93},
        "critical_high": 500,
        "critical_low": 30,
        "description": "肾功能主要标志，升高提示肾脏清除功能下降",
        "clinical_stages": {
            "G1": {"min": None, "max": None, "desc": "正常肾功能（>90 mL/min）"},
            "G2": {"min": None, "max": None, "desc": "轻度肾功能下降（60-89 mL/min）"},
            "G3a": {"min": None, "max": None, "desc": "轻中度肾功能下降（45-59 mL/min）"},
            "G3b": {"min": None, "max": None, "desc": "中重度肾功能下降（30-44 mL/min）"},
            "G4": {"min": None, "max": None, "desc": "重度肾功能下降（15-29 mL/min）"},
            "G5": {"min": None, "max": None, "desc": "肾功能衰竭（<15 mL/min）"}
        }
    },
    "BUN": {
        "name": "血尿素氮 (Blood Urea Nitrogen)",
        "unit": "mmol/L",
        "pediatric": {"min": 1.8, "max": 6.4},
        "child": {"min": 1.8, "max": 6.4},
        "infant": {"min": 1.8, "max": 6.4},
        "adolescent": {"min": 2.5, "max": 7.1},
        "teen": {"min": 2.5, "max": 7.1},
        "adult": {"min": 2.5, "max": 8.0},
        "elderly": {"min": 3.0, "max": 9.0},
        "geriatric": {"min": 3.0, "max": 9.0},
        "senior": {"min": 3.0, "max": 9.0},
        "normal": {"min": 2.5, "max": 8.0},
        "critical_high": 15,
        "description": "肾脏清除功能标志，升高可能提示肾脏病变或脱水"
    },
    "eGFR": {
        "name": "估算肾小球滤过率 (Estimated GFR)",
        "unit": "mL/min/1.73m²",
        "pediatric": {"min": 90, "max": None},
        "child": {"min": 90, "max": None},
        "infant": {"min": 90, "max": None},
        "adolescent": {"min": 90, "max": None},
        "teen": {"min": 90, "max": None},
        "adult": {"min": 85, "max": None},
        "elderly": {"min": 60, "max": None},
        "geriatric": {"min": 60, "max": None},
        "senior": {"min": 60, "max": None},
        "normal": {"min": 85, "max": None},
        "male": {"min": 90, "max": None},
        "female": {"min": 85, "max": None},
        "description": "更准确的肾功能评估指标，基于Cr和年龄等计算"
    },
    "UA": {
        "name": "血尿酸 (Uric Acid)",
        "unit": "μmol/L",
        "pediatric": {"min": 120, "max": 360},
        "child": {"min": 120, "max": 360},
        "infant": {"min": 120, "max": 360},
        "adolescent": {"min": 140, "max": 380},
        "teen": {"min": 140, "max": 380},
        "adult": {"min": 140, "max": 400},
        "elderly": {"min": 140, "max": 420},
        "geriatric": {"min": 140, "max": 420},
        "senior": {"min": 140, "max": 420},
        "normal": {"min": 140, "max": 400},
        "male": {"min": 200, "max": 400},
        "female": {"min": 140, "max": 320},
        "critical_high": 600,
        "description": "尿酸代谢指标，升高与痛风、肾脏病相关"
    },

    # ===== 血液系统指标 (CBC) =====
    "WBC": {
        "name": "白细胞计数 (White Blood Cell Count)",
        "unit": "×10⁹/L",
        "pediatric": {"min": 5.0, "max": 12.0},
        "child": {"min": 5.0, "max": 12.0},
        "infant": {"min": 6.0, "max": 17.5},
        "adolescent": {"min": 4.5, "max": 11.0},
        "teen": {"min": 4.5, "max": 11.0},
        "adult": {"min": 4.5, "max": 11.0},
        "elderly": {"min": 3.8, "max": 10.5},
        "geriatric": {"min": 3.8, "max": 10.5},
        "senior": {"min": 3.8, "max": 10.5},
        "normal": {"min": 4.5, "max": 11.0},
        "critical_low": 1.5,
        "critical_high": 30,
        "description": "免疫细胞数量，升高提示感染或炎症，降低提示免疫抑制"
    },
    "RBC": {
        "name": "红细胞计数 (Red Blood Cell Count)",
        "unit": "×10¹²/L",
        "pediatric": {"min": 3.8, "max": 5.2},
        "child": {"min": 3.8, "max": 5.2},
        "infant": {"min": 3.9, "max": 5.5},
        "adolescent": {"min": 4.0, "max": 5.3},
        "teen": {"min": 4.0, "max": 5.3},
        "adult": {"min": 4.1, "max": 5.9},
        "elderly": {"min": 3.8, "max": 5.6},
        "geriatric": {"min": 3.8, "max": 5.6},
        "senior": {"min": 3.8, "max": 5.6},
        "normal": {"min": 4.1, "max": 5.9},
        "male": {"min": 4.5, "max": 5.9},
        "female": {"min": 4.1, "max": 5.1},
        "critical_low": 2.0,
        "critical_high": 8.0,
        "description": "红细胞数量，降低提示贫血，升高提示脱水或真性红细胞增多症"
    },
    "HB": {
        "name": "血红蛋白 (Hemoglobin)",
        "unit": "g/L",
        "pediatric": {"min": 95, "max": 145},
        "child": {"min": 95, "max": 145},
        "infant": {"min": 100, "max": 150},
        "adolescent": {"min": 110, "max": 160},
        "teen": {"min": 110, "max": 160},
        "adult": {"min": 115, "max": 175},
        "elderly": {"min": 110, "max": 170},
        "geriatric": {"min": 110, "max": 170},
        "senior": {"min": 110, "max": 170},
        "normal": {"min": 115, "max": 175},
        "male": {"min": 130, "max": 175},
        "female": {"min": 115, "max": 150},
        "critical_low": 70,
        "description": "携氧蛋白质，降低提示贫血"
    },
    "HCT": {
        "name": "血细胞比容 (Hematocrit)",
        "unit": "%",
        "male": {"min": 41, "max": 53},
        "female": {"min": 36, "max": 46},
        "description": "红细胞容积百分比，用于评估贫血程度"
    },
    "PLT": {
        "name": "血小板计数 (Platelet Count)",
        "unit": "×10⁹/L",
        "pediatric": {"min": 150, "max": 450},
        "child": {"min": 150, "max": 450},
        "infant": {"min": 150, "max": 450},
        "adolescent": {"min": 150, "max": 400},
        "teen": {"min": 150, "max": 400},
        "adult": {"min": 150, "max": 400},
        "elderly": {"min": 130, "max": 350},
        "geriatric": {"min": 130, "max": 350},
        "senior": {"min": 130, "max": 350},
        "normal": {"min": 150, "max": 400},
        "critical_low": 50,
        "critical_high": 1000,
        "description": "止血细胞，降低增加出血风险，升高增加血栓风险"
    },

    # ===== 肝功能指标 =====
    "ALT": {
        "name": "丙氨酸氨基转移酶 (Alanine Aminotransferase)",
        "unit": "U/L",
        "pediatric": {"min": None, "max": 45},
        "child": {"min": None, "max": 45},
        "infant": {"min": None, "max": 50},
        "adolescent": {"min": None, "max": 40},
        "teen": {"min": None, "max": 40},
        "adult": {"min": None, "max": 40},
        "elderly": {"min": None, "max": 40},
        "geriatric": {"min": None, "max": 40},
        "senior": {"min": None, "max": 40},
        "normal": {"min": None, "max": 40},
        "male": {"min": None, "max": 40},
        "female": {"min": None, "max": 32},
        "critical_high": 500,
        "description": "肝脏损伤标志，升高提示肝炎或肝脏病变"
    },
    "AST": {
        "name": "天冬氨酸氨基转移酶 (Aspartate Aminotransferase)",
        "unit": "U/L",
        "pediatric": {"min": None, "max": 45},
        "child": {"min": None, "max": 45},
        "infant": {"min": None, "max": 50},
        "adolescent": {"min": None, "max": 40},
        "teen": {"min": None, "max": 40},
        "adult": {"min": None, "max": 40},
        "elderly": {"min": None, "max": 40},
        "geriatric": {"min": None, "max": 40},
        "senior": {"min": None, "max": 40},
        "normal": {"min": None, "max": 40},
        "critical_high": 500,
        "description": "肝脏和心肌损伤标志，AST/ALT比值>1提示酒精性肝病"
    },
    "GGT": {
        "name": "γ-谷氨酰转肽酶 (Gamma-Glutamyl Transferase)",
        "unit": "U/L",
        "male": {"min": None, "max": 64},
        "female": {"min": None, "max": 36},
        "description": "胆逆流标志，升高与胆石症或肝病相关"
    },
    "ALP": {
        "name": "碱性磷酸酶 (Alkaline Phosphatase)",
        "unit": "U/L",
        "adult": {"min": 30, "max": 120},
        "description": "骨代谢标志，升高与骨病或肝病相关"
    },
    "TBIL": {
        "name": "总胆红素 (Total Bilirubin)",
        "unit": "μmol/L",
        "pediatric": {"min": 0, "max": 20},
        "child": {"min": 0, "max": 20},
        "infant": {"min": 0, "max": 20},
        "adolescent": {"min": 0, "max": 21},
        "teen": {"min": 0, "max": 21},
        "adult": {"min": 0, "max": 20},
        "elderly": {"min": 0, "max": 22},
        "geriatric": {"min": 0, "max": 22},
        "senior": {"min": 0, "max": 22},
        "normal": {"min": None, "max": 20},
        "critical_high": 50,
        "description": "肝脏排泄功能标志，升高提示肝炎或溶血"
    },
    "DBIL": {
        "name": "直接胆红素 (Direct Bilirubin)",
        "unit": "μmol/L",
        "pediatric": {"min": 0, "max": 8},
        "child": {"min": 0, "max": 8},
        "infant": {"min": 0, "max": 8},
        "adolescent": {"min": 0, "max": 6},
        "teen": {"min": 0, "max": 6},
        "adult": {"min": 0, "max": 5},
        "elderly": {"min": 0, "max": 6},
        "geriatric": {"min": 0, "max": 6},
        "senior": {"min": 0, "max": 6},
        "normal": {"min": None, "max": 5},
        "description": "胆道排泄功能标志，升高提示胆汁淤积"
    },

    # ===== 代谢指标 =====
    "GLU": {
        "name": "血糖 (Glucose)",
        "unit": "mmol/L",
        "pediatric": {"min": 3.6, "max": 6.1},
        "child": {"min": 3.6, "max": 6.1},
        "infant": {"min": 3.3, "max": 6.0},
        "adolescent": {"min": 3.9, "max": 6.1},
        "teen": {"min": 3.9, "max": 6.1},
        "adult": {"min": 3.9, "max": 6.0},
        "elderly": {"min": 4.1, "max": 6.5},
        "geriatric": {"min": 4.1, "max": 6.5},
        "senior": {"min": 4.1, "max": 6.5},
        "normal": {"min": 3.9, "max": 7.8},
        "fasting": {"min": 3.9, "max": 6.0},
        "postprandial": {"min": None, "max": 7.8},
        "critical_low": 2.8,
        "critical_high": 30,
        "description": "能量代谢标志，升高提示糖尿病，降低提示低血糖"
    },
    "HbA1c": {
        "name": "糖化血红蛋白 (Hemoglobin A1c)",
        "unit": "%",
        "pediatric": {"min": 4.0, "max": 5.9},
        "child": {"min": 4.0, "max": 5.9},
        "infant": {"min": 4.0, "max": 6.0},
        "adolescent": {"min": 4.0, "max": 5.9},
        "teen": {"min": 4.0, "max": 5.9},
        "adult": {"min": 4.0, "max": 5.7},
        "elderly": {"min": 4.0, "max": 6.2},
        "geriatric": {"min": 4.0, "max": 6.2},
        "senior": {"min": 4.0, "max": 6.2},
        "normal": {"min": 4.0, "max": 5.7},
        "prediabetes": {"min": 5.7, "max": 6.4},
        "diabetes": {"min": 6.5, "max": None},
        "description": "近2-3个月平均血糖水平，糖尿病筛查与疗效评估核心指标"
    },
    "TSH": {
        "name": "促甲状腺激素 (Thyroid Stimulating Hormone)",
        "unit": "mIU/L",
        "pediatric": {"min": 0.7, "max": 6.0},
        "child": {"min": 0.7, "max": 6.0},
        "infant": {"min": 1.0, "max": 8.0},
        "adolescent": {"min": 0.5, "max": 5.0},
        "teen": {"min": 0.5, "max": 5.0},
        "adult": {"min": 0.27, "max": 4.2},
        "elderly": {"min": 0.4, "max": 6.0},
        "geriatric": {"min": 0.4, "max": 6.0},
        "senior": {"min": 0.4, "max": 6.0},
        "normal": {"min": 0.27, "max": 4.2},
        "description": "甲状腺轴关键调节激素，升高多见于甲减，降低多见于甲亢"
    },
    "T3": {
        "name": "三碘甲状腺原氨酸 (Triiodothyronine, T3)",
        "unit": "nmol/L",
        "pediatric": {"min": 1.3, "max": 3.1},
        "child": {"min": 1.3, "max": 3.1},
        "infant": {"min": 1.4, "max": 3.5},
        "adolescent": {"min": 1.2, "max": 3.1},
        "teen": {"min": 1.2, "max": 3.1},
        "adult": {"min": 1.3, "max": 3.1},
        "elderly": {"min": 1.0, "max": 2.8},
        "geriatric": {"min": 1.0, "max": 2.8},
        "senior": {"min": 1.0, "max": 2.8},
        "normal": {"min": 1.3, "max": 3.1},
        "description": "甲状腺激素活性形式之一，评估甲状腺功能状态"
    },
    "T4": {
        "name": "甲状腺素 (Thyroxine, T4)",
        "unit": "nmol/L",
        "pediatric": {"min": 70, "max": 170},
        "child": {"min": 70, "max": 170},
        "infant": {"min": 80, "max": 190},
        "adolescent": {"min": 65, "max": 165},
        "teen": {"min": 65, "max": 165},
        "adult": {"min": 66, "max": 181},
        "elderly": {"min": 60, "max": 160},
        "geriatric": {"min": 60, "max": 160},
        "senior": {"min": 60, "max": 160},
        "normal": {"min": 66, "max": 181},
        "description": "甲状腺分泌的主要激素，联合TSH/T3用于甲功判断"
    },
    "CRP": {
        "name": "C反应蛋白 (C-Reactive Protein)",
        "unit": "mg/L",
        "pediatric": {"min": 0, "max": 8},
        "child": {"min": 0, "max": 8},
        "infant": {"min": 0, "max": 10},
        "adolescent": {"min": 0, "max": 8},
        "teen": {"min": 0, "max": 8},
        "adult": {"min": 0, "max": 8},
        "elderly": {"min": 0, "max": 10},
        "geriatric": {"min": 0, "max": 10},
        "senior": {"min": 0, "max": 10},
        "normal": {"min": 0, "max": 8},
        "critical_high": 100,
        "description": "急性时相炎症指标，升高提示感染、炎症或组织损伤"
    },
    "CHOL": {
        "name": "总胆固醇 (Total Cholesterol)",
        "unit": "mmol/L",
        "optimal": {"min": None, "max": 5.2},
        "borderline_high": {"min": 5.2, "max": 6.2},
        "high": {"min": 6.2, "max": None},
        "description": "脂质代谢指标，升高与心血管疾病风险相关"
    },
    "TG": {
        "name": "甘油三酯 (Triglycerides)",
        "unit": "mmol/L",
        "normal": {"min": None, "max": 1.7},
        "borderline_high": {"min": 1.7, "max": 2.3},
        "high": {"min": 2.3, "max": None},
        "description": "脂质代谢指标，升高与代谢综合征相关"
    },
    "HDL": {
        "name": "高密度脂蛋白 (High-Density Lipoprotein)",
        "unit": "mmol/L",
        "male": {"min": 1.0, "max": None},
        "female": {"min": 1.3, "max": None},
        "description": "保护性脂蛋白，升高降低心血管风险"
    },
    "LDL": {
        "name": "低密度脂蛋白 (Low-Density Lipoprotein)",
        "unit": "mmol/L",
        "optimal": {"min": None, "max": 2.6},
        "borderline_high": {"min": 2.6, "max": 3.4},
        "high": {"min": 3.4, "max": None},
        "description": "致病性脂蛋白，升高增加心血管风险"
    },

    # ===== 电解质指标 =====
    "Na": {
        "name": "钠离子 (Sodium)",
        "unit": "mmol/L",
        "pediatric": {"min": 135, "max": 145},
        "child": {"min": 135, "max": 145},
        "infant": {"min": 133, "max": 146},
        "adolescent": {"min": 136, "max": 145},
        "teen": {"min": 136, "max": 145},
        "adult": {"min": 136, "max": 145},
        "elderly": {"min": 135, "max": 145},
        "geriatric": {"min": 135, "max": 145},
        "senior": {"min": 135, "max": 145},
        "normal": {"min": 136, "max": 145},
        "critical_low": 120,
        "critical_high": 160,
        "description": "细胞外液主要阳离子，异常与脑水肿或脱水相关"
    },
    "K": {
        "name": "钾离子 (Potassium)",
        "unit": "mmol/L",
        "pediatric": {"min": 3.5, "max": 5.2},
        "child": {"min": 3.5, "max": 5.2},
        "infant": {"min": 3.7, "max": 5.9},
        "adolescent": {"min": 3.5, "max": 5.2},
        "teen": {"min": 3.5, "max": 5.2},
        "adult": {"min": 3.5, "max": 5.2},
        "elderly": {"min": 3.5, "max": 5.3},
        "geriatric": {"min": 3.5, "max": 5.3},
        "senior": {"min": 3.5, "max": 5.3},
        "normal": {"min": 3.5, "max": 5.2},
        "critical_low": 2.5,
        "critical_high": 6.5,
        "description": "细胞内液主要阳离子，异常影响心脏传导"
    },
    "Cl": {
        "name": "氯离子 (Chloride)",
        "unit": "mmol/L",
        "pediatric": {"min": 98, "max": 107},
        "child": {"min": 98, "max": 107},
        "infant": {"min": 96, "max": 110},
        "adolescent": {"min": 98, "max": 107},
        "teen": {"min": 98, "max": 107},
        "adult": {"min": 98, "max": 107},
        "elderly": {"min": 98, "max": 108},
        "geriatric": {"min": 98, "max": 108},
        "senior": {"min": 98, "max": 108},
        "normal": {"min": 98, "max": 107},
        "description": "主要阴离子，参与酸碱平衡"
    },
    "Ca": {
        "name": "血钙 (Calcium)",
        "unit": "mmol/L",
        "pediatric": {"min": 2.10, "max": 2.70},
        "child": {"min": 2.10, "max": 2.70},
        "infant": {"min": 2.15, "max": 2.75},
        "adolescent": {"min": 2.12, "max": 2.65},
        "teen": {"min": 2.12, "max": 2.65},
        "adult": {"min": 2.12, "max": 2.63},
        "elderly": {"min": 2.10, "max": 2.60},
        "geriatric": {"min": 2.10, "max": 2.60},
        "senior": {"min": 2.10, "max": 2.60},
        "normal": {"min": 2.12, "max": 2.63},
        "critical_low": 1.8,
        "critical_high": 3.5,
        "description": "骨代谢和神经肌肉传导关键，异常与骨病或甲状旁腺病相关"
    },
    "Mg": {
        "name": "血镁 (Magnesium)",
        "unit": "mmol/L",
        "normal": {"min": 0.75, "max": 1.02},
        "description": "酶促反应必需元素，降低影响肌肉和神经功能"
    },
    "P": {
        "name": "血磷 (Phosphate)",
        "unit": "mmol/L",
        "pediatric": {"min": 1.0, "max": 1.9},
        "child": {"min": 1.0, "max": 1.9},
        "infant": {"min": 1.2, "max": 2.1},
        "adolescent": {"min": 0.9, "max": 1.7},
        "teen": {"min": 0.9, "max": 1.7},
        "adult": {"min": 0.81, "max": 1.45},
        "elderly": {"min": 0.75, "max": 1.45},
        "geriatric": {"min": 0.75, "max": 1.45},
        "senior": {"min": 0.75, "max": 1.45},
        "normal": {"min": 0.81, "max": 1.45},
        "critical_low": 0.3,
        "critical_high": 2.5,
        "description": "能量代谢和骨矿化关键，异常与肾脏病或骨病相关"
    },
    "PO4": {
        "name": "磷酸根 (Phosphate)",
        "unit": "mmol/L",
        "pediatric": {"min": 1.0, "max": 1.9},
        "child": {"min": 1.0, "max": 1.9},
        "infant": {"min": 1.2, "max": 2.1},
        "adolescent": {"min": 0.9, "max": 1.7},
        "teen": {"min": 0.9, "max": 1.7},
        "adult": {"min": 0.81, "max": 1.45},
        "elderly": {"min": 0.75, "max": 1.45},
        "geriatric": {"min": 0.75, "max": 1.45},
        "senior": {"min": 0.75, "max": 1.45},
        "normal": {"min": 0.81, "max": 1.45},
        "critical_low": 0.3,
        "critical_high": 2.5,
        "description": "能量代谢和骨矿化关键，异常与肾脏病或骨病相关"
    },

    # ===== 红细胞形态指标 =====
    "MCV": {
        "name": "平均红细胞体积 (Mean Corpuscular Volume)",
        "unit": "fL",
        "normal": {"min": 80, "max": 100},
        "description": "反映红细胞大小，降低提示小细胞贫血，升高提示大细胞贫血"
    },
    "MCH": {
        "name": "平均红细胞血红蛋白含量 (Mean Corpuscular Hemoglobin)",
        "unit": "pg",
        "normal": {"min": 27, "max": 33},
        "description": "每个红细胞含血红蛋白量，降低提示低血红蛋白性贫血"
    },
    "MCHC": {
        "name": "平均红细胞血红蛋白浓度 (Mean Corpuscular Hemoglobin Concentration)",
        "unit": "g/L",
        "normal": {"min": 320, "max": 360},
        "description": "红细胞内血红蛋白浓度，降低提示低色素性贫血"
    },
    "RDW": {
        "name": "红细胞分布宽度 (Red Cell Distribution Width)",
        "unit": "%",
        "normal": {"min": 11.5, "max": 14.5},
        "description": "反映红细胞大小不均匀程度，升高提示异形贫血或溶血"
    },
    "NRBC": {
        "name": "有核红细胞 (Nucleated Red Blood Cell)",
        "unit": "×10⁹/L",
        "normal": {"min": 0, "max": 0},
        "description": "正常人外周血无有核红细胞，出现提示造血功能代偿或肿瘤"
    },

    # ===== 白细胞分类 =====
    "NE": {
        "name": "中性粒细胞 (Neutrophils)",
        "unit": "%",
        "normal": {"min": 50, "max": 70},
        "absolute": {"min": 2.0, "max": 7.5},  # ×10⁹/L
        "description": "白细胞中比例最高的细胞，升高提示细菌感染或炎症"
    },
    "LY": {
        "name": "淋巴细胞 (Lymphocytes)",
        "unit": "%",
        "normal": {"min": 20, "max": 40},
        "absolute": {"min": 1.0, "max": 4.8},  # ×10⁹/L
        "description": "免疫细胞，升高提示病毒感染或淋巴瘤，降低提示免疫缺陷"
    },
    "MO": {
        "name": "单核细胞 (Monocytes)",
        "unit": "%",
        "normal": {"min": 3, "max": 10},
        "absolute": {"min": 0.1, "max": 0.6},  # ×10⁹/L
        "description": "吞噬细胞，升高提示细菌感染、结核或白血病"
    },
    "EO": {
        "name": "嗜酸粒细胞 (Eosinophils)",
        "unit": "%",
        "normal": {"min": 1, "max": 4},
        "absolute": {"min": 0.05, "max": 0.5},  # ×10⁹/L
        "description": "抗寄生虫和过敏反应，升高与过敏或寄生虫感染相关"
    },
    "BA": {
        "name": "嗜碱粒细胞 (Basophils)",
        "unit": "%",
        "normal": {"min": 0, "max": 1},
        "absolute": {"min": 0, "max": 0.1},  # ×10⁹/L
        "description": "参与过敏反应，升高罕见，多见于白血病"
    },

    # ===== 血小板相关指标 =====
    "MPV": {
        "name": "平均血小板体积 (Mean Platelet Volume)",
        "unit": "fL",
        "normal": {"min": 7.4, "max": 10.4},
        "description": "反映血小板大小，升高与出血倾向相关，降低与脾脏疾病相关"
    },
    "PCT": {
        "name": "血小板比容 (Plateletcrit)",
        "unit": "%",
        "normal": {"min": 0.108, "max": 0.282},
        "description": "血小板体积占血液总体积的百分比，反映血小板的生成和消耗"
    },
    "PDW": {
        "name": "血小板分布宽度 (Platelet Distribution Width)",
        "unit": "%",
        "normal": {"min": 10, "max": 18},
        "description": "反映血小板体积不均匀程度，升高提示血小板异常或造血功能异常"
    },

    # ===== 脂质指标别名 =====
    "CHO": {
        "name": "总胆固醇 (Total Cholesterol)",
        "unit": "mmol/L",
        "optimal": {"min": None, "max": 5.2},
        "borderline_high": {"min": 5.2, "max": 6.2},
        "high": {"min": 6.2, "max": None},
        "description": "脂质代谢指标，升高与心血管疾病风险相关"
    },

    # ===== 心肌标志物 =====
    "CK-MB": {
        "name": "肌酸激酶MB同工体 (Creatine Kinase-MB)",
        "unit": "U/L",
        "normal": {"min": None, "max": 24},
        "critical_high": 50,
        "description": "心肌损伤标志物，升高提示心肌梗死或心肌炎"
    },
    "Troponin": {
        "name": "肌钙蛋白 (Troponin I/T)",
        "unit": "pg/mL",
        "normal": {"min": None, "max": 0.04},
        "critical_high": 0.1,
        "description": "高特异性心肌损伤标志物，最佳早期诊断指标"
    },
    "BNP": {
        "name": "B型脑利钠肽 (B-type Natriuretic Peptide)",
        "unit": "pg/mL",
        "normal": {"min": None, "max": 100},
        "heart_failure": {"min": 100, "max": None},
        "description": "心脏功能标志物，升高提示心力衰竭"
    },

    # ===== 蛋白质代谢指标 =====
    "TP": {
        "name": "总蛋白 (Total Protein)",
        "unit": "g/L",
        "normal": {"min": 60, "max": 80},
        "critical_low": 40,
        "description": "肝脏合成功能标志，降低与肝脏病变或营养不良相关"
    },
    "ALB": {
        "name": "白蛋白 (Albumin)",
        "unit": "g/L",
        "normal": {"min": 35, "max": 55},
        "critical_low": 20,
        "description": "肝脏合成功能主要标志，降低与肝脏合成功能下降相关"
    },
    "GLO": {
        "name": "球蛋白 (Globulin)",
        "unit": "g/L",
        "normal": {"min": 20, "max": 35},
        "description": "免疫球蛋白和其他蛋白组成，升高与免疫反应或肝脏病变相关"
    },
    "A/G": {
        "name": "白球比 (Albumin/Globulin Ratio)",
        "unit": "比值",
        "normal": {"min": 1.2, "max": 2.3},
        "description": "反映肝脏合成功能，降低常见于肝脏病变"
    },

    # ===== 胆汁酸和胆汁相关 =====
    "TBA": {
        "name": "总胆汁酸 (Total Bile Acid)",
        "unit": "μmol/L",
        "normal": {"min": None, "max": 10},
        "critical_high": 50,
        "description": "胆汁排泄功能标志，升高提示胆汁淤积或肝脏病变"
    },
    "CHE": {
        "name": "胆碱酯酶 (Cholinesterase)",
        "unit": "kU/L",
        "normal": {"min": 3.930, "max": 12.000},
        "critical_low": 2.000,
        "description": "肝脏合成功能标志，降低与肝脏损伤或有机磷中毒相关"
    },

    # ===== 肌酸激酶同工体 =====
    "CK": {
        "name": "肌酸激酶 (Creatine Kinase)",
        "unit": "U/L",
        "male": {"min": None, "max": 171},
        "female": {"min": None, "max": 145},
        "critical_high": 500,
        "description": "肌肉和心脏损伤标志物，升高提示肌肉炎症或心肌梗死"
    },
    "LDH": {
        "name": "乳酸脱氢酶 (Lactate Dehydrogenase)",
        "unit": "U/L",
        "normal": {"min": None, "max": 250},
        "critical_high": 500,
        "description": "细胞坏死标志物，升高与溶血、肌肉损伤或多种器官病变相关"
    },
    "α-HBD": {
        "name": "α-羟基丁酸脱氢酶 (α-Hydroxybutyrate Dehydrogenase)",
        "unit": "U/L",
        "normal": {"min": None, "max": 175},
        "description": "心肌梗死早期标志物，持续时间长于肌酸激酶同工体"
    },

    # ===== 肾功能扩展 =====
    "UREA": {
        "name": "尿素 (Urea)",
        "unit": "mmol/L",
        "pediatric": {"min": 1.8, "max": 6.4},
        "child": {"min": 1.8, "max": 6.4},
        "infant": {"min": 1.8, "max": 6.4},
        "adolescent": {"min": 2.5, "max": 7.1},
        "teen": {"min": 2.5, "max": 7.1},
        "adult": {"min": 2.5, "max": 8.3},
        "elderly": {"min": 3.0, "max": 9.0},
        "geriatric": {"min": 3.0, "max": 9.0},
        "senior": {"min": 3.0, "max": 9.0},
        "normal": {"min": 2.5, "max": 8.3},
        "critical_high": 15,
        "description": "肾脏清除功能标志，同BUN的另一种表达方式，升高提示肾脏病变或脱水"
    },
    "CysC": {
        "name": "胱抑素C (Cystatin C)",
        "unit": "mg/L",
        "pediatric": {"min": 0.52, "max": 1.03},
        "child": {"min": 0.52, "max": 1.03},
        "infant": {"min": 0.52, "max": 1.10},
        "adolescent": {"min": 0.52, "max": 1.03},
        "teen": {"min": 0.52, "max": 1.03},
        "adult": {"min": 0.52, "max": 1.03},
        "elderly": {"min": 0.60, "max": 1.20},
        "geriatric": {"min": 0.60, "max": 1.20},
        "senior": {"min": 0.60, "max": 1.20},
        "normal": {"min": 0.52, "max": 1.03},
        "description": "肾功能敏感指标，不受肌肉质量和年龄影响，比肌酐更准确"
    },

    # ===== 酸碱和气体 =====
    "CO2": {
        "name": "二氧化碳 (Carbon Dioxide)",
        "unit": "mmol/L",
        "pediatric": {"min": 20, "max": 28},
        "child": {"min": 20, "max": 28},
        "infant": {"min": 18, "max": 28},
        "adolescent": {"min": 22, "max": 29},
        "teen": {"min": 22, "max": 29},
        "adult": {"min": 22, "max": 29},
        "elderly": {"min": 22, "max": 30},
        "geriatric": {"min": 22, "max": 30},
        "senior": {"min": 22, "max": 30},
        "normal": {"min": 22, "max": 29},
        "description": "酸碱平衡标志物，降低提示代谢性酸中毒，升高提示代谢性碱中毒"
    }
}


def get_reference_range(indicator_code: str) -> dict:
    """获取指定指标的参考范围"""
    return REFERENCE_RANGES.get(indicator_code, {})


def format_reference_text(indicator_code: str) -> str:
    """格式化参考范围为可读文本"""
    ref = get_reference_range(indicator_code)
    if not ref:
        return f"指标 {indicator_code} 参考范围未找到"
    
    text = f"## {ref.get('name', indicator_code)} ({indicator_code})\n"
    text += f"**单位**：{ref.get('unit', '未知')}\n\n"
    
    if "male" in ref and "female" in ref:
        male = ref["male"]
        female = ref["female"]
        text += f"**正常范围**：\n"
        text += f"- 男性：{male.get('min', '-')} - {male.get('max', '-')}\n"
        text += f"- 女性：{female.get('min', '-')} - {female.get('max', '-')}\n"
    elif "normal" in ref:
        normal = ref["normal"]
        text += f"**正常范围**：{normal.get('min', '-')} - {normal.get('max', '-')}\n"
    
    if "critical_low" in ref or "critical_high" in ref:
        text += "\n**危急值**：\n"
        if "critical_low" in ref:
            text += f"- 低于：{ref['critical_low']}\n"
        if "critical_high" in ref:
            text += f"- 高于：{ref['critical_high']}\n"
    
    if "description" in ref:
        text += f"\n**临床意义**：{ref['description']}\n"
    
    return text


if __name__ == "__main__":
    # 测试
    print(format_reference_text("Cr"))
    print("\n" + "="*60 + "\n")
    print(format_reference_text("WBC"))
