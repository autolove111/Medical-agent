import logging
import re
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterator, Optional, List, Tuple
from urllib.parse import urlsplit, urlunsplit, quote

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from core.config import settings

# 确保导入路径正确，使用绝对路径
try:
    from knowledge.rag import retrieve_medical_knowledge
    from tools import query_user_medical_history, set_current_user_id
    from knowledge.medical_knowledge import create_knowledge_base, PatientHistoryEnhancer
    from vision.vision_analyzer import analyze_medical_image
except ImportError as e:
    logging.error(f"核心模块导入失败: {e}")
    # 提供 Mock 函数防止程序崩溃
    retrieve_medical_knowledge = lambda x: ("无知识库检索结果", [])
    query_user_medical_history = lambda x: "未知病史"
    set_current_user_id = lambda x: None
    create_knowledge_base = lambda: None
    PatientHistoryEnhancer = lambda x: None
    analyze_medical_image = lambda x: "【OCR 不可用】视觉识别模块未加载"

logger = logging.getLogger(__name__)

_sync_llm = None
_streaming_llm = None

# 正则：匹配元数据
META_PATTERN = re.compile(r"\[META\|([^\]]+)\]")

SYSTEM_PROMPT = """# Role
你是一款基于双路图注意力机制 (Dual-GAT) 增强的医学检验智能体 —— MedLabAgent。
你拥有专业的循证医学知识，并严格遵循 ReAct (Reasoning and Acting) 框架进行逻辑推导和工具调用。

# Context (System Inputs)
【患者档案】: {patient_info}
【化验异常清单】: {abnormal_labs}

🧠 【GAT-1 疾病候选预测】 (先验概率参考): 
{gat_disease_priors}

🛠️ 【GAT-2 动作路由预测】 (工具调用参考): 
{gat_tool_priors}

# Execution Rules
请严格遵循以下规则执行诊断与回复：
<rule_1: First_Line_Diagnosis>
最终交付给用户的回答，第一行必须严格按照以下格式：
主诊断：[疾病名称] 次诊断：[疾病名称]（置信度：[0-100]%）
</rule_1>

<rule_2: Priority_and_Caution>
1. 优先验证 GAT-1 提供的高置信度疾病候选，切勿盲目发散。
2. 遇到疑难点时，优先调用 GAT-2 推荐的科室工具 ({tool_names})。
3. 回复末尾必须包含免责声明：“⚠️ 以上建议由 AI 基于检验数据生成，仅供临床参考，请以执业医师最终诊断为准。”
</rule_2>

<rule_3: Metadata_Output>
1. 要列举出数据对诊断进行讲解，但不能过度解读或夸大数据的意义。
2. 回答的最后一行必须严格输出状态元数据（不要有任何多余字符，注意小写和布尔值）：
[META|medical:true/false|disease:string/None|allergy:string/None]
</rule_3>

# Available Tools
你可以使用以下工具：
{tools}

# ReAct Format Instructions
你必须按照以下格式进行思考和行动：
Question: 需要解答的医学检验问题或用户的输入。
Thought: 思考你需要做什么。分析当前的异常指标，结合 GAT-1 的预测，决定是否需要调用工具。
Action: 必须是 [{tool_names}] 中的一个。参考 GAT-2 的推荐。
Action Input: 工具的输入参数。
Observation: 工具返回的结果。
... (Thought/Action/Action Input/Observation 可以重复多次)
Thought: 我现在已经掌握了足够的信息，可以给出最终的结构化诊断报告。
Final Answer: 最终给用户的专业回复（必须满足第一行诊断、免责声明和最后一行 META 的要求）。

# Begin!
Question: {input}
Thought: {agent_scratchpad}"""


