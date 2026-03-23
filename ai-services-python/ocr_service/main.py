import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

import httpx
import redis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()

API_KEY = os.getenv("DASHSCOPE_API_KEY")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen-vl-plus")
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))
LLM_API_TIMEOUT = int(os.getenv("LLM_API_TIMEOUT", "60"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_TTL_SECONDS = int(os.getenv("OCR_CACHE_TTL_SECONDS", "3600"))

logger.info("Initializing OCR service with model: %s", VISION_MODEL)

app = FastAPI(
    title="MedLabAgent OCR Service",
    description="OCR cache service backed by Redis",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeVisionRequest(BaseModel):
    path: str
    model: Optional[str] = None
    force_recheck: bool = False
    focus_item: Optional[str] = None


def create_redis_client() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD or None,
        decode_responses=True,
        socket_timeout=HTTP_TIMEOUT,
        socket_connect_timeout=HTTP_TIMEOUT,
    )


redis_client = create_redis_client()


def normalize_input_path(file_path: str) -> str:
    return file_path.replace("\\", "/").strip()


def build_cache_key(file_path: str, model: str) -> str:
    return f"ocr_cache:{model}:{normalize_input_path(file_path)}"


def resolve_local_path(file_path: str) -> Optional[Path]:
    candidate = normalize_input_path(file_path)
    parsed = urlparse(candidate)

    if parsed.scheme in {"http", "https"}:
        if "/api/v1/file/view/" in parsed.path:
            filename = unquote(parsed.path.rsplit("/", 1)[-1])
            return (Path(UPLOAD_DIR) / filename).resolve()
        return None

    direct = Path(candidate)
    if direct.exists():
        return direct.resolve()

    relative_name = Path(candidate).name
    search_paths = [
        Path(UPLOAD_DIR) / relative_name,
        Path.cwd() / relative_name,
        Path.cwd() / candidate,
        Path.cwd().parent / "backend-java" / "uploads" / relative_name,
        Path.cwd().parent / "uploads" / relative_name,
    ]

    for path in search_paths:
        if path.exists():
            return path.resolve()

    return None


async def load_image_bytes(file_path: str) -> bytes:
    candidate = normalize_input_path(file_path)
    parsed = urlparse(candidate)

    if parsed.scheme in {"http", "https"}:
        logger.info("Downloading remote image for OCR: %s", candidate)
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False, follow_redirects=True) as client:
                response = await client.get(candidate)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"Failed to fetch remote image: {candidate}"
            if status_code is not None:
                detail = f"{detail} (HTTP {status_code})"
            raise HTTPException(status_code=404, detail=detail) from exc

    resolved_path = resolve_local_path(candidate)
    if resolved_path is None or not resolved_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    logger.info("Reading local image for OCR: %s", resolved_path)
    return resolved_path.read_bytes()


def build_prompt(force_recheck: bool, focus_item: Optional[str]) -> str:
    if force_recheck and focus_item:
        return f"""
请对这张医学化验单做高精度二次核对，只重点确认“{focus_item}”相关内容。

要求：
1. 优先确保该项目名称、数值、单位、参考范围准确。
2. 如果该项目在图中不存在，不要臆测，返回空数组或说明未识别到。
3. 输出必须是 JSON 数组，字段固定为:
   item, value, unit, normal_range, status
4. 不要输出 JSON 之外的任何文字。
"""

    return """
请分析这张医学化验单图片，并输出 JSON 数组。

每一项必须包含以下字段：
- item: 检查项目名称
- value: 数值
- unit: 单位
- normal_range: 正常范围
- status: 正常 / ↑升高 / ↓降低 / 未知

要求：
1. 只返回合法 JSON。
2. 尽量提取所有指标。
3. 无法识别的字段可填空字符串，但不要编造。
"""


def parse_llm_json(content: str) -> List[Dict[str, Any]]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.startswith("json"):
            text = text[4:].strip()

    parsed = json.loads(text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    return [{"raw_output": content}]


async def call_vision_llm(base64_image: str, model: str, prompt: str, timeout: int) -> List[Dict[str, Any]]:
    if model.startswith("qwen"):
        return await call_qwen_vision_async(base64_image, model, prompt, timeout)
    if model in {"gpt-4o", "gpt-4-turbo"}:
        return await call_openai_vision_async(base64_image, model, prompt, timeout)
    if model.startswith("claude"):
        return await call_claude_vision_async(base64_image, model, prompt, timeout)

    logger.warning("Unsupported model %s, returning mock data", model)
    return mock_vision_analysis()


async def call_qwen_vision_async(
    base64_image: str,
    model: str,
    prompt: str,
    timeout: int,
) -> List[Dict[str, Any]]:
    if not API_KEY:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY not configured")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.1 if "二次核对" in prompt else 0.3,
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return parse_llm_json(content)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="LLM API timeout") from exc
    except json.JSONDecodeError:
        logger.warning("Qwen returned non-JSON output")
        return [{"raw_output": content}]
    except Exception as exc:
        logger.error("Qwen vision call failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {exc}") from exc


async def call_openai_vision_async(
    base64_image: str,
    model: str,
    prompt: str,
    timeout: int,
) -> List[Dict[str, Any]]:
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.1 if "二次核对" in prompt else 0.3,
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return parse_llm_json(content)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="LLM API timeout") from exc
    except json.JSONDecodeError:
        logger.warning("OpenAI returned non-JSON output")
        return [{"raw_output": content}]
    except Exception as exc:
        logger.error("OpenAI vision call failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {exc}") from exc


