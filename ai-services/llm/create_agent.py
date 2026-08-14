"""
create_agent
~~~~~~~~~~~~
自研 Agent 创建模块。

Agent 绑定：记忆系统 + 工具注册表。
chat() 只做单次推理，工具调用循环由 loop 模块处理。
"""

import json
import logging
from typing import Iterable

from llm.chat_model import ChatModel, Chunk, JudgeModel, ChatResponse
from memory import MemorySystem
from tools import get_registry
from loop.prompt import SystemPromptBuilder


logger = logging.getLogger(__name__)


def _safety_check(reply: str) -> str:
    try:
        from app.safety.output_guard import get_output_guard
        guard = get_output_guard()
        report = guard.sanitize(reply)
        safe = guard.inject_disclaimer(report.sanitized)
        if report.blocked:
            logger.warning("Output blocked: %s", report.blocking_rules)
        return safe
    except Exception as e:
        logger.warning("Safety check failed: %s", e)
        return reply


# ============================================================
# LabAgent
# ============================================================

class LabAgent:
    """
    医疗检验 Agent — 绑定记忆系统 + 工具注册表

    使用方式：
        agent = LabAgent(chat_model, memory, tool_registry)
        reply = agent.chat("肌酐偏高怎么办")           # 单次推理
        reply = agent.chat_with_tools("肌酐偏高怎么办") # 带工具调用循环
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        def_prompt: str,
        format_prompt: str,
    ):

        self.memory = MemorySystem(user_id, session_id)
        self.memory.load_snapshot()  # 创建时加载快照，后续直接用
        self.chat_model = ChatModel()
        self.system_prompt = SystemPromptBuilder()
        self.tool_registry = get_registry()
        self.def_prompt = def_prompt
        self.format_prompt = format_prompt
        self.judge_model = JudgeModel()

        # 注册到监控面板
        try:
            from Debugging.short_memory_watching import register_memory
            register_memory(user_id, session_id, self.memory)
        except Exception:
            pass  # 监控服务未启动时忽略

    
    # ----------------------------------------------------------
    # 写入记忆能力
    # ----------------------------------------------------------
    def memory_judge(self, content: str) -> str:
        """用 7B 模型做三维打分 + 画像提取"""
        prompt = [
            {"role": "system", "content": (
                "对用户消息完成两个任务，严格按JSON格式输出：\n\n"
                "## 任务1：打分（0.0-1.0）\n"
                "- medical：医疗信息价值（指标/症状/诊断/用药）\n"
                "- experience：经验总结价值（效果反馈/行为改变）\n"
                "- profile：画像更新价值（习惯/家族史/关注点）\n\n"
                "## 任务2：画像提取\n"
                "如果消息包含以下字段的信息就填写，没有就留空：\n"
                "allergies, chronic_diseases, medications, family_history, lifestyle\n\n"
                "## 输出格式（每行一个字段，没有就留空）\n"
                "medical: 分数\n"
                "experience: 分数\n"
                "profile: 分数\n"
                "allergies: 值1,值2\n"
                "chronic_diseases: 值1,值2\n"
                "medications: 值1,值2\n"
                "family_history: 关系:疾病,关系:疾病\n"
                "lifestyle: 项目:内容,项目:内容\n\n"
                "## 示例\n"
                "输入：我爸有高血压，我每天熬夜到两点\n"
                "输出：\n"
                "medical: 0.1\n"
                "experience: 0.0\n"
                "profile: 0.9\n"
                "allergies: \n"
                "chronic_diseases: \n"
                "medications: \n"
                "family_history: 父亲:高血压\n"
                "lifestyle: 作息:熬夜到两点"
            )},
            {"role": "user", "content": content}
        ]

        try:
            response = self.judge_model.invoke(prompt)
            raw = response.choices[0].message.content

            # 解析填表格式
            scores = {"medical": 0.0, "experience": 0.0, "profile": 0.0}
            profile_data = {}

            for line in raw.strip().splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()

                if key in scores:
                    try:
                        scores[key] = round(float(value), 2)
                    except ValueError:
                        pass
                elif key in ("allergies", "chronic_diseases", "medications"):
                    if value:
                        profile_data[key] = [v.strip() for v in value.split(",") if v.strip()]
                elif key in ("family_history", "lifestyle"):
                    if value:
                        pairs = {}
                        for item in value.split(","):
                            if ":" in item:
                                k, _, v = item.partition(":")
                                pairs[k.strip()] = v.strip()
                        if pairs:
                            profile_data[key] = pairs
                elif key in ("name", "gender", "blood_type") and value:
                    profile_data[key] = value
                elif key in ("age", "height", "weight") and value:
                    try:
                        profile_data[key] = float(value) if "." in value else int(value)
                    except ValueError:
                        pass

            result = {
                "content": content,
                "medical": scores["medical"],
                "experience": scores["experience"],
                "profile": scores["profile"],
                "profile_data": profile_data,
            }
            return json.dumps(result, ensure_ascii=False)

        except Exception as e:
            logger.warning("memory_judge failed: %s", e)

        return json.dumps({
            "content": content, "medical": 0.0, "experience": 0.0,
            "profile": 0.0, "profile_data": {}
        }, ensure_ascii=False)

    def write_user_message_to_memory(self, user_input: str) -> None:
        """将用户消息写入记忆、打分、提取画像"""
        # 1. 打分 + 提取
        result = self.memory_judge(user_input)
        data = json.loads(result)

        logger.debug("memory_judge: medical=%s experience=%s profile=%s", data['medical'], data['experience'], data['profile'])
        logger.debug("profile_data: %s", data.get('profile_data', {}))

        # 2. 写入对话 + 权重
        self.memory.on_user_message(data["content"], {
            "medical": data["medical"],
            "experience": data["experience"],
            "profile": data["profile"],
        })

        # 3. 更新画像
        if data["profile"] > 0.3 and data.get("profile_data"):
            logger.debug("profile.update: %s", data['profile_data'])
            self.memory.profile.update(data["profile_data"])

    def write_assistant_message_to_memory(self, content: str) -> None:
        """将助手回复写入记忆、打分、提取画像"""
        # 1. 打分 + 提取
        result = self.memory_judge(content)
        data = json.loads(result)

        # 2. 写入对话 + 权重
        self.memory.on_assistant_message(data["content"], {
            "medical": data["medical"],
            "experience": data["experience"],
            "profile": data["profile"],
        })

        # 3. 更新画像
        if data["profile"] > 0.3 and data.get("profile_data"):
            self.memory.profile.update(data["profile_data"])

    def write_tool_calls_to_memory(self, content: str, tool_calls: list[dict]) -> None:
        """将工具调用请求写入记忆"""
        self.memory.on_assistant_tool_calls(content=content, tool_calls=tool_calls)

    def write_tool_result_to_memory(self, tool_call_id: str, observation: str) -> None:
        """将工具执行结果写入记忆"""
        self.memory.on_tool_result(tool_call_id, observation)
    # ----------------------------------------------------------    
    # 获取短期记忆文本能力
    # ----------------------------------------------------------    
    def get_short_memory_text(self) -> list[dict]:
        """获取短期记忆消息列表"""
        return self.memory.get_short_memory_text()

    def get_summary(self) -> list[dict]:
        """获取会话摘要列表"""
        return self.memory.get_summary_text()

    def get_profile(self) -> str:
        """获取用户画像（可读文本）"""
        profile = self.memory.get_profile_text()
        if not profile:
            return ""
        parts = []
        if profile.get("name"):
            parts.append(f"姓名: {profile['name']}")
        if profile.get("age"):
            parts.append(f"年龄: {profile['age']}")
        if profile.get("gender"):
            parts.append(f"性别: {profile['gender']}")
        if profile.get("allergies"):
            parts.append(f"过敏史: {', '.join(profile['allergies'])}")
        if profile.get("chronic_diseases"):
            parts.append(f"慢性病: {', '.join(profile['chronic_diseases'])}")
        if profile.get("medications"):
            parts.append(f"当前用药: {', '.join(profile['medications'])}")
        if profile.get("family_history"):
            parts.append(f"家族史: {profile['family_history']}")
        if profile.get("lifestyle"):
            parts.append(f"生活方式: {profile['lifestyle']}")
        return "\n".join(parts)
    # ----------------------------------------------------------
    # 获取system prompt能力
    # ----------------------------------------------------------
    def get_system_prompt(self) -> list[dict]:
        """获取系统提示词，返回 FC 格式的 system message"""
        return self.system_prompt.get(self.def_prompt, self.format_prompt, self.get_summary(), self.get_profile())


    # ----------------------------------------------------------
    # Prompt 组装system_message+shoort memory能力，返回message列表
    # ----------------------------------------------------------
    def get_message_prompt(self) -> list[dict]:
        """组装系统提示词和短期记忆为最终 prompt，返回 FC 格式的 messages 列表"""
        messages = []
        system_message = self.get_system_prompt()
        if system_message:
            messages.extend(system_message)
        short_memory = self.get_short_memory_text()
        if short_memory:
            messages.extend(short_memory)
        return messages

    # ----------------------------------------------------------
    # 单次对话能力（不处理工具调用循环）
    # ----------------------------------------------------------
    def chat(self, message_prompt: list[dict]) -> ChatResponse:
        """单次推理，不处理工具调用循环"""

        logger.info("=" * 60)
        logger.info("PROMPT:\n%s", message_prompt)
        logger.info("=" * 60)

        tools_schemas = self.tool_registry.get_all_openai_schemas()
        response = self.chat_model.invoke(message_prompt, tools=tools_schemas)
        return response

    # ----------------------------------------------------------
    # 工具执行能力
    # --------------------------------------------------

    def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """通过注册表执行工具"""
        if tool_name not in self.tool_registry:
            return f"错误：未找到工具 '{tool_name}'"
        tool = self.tool_registry.get(tool_name)
        try:
            import asyncio
            result = asyncio.run(tool.execute(**arguments))
            return result.content
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return f"工具执行错误: {e}"

    # ----------------------------------------------------------
    # 流式对话
    # ----------------------------------------------------------

    def chat_stream(self, prompt: str) -> Iterable[Chunk]:
        """流式对话（不支持工具调用）"""

        full_reply = ""
        for chunk in self.chat_model.stream(prompt):
            full_reply += chunk.content
            yield chunk

        full_reply = _safety_check(full_reply)
        self.memory.on_assistant_message(full_reply)

    # ----------------------------------------------------------
    # 会话管理
    # ----------------------------------------------------------

    def end_session(self):
        """结束会话"""
        self.memory.end_session()
