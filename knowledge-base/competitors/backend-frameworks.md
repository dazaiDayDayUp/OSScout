# 后端框架竞品映射

## 领域概述

后端 Web 框架是服务端开发的核心选型。本竞品映射覆盖 Node.js 和 Python 生态的主流框架。

## Node.js 生态

### Express.js

- **定位**：最经典的 Node.js 框架，极简、灵活
- **GitHub**: expressjs/express
- **Stars**: 66k+ | 贡献者: 300+
- **现状**：维护缓慢，Express 5 开发多年未发布，核心团队缩小
- **风险**：活跃度下降，Bus Factor 降低

### Fastify

- **定位**：高性能、低开销的 Node.js 框架
- **GitHub**: fastify/fastify
- **Stars**: 33k+ | 贡献者: 700+
- **优势**：性能优于 Express，插件生态丰富，OpenJS Foundation 支持
- **趋势**：增长迅速，社区活跃

### NestJS

- **定位**：企业级 Node.js 框架，受 Angular 启发
- **GitHub**: nestjs/nest
- **Stars**: 70k+ | 贡献者: 500+
- **优势**：TypeScript 原生支持、模块化架构、企业友好
- **风险**：抽象层较厚，学习曲线陡峭

## Python 生态

### FastAPI

- **定位**：现代、高性能 Python Web 框架
- **GitHub**: tiangolo/fastapi
- **Stars**: 82k+ | 贡献者: 600+
- **优势**：异步原生、自动 OpenAPI 文档、类型安全
- **采用**：被 Microsoft、Uber、Netflix 等公司使用

### Django

- **定位**：全功能 Web 框架，"batteries included"
- **GitHub**: django/django
- **Stars**: 81k+ | 贡献者: 2200+
- **优势**：生态最成熟、Django Software Foundation 治理、安全性强
- **风险**：同步为主（Django 4+ 支持 async 但不够完善）

### Flask

- **定位**：轻量级微框架
- **GitHub**: pallets/flask
- **Stars**: 69k+ | 贡献者: 800+
- **现状**：Pallets 项目（Flask + Jinja + Werkzeug）维护稳定但创新放缓

## 跨语言对比

| 维度 | Express | Fastify | NestJS | FastAPI | Django | Flask |
|------|---------|---------|--------|---------|--------|-------|
| 性能 | ★★☆ | ★★★★★ | ★★★☆ | ★★★★★ | ★★☆ | ★★☆ |
| 社区活跃 | ★★☆ | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★★★ | ★★★★☆ |
| 企业采用 | ★★★★☆ | ★★★☆ | ★★★★☆ | ★★★★☆ | ★★★★★ | ★★★★☆ |
| 学习曲线 | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★★☆ | ★★★☆☆ | ★★★★★ |

## 趋势判断

- **Express 正在衰退**：维护放缓，新项目选择减少
- **Fastify/FastAPI 正在崛起**：性能导向的现代框架受青睐
- **NestJS 稳占企业市场**：TypeScript + 模块化 = 企业友好
- **Django 仍是 Python 首选**：生态和成熟度无人能及