async def call_claude_vision_async(
    base64_image: str,
    model: str,
    prompt: str,
    timeout: int,
) -> List[Dict[str, Any]]:
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 2000,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": base64_image,
                                    },
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                },
            )
        response.raise_for_status()
        content = response.json()["content"][0]["text"]
        return parse_llm_json(content)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="LLM API timeout") from exc
    except json.JSONDecodeError:
        logger.warning("Claude returned non-JSON output")
        return [{"raw_output": content}]
    except Exception as exc:
        logger.error("Claude vision call failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {exc}") from exc


async def run_vision_analysis(file_path: str, model: str, prompt: str) -> List[Dict[str, Any]]:
    image_bytes = await load_image_bytes(file_path)
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    return await call_vision_llm(
        base64_image=base64_image,
        model=model,
        prompt=prompt,
        timeout=LLM_API_TIMEOUT,
    )


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    redis_ok = True
    try:
        redis_client.ping()
    except Exception:
        redis_ok = False

    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "OCR Service",
        "model": VISION_MODEL,
        "redis": redis_ok,
        "version": "3.0.0",
    }


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "service": "MedLabAgent OCR Service",
        "version": "3.0.0",
        "description": "OCR cache service backed by Redis",
        "endpoints": {
            "health": "/health",
            "analyze_vision": "/api/v1/analyze-vision",
        },
    }


@app.post("/api/v1/analyze-vision")
async def analyze_vision(request: AnalyzeVisionRequest) -> Dict[str, Any]:
    file_path = normalize_input_path(request.path)
    model = request.model or VISION_MODEL
    cache_key = build_cache_key(file_path, model)

    if not request.force_recheck:
        try:
            cached_payload = redis_client.get(cache_key)
            if cached_payload:
                analysis = json.loads(cached_payload)
                logger.info("OCR cache hit: %s", cache_key)
                return {
                    "status": "success",
                    "file_path": file_path,
                    "model": model,
                    "analysis": analysis,
                    "cached": True,
                    "cache_key": cache_key,
                }
        except Exception as exc:
            logger.warning("Failed to read OCR cache: %s", exc)

    prompt = build_prompt(request.force_recheck, request.focus_item)
    analysis = await run_vision_analysis(file_path=file_path, model=model, prompt=prompt)

    try:
        redis_client.setex(cache_key, REDIS_TTL_SECONDS, json.dumps(analysis, ensure_ascii=False))
    except Exception as exc:
        logger.warning("Failed to write OCR cache: %s", exc)

    logger.info(
        "OCR processed: path=%s force_recheck=%s focus_item=%s",
        file_path,
        request.force_recheck,
        request.focus_item,
    )
    return {
        "status": "success",
        "file_path": file_path,
        "model": model,
        "analysis": analysis,
        "cached": False,
        "cache_key": cache_key,
    }


def mock_vision_analysis() -> List[Dict[str, Any]]:
    return [
        {
            "item": "红细胞计数",
            "value": "4.5",
            "unit": "10^12/L",
            "normal_range": "4.0-5.5",
            "status": "正常",
        },
        {
            "item": "白细胞计数",
            "value": "7.2",
            "unit": "10^9/L",
            "normal_range": "4.5-11.0",
            "status": "正常",
        },
        {
            "item": "空腹血糖",
            "value": "7.5",
            "unit": "mmol/L",
            "normal_range": "3.9-6.1",
            "status": "↑升高",
        },
    ]


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting MedLabAgent OCR service on 0.0.0.0:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
