"""Web 搜索客户端

Phase 4.6 的 fallback 组件。
当本地知识库（ChromaDB）无法提供足够信息时，
调用 Serper API（Google 搜索代理）获取实时外部数据。

Serper API 简介：
- 服务地址：https://serper.dev/
- 功能：将搜索请求转发给 Google，返回结构化结果
- 定价：每月 2500 次免费查询，之后按量计费
- 使用方式：HTTP POST，Header 中携带 X-API-KEY

使用示例：
    client = WebSearchClient()
    results = client.search("开源项目安全评估标准", num_results=5)
"""

import os

import httpx

from app.core.logger import get_logger

logger = get_logger(__name__)

# Serper API 端点
SERPER_API_URL = "https://google.serper.dev/search"


class WebSearchClient:
    """Web 搜索客户端（Serper API）

    将查询发送到 Serper，获取 Google 搜索结果，
    转换为与向量检索结果一致的格式供 Agent 使用。

    Args:
        api_key: Serper API Key，None 时从环境变量 SERPER_API_KEY 读取
        timeout: HTTP 请求超时时间（秒）
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("SERPER_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Serper API Key 未配置。请在 .env 文件中设置 SERPER_API_KEY="
                "或在 https://serper.dev/ 注册获取免费 API Key。"
            )

        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

        logger.info("Web 搜索客户端初始化完成")

    def search(self, query: str, num_results: int = 5) -> list[dict]:
        """执行 Web 搜索

        Args:
            query: 搜索关键词
            num_results: 返回结果数量（最大 10）

        Returns:
            搜索结果列表，格式与 VectorStore.search() 一致：
            {
                "id": "web_{index}",
                "content": "标题 + 摘要",
                "metadata": {
                    "source": "web",
                    "title": "...",
                    "link": "...",
                },
                "distance": 0.5,  # 固定值，Web 结果无距离概念
            }
        """
        num_results = min(num_results, 10)  # Serper 免费版限制

        logger.info("执行 Web 搜索", query=query[:80], num_results=num_results)

        try:
            response = self._client.post(
                SERPER_API_URL,
                headers={"X-API-KEY": self.api_key},
                json={"q": query, "num": num_results},
            )
            response.raise_for_status()
            data = response.json()

            # 解析搜索结果
            organic = data.get("organic", [])

            results: list[dict] = []
            for i, item in enumerate(organic[:num_results]):
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                link = item.get("link", "")

                content = f"{title}\n{snippet}"
                if len(content) > 2000:
                    content = content[:2000] + "..."

                results.append({
                    "id": f"web_{i}",
                    "content": content,
                    "metadata": {
                        "source": "web",
                        "title": title,
                        "link": link,
                        "category": "web",
                        "topic": title,
                    },
                    "distance": 0.5,  # Web 结果无向量距离，设固定值
                })

            logger.info(
                "Web 搜索完成",
                query=query[:80],
                returned=len(results),
            )
            return results

        except httpx.HTTPStatusError as e:
            logger.error(
                "Web 搜索 HTTP 错误",
                query=query[:80],
                status=e.response.status_code,
                body=e.response.text[:200],
            )
            raise
        except Exception as e:
            logger.error("Web 搜索失败", query=query[:80], error=str(e))
            raise

    def close(self) -> None:
        """关闭 HTTP 客户端"""
        self._client.close()