_GRAPH_INDICATOR_ALIAS = {
    # ========== 血细胞计数 ==========
    "wbc": "WBC",
    "rbc": "RBC",
    "hemoglobin": "Hb",
    "hematocrit": "HCT",
    "mcv": "MCV",
    "mch": "MCH",
    "mchc": "MCHC",
    "plt": "PLT",
    # ========== 白细胞分类 ==========
    "ne": "NE",
    "ly": "LY",
    "mo": "MO",
    "eo": "EO",
    "ba": "BA",
    # ========== 红细胞分类 ==========
    "nrbc": "NRBC",
    "rdw": "RDW",
    # ========== 血小板相关 ==========
    "mpv": "MPV",
    "pct": "PCT",
    "pdw": "PDW",
    # ========== 生化指标：代谢 ==========
    "glucose": "GLU",
    "bun": "BUN",
    "creatinine": "Cr",
    "uric_acid": "UA",
    # ========== 生化指标：肝功能 ==========
    "alt": "ALT",
    "ast": "AST",
    "alp": "ALP",
    "ggt": "GGT",
    "total_bilirubin": "TBIL",
    "direct_bilirubin": "DBIL",
    # ========== 生化指标：电解质 ==========
    "sodium": "Na",
    "potassium": "K",
    "chloride": "Cl",
    "calcium": "Ca",
    "phosphorus": "P",
    "magnesium": "Mg",
    # ========== 生化指标：脂质 ==========
    "cholesterol": "CHO",
    "triglyceride": "TG",
    # ========== 蛋白质代谢 ==========
    "total_protein": "TP",
    "albumin": "ALB",
    "globulin": "GLO",
    "a_g_ratio": "A/G",
    # ========== 胆汁和肝脏 ==========
    "total_bile_acid": "TBA",
    "cholinesterase": "CHE",
    # ========== 心肌酶 ==========
    "creatine_kinase": "CK",
    "ldh": "LDH",
    "a_hbd": "α-HBD",
    # ========== 肾功能扩展 ==========
    "urea": "UREA",
    "cystatin_c": "CysC",
    # ========== 酸碱平衡 ==========
    "co2": "CO2",
    # ========== 原有的保留项（保持兼容） ==========
    "egfr": "eGFR",
    "p": "PO4",
    "tbil": "TBIL",
    "dbil": "DBIL",
    "hba1c": "HbA1c",
}


