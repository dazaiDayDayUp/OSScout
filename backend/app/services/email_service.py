"""
邮件服务封装

基于 FastAPI-Mail 的异步邮件发送服务，
负责渲染 HTML 模板并发送尽调报告通知邮件。
"""

from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from jinja2 import Environment, FileSystemLoader

from app.config import settings

# Jinja2 模板环境
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))

# FastMail 实例延迟初始化（避免未配置时校验失败）
_fast_mail: FastMail | None = None


def _get_fast_mail() -> FastMail:
    """获取或创建 FastMail 实例"""
    global _fast_mail
    if _fast_mail is None:
        _mail_config = ConnectionConfig(
            MAIL_USERNAME=settings.mail_username,
            MAIL_PASSWORD=settings.mail_password,
            MAIL_FROM=settings.mail_from or settings.mail_username,
            MAIL_PORT=settings.mail_port,
            MAIL_SERVER=settings.mail_server,
            MAIL_STARTTLS=settings.mail_starttls,
            MAIL_SSL_TLS=settings.mail_ssl_tls,
            USE_CREDENTIALS=settings.mail_use_credentials,
            VALIDATE_CERTS=settings.mail_validate_certs,
            TEMPLATE_FOLDER=str(_TEMPLATE_DIR),
        )
        _fast_mail = FastMail(_mail_config)
    return _fast_mail

# 评分颜色映射（用于 SVG 环形图）
_RATING_COLORS = {
    "A+": "#2d8a4e",
    "A": "#4CAF50",
    "B+": "#f0ad4e",
    "B": "#ffc107",
    "C": "#ff9800",
    "D": "#e74c3c",
}

# 评级对应的 CSS 类名
_RATING_CLASSES = {
    "A+": "a-plus",
    "A": "a",
    "B+": "b-plus",
    "B": "b",
    "C": "c",
    "D": "d",
}


def _get_score_color(rating: str) -> str:
    """根据评级获取环形图颜色"""
    return _RATING_COLORS.get(rating, "#94a3b8")


def _get_rating_class(rating: str) -> str:
    """根据评级获取 CSS 类名"""
    return _RATING_CLASSES.get(rating, "d")


def _build_dimension_data(report) -> list[dict]:
    """
    构建维度评分数据（用于模板渲染）

    四个维度的名称、得分、满分、百分比，
    按 PROJECT_PLAN 中的权重顺序排列。
    """
    dimensions = [
        {
            "name": "社区健康度",
            "score": report.community_score,
            "max_score": 30,
            "percentage": min(100, int(report.community_score / 30 * 100)),
        },
        {
            "name": "代码质量",
            "score": report.quality_score,
            "max_score": 25,
            "percentage": min(100, int(report.quality_score / 25 * 100)),
        },
        {
            "name": "安全评分",
            "score": report.security_score,
            "max_score": 25,
            "percentage": min(100, int(report.security_score / 25 * 100)),
        },
        {
            "name": "技术演进",
            "score": report.evolution_score,
            "max_score": 20,
            "percentage": min(100, int(report.evolution_score / 20 * 100)),
        },
    ]
    return dimensions


async def send_report_notification(
    to_email: str,
    report,
    repo,
    report_url: str = "",
) -> None:
    """
    发送尽调报告通知邮件

    渲染 HTML 模板，将评分、维度条形图、关键发现等
    以邮件形式推送给用户。

    Args:
        to_email: 收件人邮箱地址
        report: DueDiligenceReport 对象（含评分、findings 等）
        repo: Repository 对象（含仓库元信息）
        report_url: 完整报告的前端查看链接（可选）

    Raises:
        邮件配置未设置时静默跳过（不打断分析流程）
    """
    # 邮件配置检查：未配置则跳过，不打断主流程
    if not settings.mail_username or not settings.mail_password:
        return

    # 计算环形图参数（半径 52，周长 = 2 * pi * 52 ≈ 326.73）
    radius = 52
    circumference = 2 * 3.14159 * radius
    percentage = min(100, max(0, report.overall_score))
    stroke_dashoffset = circumference * (1 - percentage / 100)

    # 构建模板数据
    template_data = {
        "repo_owner": repo.owner if repo else "unknown",
        "repo_name": repo.repo if repo else "unknown",
        "primary_language": repo.primary_language if repo else None,
        "star_count": repo.star_count if repo else 0,
        "fork_count": repo.fork_count if repo else 0,
        "overall_score": report.overall_score,
        "overall_rating": report.overall_rating,
        "score_color": _get_score_color(report.overall_rating),
        "rating_class": _get_rating_class(report.overall_rating),
        "circumference": round(circumference, 2),
        "stroke_dashoffset": round(stroke_dashoffset, 2),
        "dimensions": _build_dimension_data(report),
        "key_findings": report.key_findings or [],
        "recommendations": report.recommendations or [],
        "analyzed_at": report.created_at.strftime("%Y-%m-%d %H:%M") if report.created_at else "-",
        "report_url": report_url or f"http://localhost:5173/reports/{report.id}",
    }

    # 渲染 HTML 模板
    template = _jinja_env.get_template("report_notification.html")
    html_content = template.render(**template_data)

    # 构造邮件消息
    subject = f"[{report.overall_rating}] {repo.owner}/{repo.repo} 尽调报告 - OSScout"
    message = MessageSchema(
        subject=subject,
        recipients=[to_email],
        body=html_content,
        subtype=MessageType.html,
    )

    # 异步发送
    fast_mail = _get_fast_mail()
    await fast_mail.send_message(message)
