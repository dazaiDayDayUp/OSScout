"""
Prompt 模板管理

集中管理各 Agent 使用的 Prompt 模板，
支持变量插值，便于统一维护和调优。
"""
from app.core.logger import get_logger

logger = get_logger(__name__)


class PromptTemplate:
    """
    Prompt 模板类

    使用 Python f-string 风格的变量插值，
    通过 render() 方法传入变量字典生成最终 Prompt。
    """

    def __init__(
        self,
        name: str,
        template: str,
        description: str = "",
    ) -> None:
        self.name = name
        self.template = template
        self.description = description

    def render(self, **kwargs: str) -> str:
        """
        渲染模板，将占位符替换为实际值

        Args:
            **kwargs: 模板变量名和值

        Returns:
            渲染后的完整 Prompt 文本
        """
        try:
            return self.template.format(**kwargs)
        except KeyError as e:
            logger.error(
                "Prompt 模板渲染失败，缺少变量",
                template=self.name,
                missing_variable=str(e),
            )
            raise ValueError(
                f"模板 '{self.name}' 渲染失败，缺少变量: {e}"
            ) from e


# 各 Agent 的 Prompt 模板在各 Agent 模块内独立定义（如 llm_enhancer.py、synthesis_agent.py），
# 便于针对各维度单独调优。PromptTemplate 类本身保留在上方供各模块使用。
