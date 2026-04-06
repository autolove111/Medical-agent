from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List

class ComplexityResult(BaseModel):
    is_complex: bool = Field(description="是否属于疑难杂症（异常项>=3或跨越多个系统）")
    complexity_score: float = Field(description="复杂度得分 0.0 到 1.0")
    departments: List[str] = Field(description="涉及的科室列表，如 ['内分泌科', '肾内科']")
    reason: str = Field(description="为什么打这个分数的简短理由")

def route_complexity(ocr_text: str, llm) -> dict:
    """
    轻量级的复杂度打分器（TaskRouter）
    利用一个轻量级模型快速扫描 OCR 结果，判断异常项的数量和指标的离散度。
    """
    parser = JsonOutputParser(pydantic_object=ComplexityResult)
    prompt = PromptTemplate(
        template="你是一个化验单分诊台护士。请快速分析以下OCR结果并进行复杂度打分。\n"
                 "规则：异常项<3且属于同一系统则is_complex为false；跨多个医学器官系统或异常过多为true。\n{format_instructions}\n\n化验单内容:\n{ocr_text}",
        input_variables=["ocr_text"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    chain = prompt | llm | parser
    return chain.invoke({"ocr_text": ocr_text})
