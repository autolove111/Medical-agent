import logging
import re
import time
from typing import Dict, Iterator, Optional

from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from .config import settings
from rag import retrieve_medical_knowledge
from tools import query_user_medical_history, set_current_user_id
from medical_knowledge import create_knowledge_base, PatientHistoryEnhancer

logger = logging.getLogger(__name__)

_sync_llm = None
_streaming_llm = None

META_PATTERN = re.compile(r"\[META\|([^\]]+)\]")
META_START = "[META|"
KEY_MEDICAL = "\u533b\u7597"
KEY_DISEASE = "\u75be\u75c5"
KEY_ALLERGY = "\u8fc7\u654f"
VALUE_YES = "\u662f"
VALUE_NO = "\u5426"
VALUE_NONE = "\u65e0"

SYSTEM_PROMPT = """浣犳槸涓撲笟鐨勫尰瀛︽楠屾櫤鑳藉姪鎵?MedLabAgent銆?
璇烽伒寰互涓嬭鍒欙細
1. 缁欏嚭涓撲笟銆佽皑鎱庛€佺粨鏋勫寲鐨勫尰瀛﹀垎鏋愪笌寤鸿銆?2. 浼樺厛缁撳悎鐭ヨ瘑搴撴绱㈢粨鏋滃拰鐢ㄦ埛鐥呭彶淇℃伅鍥炵瓟銆?3. 濡傛秹鍙婅瘖鏂垨娌荤枟寤鸿锛屽繀椤绘彁閱掆€滀互涓婂缓璁粎渚涘弬鑰冿紝璇蜂互涓村簥鍖荤敓璇婃柇涓哄噯鈥濄€?4. 濡傛灉淇℃伅涓嶈冻锛岃鏄庣‘璇存槑涓嶇‘瀹氭€э紝涓嶈鑷嗘柇銆?5. 鍥炵瓟鏈€鍚庡繀椤昏拷鍔犱竴琛屽厓鏁版嵁锛屾牸寮忓浐瀹氫负锛?[META|鍖荤枟:鏄垨鍚鐤剧梾:鐤剧梾鍚嶇О鎴栨棤|杩囨晱:鑽墿鍚嶇О鎴栨棤]
"""


def get_llm(streaming: bool = False):
    global _sync_llm, _streaming_llm
    cached = _streaming_llm if streaming else _sync_llm
    if cached is not None:
        return cached

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


def extract_metadata(text: str) -> tuple[str, Dict[str, str]]:
    metadata = {
        "isMedical": False,
        "diseases": "",
        "drugAllergies": "",
    }
    match = META_PATTERN.search(text)
    if not match:
        return text, metadata

    parsed_fields: Dict[str, str] = {}
    for field in match.group(1).split("|"):
        if ":" not in field:
            continue
        key, value = field.split(":", 1)
        parsed_fields[key.strip()] = value.strip()

    metadata["isMedical"] = parsed_fields.get("鍖荤枟", "鍚?) == "鏄?
    disease = parsed_fields.get("鐤剧梾", "鏃?)
    allergy = parsed_fields.get("杩囨晱", "鏃?)
    metadata["diseases"] = "" if disease == "鏃? else disease
    metadata["drugAllergies"] = "" if allergy == "鏃? else allergy
    cleaned = META_PATTERN.sub("", text).rstrip()
    return cleaned, metadata


class MedicalAgent:
    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.kb = create_knowledge_base()
        self.enhancer = PatientHistoryEnhancer(self.kb)

    def _build_messages(self, query: str, user_context: Optional[str] = None, lab_results: Optional[Dict] = None) -> tuple[list, list]:
        set_current_user_id(self.user_id)
        rag_result, sources = retrieve_medical_knowledge(query)
        history_text = user_context or query_user_medical_history(self.user_id)
        
        # 銆愭柊澧炪€戜娇鐢ㄥ尰瀛︾煡璇嗗簱澧炲己鐥呭巻淇℃伅
        if lab_results:
            history_text = self.enhancer.enhance_medical_summary(history_text, lab_results)
        
        user_id_info = self.user_id or "anonymous"

        prompt = f"""褰撳墠鐢ㄦ埛ID锛歿user_id_info}

銆愮煡璇嗗簱妫€绱㈢粨鏋溿€?{rag_result or "鏃犵浉鍏崇煡璇嗗簱缁撴灉"}

銆愮敤鎴风梾鍙蹭笌杩囨晱淇℃伅銆?{history_text or "鏃犵敤鎴锋。妗?}

銆愮敤鎴烽棶棰樸€?{query}

璇风粨鍚堜互涓婁俊鎭紝缁欏嚭缁撴瀯鍖栧尰瀛﹀垎鏋愩€傚缓璁寘鍚細
1. 鍏抽敭鎸囨爣鎴栭棶棰樺垽鏂?2. 鍙兘鍘熷洜鍒嗘瀽
3. 闇€瑕侀噸鐐瑰叧娉ㄧ殑椋庨櫓
4. 鍚庣画妫€鏌ユ垨灏卞尰寤鸿

鏈€鍚庡崟鐙緭鍑轰竴琛?META 鏍囪銆?""

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        return messages, sources

    def process_query(self, query: str, user_context: Optional[str] = None, lab_results: Optional[Dict] = None) -> tuple[str, list]:
        try:
            messages, sources = self._build_messages(query, user_context, lab_results)
            response = get_llm(streaming=False).invoke(messages)
            content = getattr(response, "content", str(response))
            cleaned, _ = extract_metadata(content)
            logger.info("Synchronous query processed successfully: %s", query[:50])
            return cleaned, sources
        except Exception as exc:
            logger.error("Synchronous query processing failed: %s", exc, exc_info=True)
            return f"澶勭悊寮傚父: {exc}", []

    def stream_query(self, query: str, user_context: Optional[str] = None, lab_results: Optional[Dict] = None) -> Iterator[Dict[str, object]]:
        try:
            messages, sources = self._build_messages(query, user_context, lab_results)
            full_text = ""
            stream_started_at = time.perf_counter()
            last_chunk_at = stream_started_at
            chunk_count = 0

            for chunk in get_llm(streaming=True).stream(messages):
                text = getattr(chunk, "content", "")
                if not text:
                    continue
                now = time.perf_counter()
                chunk_count += 1
                full_text += text
                logger.info(
                    "LLM stream chunk #%s len=%s delta_ms=%.1f total_ms=%.1f preview=%r",
                    chunk_count,
                    len(text),
                    (now - last_chunk_at) * 1000,
                    (now - stream_started_at) * 1000,
                    text[:40],
                )
                last_chunk_at = now
                yield {"type": "delta", "content": text}

            _, metadata = extract_metadata(full_text)
            logger.info(
                "LLM stream completed chunk_count=%s total_chars=%s total_ms=%.1f",
                chunk_count,
                len(full_text),
                (time.perf_counter() - stream_started_at) * 1000,
            )
            formatted_sources = [
                {
                    "content": source.page_content[:200],
                    "metadata": getattr(source, "metadata", {}),
                }
                for source in sources
            ]
            yield {
                "type": "meta",
                "metadata": metadata,
                "sources": formatted_sources,
            }
        except Exception as exc:
            logger.error("Streaming query processing failed: %s", exc, exc_info=True)
            yield {"type": "error", "error": str(exc)}


def create_medical_agent(user_id: Optional[str] = None) -> MedicalAgent:
    return MedicalAgent(user_id)