def _normalize_labs_for_graph(lab_results: Dict[str, float]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for raw_key, raw_value in (lab_results or {}).items():
        key = str(raw_key).strip()
        mapped = _GRAPH_INDICATOR_ALIAS.get(key.lower(), key)
        normalized[mapped] = raw_value
    return normalized


def _run_graph_inference_iterative(lab_results: Dict[str, float], max_iters: int = 6) -> str:
    """两轮图推理：首轮全量指标，次轮基于关键指标聚焦，模拟 ReAct 迭代更新。"""
    if not lab_results:
        return ""

    # 关键：在同进程内直接调用图推理，避免对自身 HTTP 回调导致超时。
    from graph.graph_inference import get_graph_models, _generate_prompt_injection

    current_labs = _normalize_labs_for_graph(lab_results)
    injections: List[str] = []

    indicator_gat, expert_gat = get_graph_models()
    graph_nodes = set(getattr(indicator_gat, "graph", {}).nodes()) if getattr(indicator_gat, "graph", None) is not None else set()
    logger.info("GAT输入标准化后指标: %s", dict(sorted(current_labs.items())))
    logger.info("GAT图节点匹配统计: input=%d matched=%d", len(current_labs), len([k for k in current_labs if k in graph_nodes]) if graph_nodes else len(current_labs))

    for idx in range(max_iters):
        if graph_nodes:
            filtered_labs = {k: v for k, v in current_labs.items() if k in graph_nodes}
        else:
            filtered_labs = dict(current_labs)

        if not filtered_labs:
            logger.info("Graph iteration %d skipped: no indicators match graph nodes", idx + 1)
            break

        indicator_result = indicator_gat.forward(filtered_labs)
        key_indicators = indicator_result.get("key_indicators", [])
        indicator_weights = indicator_result.get("weights", {})
        expert_result = expert_gat.forward(key_indicators, indicator_weights)

        prompt_injection = _generate_prompt_injection(
            key_indicators,
            indicator_result,
            expert_result.get("recommended_agents", []),
            expert_result,
        )
        if prompt_injection:
            injections.append(f"[图推理第{idx + 1}轮]\n{prompt_injection}")

        # 第2轮聚焦关键指标，模拟 ReAct 在观察后收缩搜索空间。
        if idx + 1 < max_iters:
            focused = {k: v for k, v in filtered_labs.items() if k in key_indicators}
            if focused and len(focused) < len(current_labs):
                current_labs = focused
            else:
                break

    return "\n\n".join(injections)

def get_llm(streaming: bool = False):
    global _sync_llm, _streaming_llm
    cached = _streaming_llm if streaming else _sync_llm
    if cached is not None:
        return cached

    # Mock 模式：返回模拟 LLM（用于演示或无 API key 的情况）
    if settings.USE_MOCK_LLM or not settings.DASHSCOPE_API_KEY or settings.DASHSCOPE_API_KEY.strip() in ("sk-", ""):
        logger.info("⚠️ 使用 Mock LLM 模式（无需真实 API key）")
        from langchain_community.llms.fake import FakeListLLM
        mock_llm = FakeListLLM(
            responses=[
                "根据您上传的化验单，我已识别到以下关键指标：\n\n"
                "【血象检查】\n"
                "- WBC（白细胞）：7.2 × 10³/μL（正常范围 4.5-11.0）\n"
                "- 状态：正常\n\n"
                "【肝功能】\n"
                "- ALT：28 U/L（正常范围 <40）\n"
                "- AST：32 U/L（正常范围 <40）\n"
                "- 状态：正常\n\n"
                "【肾功能】\n"
                "- 肌酐：0.85 mg/dL（正常范围 0.7-1.3）\n"
                "- 尿素氮：16 mg/dL（正常范围 7-20）\n"
                "- 状态：正常\n\n"
                "【综合分析】\n"
                "您的这次检验结果整体正常，主要指标均在参考范围内。建议：\n"
                "1. 保持良好的生活习惯和饮食均衡\n"
                "2. 定期体检监测\n"
                "3. 如有任何不适症状，及时就医\n\n"
                "⚠️ 本分析仅供参考，请以临床医生诊断为准。\n\n"
                "[META|医疗:是|疾病:无|过敏:无]"
            ]
        )
        return mock_llm

    llm = ChatOpenAI(
        model=settings.DASHSCOPE_MODEL,
        openai_api_key=settings.DASHSCOPE_API_KEY,
        openai_api_base=settings.DASHSCOPE_BASE_URL,
        temperature=settings.TEMPERATURE,
        max_tokens=settings.MAX_TOKENS,
        streaming=streaming,
    )
    if streaming:
        _streaming_llm = llm
    else:
        _sync_llm = llm
    return llm

def extract_metadata(text: str) -> Tuple[str, Dict]:
    metadata = {
        "isMedical": False,
        "diseases": "",
        "drugAllergies": "",
    }
    match = META_PATTERN.search(text)
    if not match:
        return text, metadata

    parsed_fields: Dict[str, str] = {}
    try:
        for field in match.group(1).split("|"):
            if ":" not in field:
                continue
            key, value = field.split(":", 1)
            parsed_fields[key.strip()] = value.strip()

        metadata["isMedical"] = (parsed_fields.get("医疗", "") == "是")
        disease = parsed_fields.get("疾病", "")
        allergy = parsed_fields.get("过敏", "")
        metadata["diseases"] = "" if disease == "无" else disease
        metadata["drugAllergies"] = "" if allergy == "无" else allergy
    except Exception as e:
        logger.warning(f"解析元数据失败: {e}")

    cleaned = META_PATTERN.sub("", text).rstrip()
    return cleaned, metadata

class MedicalAgent:
    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        try:
            self.kb = create_knowledge_base()
            if self.kb:
                self.enhancer = PatientHistoryEnhancer(self.kb)
            else:
                self.enhancer = None
        except Exception as e:
            logger.error(f"知识库初始化失败: {e}")
            self.kb = None
            self.enhancer = None

    def _build_messages(self, query: str, user_context: Optional[str] = None, lab_results: Optional[Dict] = None):
        set_current_user_id(self.user_id)
        logger.info("🔵 _build_messages 进入，user_id=%s", self.user_id)

        lab_results = lab_results or {}
        
        # 【关键】先提取和清理 URL，确保后续所有查询都不含 URL
        ocr_text = ""
        query_for_model = query
        image_url_raw = self._extract_image_url(query)
        image_url = self._normalize_image_url(image_url_raw) if image_url_raw else None
        logger.info("1️⃣ 梳理 URL: image_url=%s (存在=%s)", image_url, bool(image_url))
        
        if image_url:
            # 不把原始 URL 交给模型，也不传给 RAG 检索
            query_for_model = self._remove_image_url(query, image_url_raw)
            logger.info("2️⃣ 清理 URL 后的 query: %s", query_for_model[:100])
        
        # 使用清理后的 query 作为 RAG 查询基础（不含 URL）
        rag_query = query_for_model
        if lab_results:
            rag_query = f"{query_for_model}\n关键检验指标: {', '.join(lab_results.keys())}"
        
        if image_url:
            # 【关键】始终主动调用 OCR 服务，利用 Redis 缓存优化性能
            try:
                logger.info("3️⃣ 【异步预热利用】检测到图片 URL，主动调用 OCR 服务（会优先返回 Redis 缓存）: %s", image_url)
                try:
                    from vision.vision_analyzer import analyze_medical_image_comprehensive
                    logger.info("   - 导入 analyze_medical_image_comprehensive ✓")
                    ocr_text, extracted_labs = analyze_medical_image_comprehensive(image_url)
                    logger.info("4️⃣ ✓ OCR 完成：文本长度=%s，提取指标=%s", len(ocr_text) if ocr_text else 0, len(extracted_labs) if extracted_labs else 0)
                except ImportError as ie:
                    logger.warning("   - 导入失败，使用回退方案: %s", ie)
                    from vision.vision_analyzer import analyze_medical_image, extract_patient_labs_from_ocr
                    ocr_text = analyze_medical_image(image_url)
                    extracted_labs = extract_patient_labs_from_ocr(image_url)
                    logger.info("4️⃣ ✓ OCR 完成（回退模式）：文本长度=%s，提取指标=%s", len(ocr_text) if ocr_text else 0, len(extracted_labs) if extracted_labs else 0)
                
                rag_query = f"{rag_query}\n{ocr_text}"
                if extracted_labs:
                    logger.info("  → 将 OCR 提取的化验指标合并到 lab_results")
                    lab_results.update(extracted_labs)
            except Exception as e:
                logger.error("❌ OCR 调用失败: %s", e, exc_info=True)
                ocr_text = "【OCR 识别失败，请手动提供化验单关键数值】"
        
        # 检索 RAG
        rag_result, sources = retrieve_medical_knowledge(rag_query)
        
        # 获取病史
        history_text = user_context or query_user_medical_history(self.user_id)
        
        # 增强病史总结
        if lab_results and self.enhancer:
            try:
                history_text = self.enhancer.enhance_medical_summary(history_text, lab_results)
            except Exception as e:
                logger.warning(f"增强病史失败: {e}")

        lab_results_text = "无结构化检验值"
        if lab_results:
            lines = []
            for key, value in lab_results.items():
                lines.append(f"- {key}: {value}")
            lab_results_text = "\n".join(lines)

        ocr_section = "无 OCR 文本"
        if ocr_text:
            ocr_section = ocr_text

        missing_info_followup = ""
        if not lab_results:
            required = self._infer_required_indicators(query_for_model)
            if required:
                missing_info_followup = (
                    "当前无法完成可靠诊断：尚未提取到结构化化验指标。\n"
                    "请先补充以下关键检查结果后我再进行多轮科室协作分析：\n"
                    + "\n".join([f"- {item}" for item in required])
                )
                logger.info("触发主动追问缺失指标: %s", required)

        react_trace_section = ""
        if lab_results:
            react_trace_section = self._run_hierarchical_react_loop(query_for_model, lab_results)
        else:
            logger.warning("跳过多轮 ReAct 协作：未提取到结构化检验指标（lab_results=0）")

        # 【第六步】如果有结构化检验值，进行 GAT 图推理
        graph_prompt_injection = ""
        if lab_results:
            try:
                logger.info("结构化检验值详情: %s", dict(sorted(lab_results.items())))
                logger.info("进入第六步：使用 GAT 图推理分析 %d 个检验指标", len(lab_results))
                graph_prompt_injection = _run_graph_inference_iterative(lab_results=lab_results)
                if graph_prompt_injection:
                    logger.info("GAT 图推理完成（两轮迭代），已获取 prompt_injection")
            except Exception as e:
                logger.warning("GAT 图推理失败（降级处理）: %s", e)
                graph_prompt_injection = ""
        else:
            logger.warning("跳过 GAT 图推理：未提取到结构化检验指标（lab_results=0）")

        # 移除冗余的 ocr_guidance 判断（已无需要）
        # 因为现在始终调用 OCR，所以必然有文本或失败提示
        user_id_info = self.user_id or "anonymous"

        # 核心提示词模板（包含 GAT 图推理注入、OCR 结果、结构化检验值）
        graph_section = f"\n【GAT 图推理指导】\n{graph_prompt_injection}" if graph_prompt_injection else ""
        react_section = f"\n【ReAct 多轮协作轨迹】\n{react_trace_section}" if react_trace_section else ""
        prompt = f"""当前用户ID：{user_id_info}
【化验单 OCR 识别结果】：\n{ocr_section}
【知识库检索结果】：{rag_result or "无相关知识库结果"}
【用户病史与过敏信息】：{history_text or "无用户档案"}
    【结构化检验值】\n{lab_results_text}{graph_section}{react_section}
【用户问题】：{query_for_model}

请结合以上信息，给出结构化医学分析。建议包含关键指标判断、原因分析、风险关注及建议。
回答第一行必须是“主诊断：xxx（置信度：xx%）”，再展开详细分析。
最后单独输出一行 META 标记。"""

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        return messages, sources, {
            "missing_info_followup": missing_info_followup,
            "lab_count": len(lab_results),
        }

    def _infer_required_indicators(self, query: str) -> List[str]:
        q = (query or "").lower()
        if any(k in q for k in ["糖", "糖尿病", "血糖", "glucose", "hba1c"]):
            return ["空腹血糖(GLU)", "糖化血红蛋白(HbA1c)", "餐后2小时血糖", "尿酮体"]
        if any(k in q for k in ["肾", "肾脏", "肾功能", "creatinine", "egfr"]):
            return ["肌酐(Cr)", "尿素氮(BUN)", "eGFR", "血钾(K)", "尿常规"]
        if any(k in q for k in ["肝", "肝炎", "alt", "ast", "胆红素"]):
            return ["ALT", "AST", "总胆红素", "直接胆红素", "ALP", "GGT"]
        return ["至少3项核心化验指标（如Cr/BUN/eGFR或GLU/HbA1c）"]

    def _run_coro_blocking(self, coro):
        """在任意上下文中安全执行 async 协程并阻塞等待结果。"""
        try:
            asyncio.get_running_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(lambda: asyncio.run(coro)).result()
        except RuntimeError:
            return asyncio.run(coro)

    def _run_hierarchical_react_loop(self, query: str, lab_results: Dict[str, float], max_rounds: int = 5) -> str:
        """主Agent多轮 ReAct 协作：思考(选路)→行动(并联科室Agent)→观察(冲突/置信度)→迭代。"""
        try:
            from task.hierarchical_main_agent import HierarchicalMedicalAgent

            h_agent = HierarchicalMedicalAgent(user_id=self.user_id)
            patient_profile = self._extract_patient_profile(query)
            clinical_prior = self._extract_clinical_prior(query)
            result = self._run_coro_blocking(
                h_agent.analyze_lab_results(
                    lab_results,
                    max_rounds=max_rounds,
                    patient_profile=patient_profile,
                    clinical_prior=clinical_prior,
                )
            )
            rounds: List[Dict] = result.get("react_rounds", [])
            if not rounds:
                rounds = [{
                    "round": 1,
                    "selected_departments": list((result.get("dept_responses") or {}).keys()),
                    "action_reason": "单轮回退",
                    "consensus": {
                        "primary_diagnosis": result.get("primary_diagnosis", "未确定"),
                        "confidence": float(result.get("consensus_confidence", 0.0) or 0.0),
                        "conflict_level": result.get("conflict_level", "unknown"),
                    },
                }]

            lines: List[str] = []
            for r in rounds:
                i = int(r.get("round", 1))
                c = r.get("consensus", {})
                diag = c.get("primary_diagnosis", "未确定")
                conf = float(c.get("confidence", 0.0) or 0.0)
                conflict = c.get("conflict_level", "unknown")
                selected = r.get("selected_departments", [])
                action_reason = r.get("action_reason", "")
                lines.append(
                    f"第{i}轮 Thought: 围绕患者最可能患病进行收敛，减少关键鉴别诊断不确定性；"
                    f"Action: 本轮调用科室={selected}（原因: {action_reason}）；"
                    f"Observation: 主诊断={diag} 置信度={conf:.2f} 冲突={conflict}；"
                    f"Reasoning: 根据多科室回传证据做共识推断与权重迭代"
                )

            lines.append(f"TaskAssignments: {result.get('task_assignments', {})}")
            lines.append(f"DeptHandoffs: {result.get('dept_handoffs', {})}")

            final_weights = h_agent.weight_updater.get_weights()
            lines.append(f"权重迭代结果: {final_weights}")
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("主Agent ReAct 循环执行失败，降级单轮推理: %s", exc)
            return ""

    def _extract_patient_profile(self, text: str) -> Dict[str, float]:
        """从查询文本提取基础画像（年龄优先）。"""
        q = text or ""
        age_years = None

        m_year = re.search(r"(\d{1,2})\s*岁", q)
        if m_year:
            age_years = float(m_year.group(1))
        else:
            m_month = re.search(r"(\d{1,2})\s*月", q)
            if m_month:
                age_years = round(float(m_month.group(1)) / 12.0, 2)

        profile: Dict[str, float] = {}
        if age_years is not None:
            profile["age_years"] = age_years
        if any(k in q for k in ["患儿", "婴儿", "幼儿", "儿童"]):
            profile["is_pediatric"] = 1.0
        return profile

    def _extract_clinical_prior(self, text: str) -> str:
        """提取临床先验（如化验单中的临床诊断字段）。"""
        q = text or ""
        m = re.search(r"(?:临床)?诊断[:：]\s*([^\n，。；]{2,40})", q)
        if m:
            return m.group(1).strip()
        return ""

    def _extract_image_url(self, text: str) -> Optional[str]:
        # 优先抓取可包含空格的图片URL（常见于原始文件名未编码）
        file_view_candidates = re.findall(
            r"https?://[^\]\)\}，。；；]+?/api/v1/file/view/[^\]\)\}，。；；]+?\.(?:png|jpg|jpeg|gif|webp|bmp)(?:\?[^\]\)\}，。；；]*)?",
            text,
            flags=re.IGNORECASE,
        )
        if file_view_candidates:
            return self._trim_url_punctuation(file_view_candidates[0])

        # 兜底抓取通用 URL（无空格场景）
        candidates = re.findall(r"https?://[^\s\]\)\}，。；；]+", text, flags=re.IGNORECASE)
        if not candidates:
            return None

        cleaned = [self._trim_url_punctuation(url) for url in candidates if url]
        for url in cleaned:
            if "/api/v1/file/view/" in url:
                return url
        for url in cleaned:
            if re.search(r"\.(png|jpg|jpeg|gif|webp|bmp)(?:\?.*)?$", url, re.IGNORECASE):
                return url
        return cleaned[0] if cleaned else None

    def _trim_url_punctuation(self, url: str) -> str:
        return url.rstrip("，。；;!！?)）]\"'”)】")

    def _normalize_image_url(self, url: str) -> str:
        """规范化URL，保留结构并编码路径中的空格/中文，避免OCR下载404。"""
        try:
            parsed = urlsplit(url)
            encoded_path = quote(parsed.path, safe="/%")
            encoded_query = quote(parsed.query, safe="=&%")
            normalized = urlunsplit((parsed.scheme, parsed.netloc, encoded_path, encoded_query, parsed.fragment))
            if normalized != url:
                logger.info("URL已规范化: %s -> %s", url, normalized)
            return normalized
        except Exception as exc:
            logger.warning("URL规范化失败，使用原URL: %s", exc)
            return url

    def _remove_image_url(self, text: str, image_url: str) -> str:
        compact = text.replace(image_url, "").strip()
        return compact or "请根据已识别的化验单数据进行分析"

    def process_query(self, query: str, user_context: Optional[str] = None, lab_results: Optional[Dict] = None):
        try:
            messages, sources, analysis_ctx = self._build_messages(query, user_context, lab_results)
            followup = (analysis_ctx or {}).get("missing_info_followup", "")
            if followup:
                return followup, []
            response = get_llm(streaming=False).invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            cleaned, _ = extract_metadata(content)
            return cleaned, sources
        except Exception as exc:
            logger.error("Query failed: %s", exc)
            return f"处理异常: {exc}", []

    def stream_query(self, query: str, user_context: Optional[str] = None, lab_results: Optional[Dict] = None) -> Iterator[Dict]:
        try:
            logger.info("🟢 stream_query 开始，query 长度=%d", len(query))
            messages, sources, analysis_ctx = self._build_messages(query, user_context, lab_results)
            followup = (analysis_ctx or {}).get("missing_info_followup", "")
            if followup:
                yield {"type": "delta", "content": followup}
                yield {
                    "type": "meta",
                    "metadata": {"isMedical": True, "diseases": "", "drugAllergies": ""},
                    "sources": [],
                }
                return
            logger.info("🟢 _build_messages 完成，开始 LLM 流式调用")
            full_text = ""
            for chunk in get_llm(streaming=True).stream(messages):
                text = chunk.content if hasattr(chunk, "content") else ""
                if not text: continue
                full_text += text
                yield {"type": "delta", "content": text}

            _, metadata = extract_metadata(full_text)
            formatted_sources = [
                {"content": s.page_content[:200], "metadata": getattr(s, "metadata", {})} 
                for s in sources
            ]
            yield {
                "type": "meta",
                "metadata": metadata,
                "sources": formatted_sources,
            }
        except Exception as exc:
            logger.error(f"❌ 流式输出异常: {exc}", exc_info=True)
            yield {"type": "error", "error": str(exc)}

def create_medical_agent(user_id: Optional[str] = None) -> MedicalAgent:
    return MedicalAgent(user_id)