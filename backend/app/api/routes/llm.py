"""
LLM 路由

提供 /llm/chat 端点，单次 LLM 对话。
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["LLM"])


class ChatRequest(BaseModel):
    message: str
    user_id: str
    session_id: str


@router.post("/chat")
async def llm_chat(request: ChatRequest):
    """单次 LLM 对话"""
    try:
        from llm.chat_model import ChatModel
        model = ChatModel()
        messages = [{"role": "user", "content": request.message}]
        response = model.invoke(messages)
        return {
            "response": response.choices[0].message.content,
            "model": model.model,
        }
    except Exception as e:
        logger.error("LLM chat failed: %s", e, exc_info=True)
        return {"error": str(e)}
