"""
工具：计算 eGFR（估算肾小球滤过率），使用 CKD-EPI 2021 公式
"""

from __future__ import annotations
import logging

from harness.tool.tool_protocol import BaseTool, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class CalculateEgfrTool(BaseTool):
    """根据肌酐值、年龄、性别计算 eGFR 和 CKD 分期"""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calculate_egfr",
            description="根据肌酐值、年龄、性别计算 eGFR 估算肾小球滤过率和 CKD 分期",
            parameters=[
                ToolParameter(
                    name="creatinine",
                    type="number",
                    description="肌酐值（μmol/L）",
                    required=True,
                ),
                ToolParameter(
                    name="age",
                    type="integer",
                    description="患者年龄",
                    required=True,
                ),
                ToolParameter(
                    name="gender",
                    type="string",
                    description="患者性别",
                    enum=["男", "女"],
                    required=True,
                ),
            ],
        )

    async def execute(self, **kwargs) -> ToolResult:
        cr = float(kwargs.get("creatinine", 0))
        age = int(kwargs.get("age", 0))
        gender = kwargs.get("gender", "男")

        if cr <= 0 or age <= 0:
            return ToolResult(content="错误：肌酐值和年龄必须大于 0", success=False)

        try:
            # CKD-EPI 2021 公式
            if gender == "女":
                kappa, alpha = 0.7, -0.241
                gender_factor = 1.012
            else:
                kappa, alpha = 0.9, -0.302
                gender_factor = 1.0

            cr_ratio = (cr / 88.4) / kappa
            egfr = 142 * (min(cr_ratio, 1.0) ** alpha) * (max(cr_ratio, 1.0) ** -1.200) * (0.9938 ** age) * gender_factor

            if egfr >= 90:
                stage = "G1（正常或高滤过）"
            elif egfr >= 60:
                stage = "G2（轻度下降）"
            elif egfr >= 45:
                stage = "G3a（轻中度下降）"
            elif egfr >= 30:
                stage = "G3b（中重度下降）"
            elif egfr >= 15:
                stage = "G4（重度下降）"
            else:
                stage = "G5（肾功能衰竭）"

            content = (
                f"eGFR = {egfr:.1f} mL/min/1.73m²\n"
                f"CKD 分期：{stage}\n"
                f"计算方法：CKD-EPI 2021\n"
                f"输入参数：肌酐={cr} μmol/L, 年龄={age}岁, 性别={gender}"
            )
            return ToolResult(content=content)
        except Exception as e:
            logger.error("eGFR calculation failed: %s", e)
            return ToolResult(content=f"计算 eGFR 失败：{e}", success=False)
