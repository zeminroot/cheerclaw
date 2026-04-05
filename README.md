# CheerClaw

一个灵活的 AI Agent 框架。旨在帮助转型智能体开发的同学，从0-1实现一个claw类智能体。

## 功能特性

- **主从 Agent 架构**：主 Agent 子 Agent 协同配合，天然上下文隔离
- **plan and execute 增强模式**: todo list 给大型任务规划更长的时间和空间跨度
- **工具系统**：tools + skills渐进式加载
- **上下文管理**：工具压缩+内容压缩，支持无限扩增的上下文窗口
- **三层记忆系统**：长期记忆 (MEMORY.md) + 对话压缩 (HISTORY.md) + 原始日志(origion.jsonl)
- **渐进式记忆召回**：主动式记忆检索
- **多通道交互**：支持 CLI 终端、QQ Bot、定时任务执行

## 安装

```bash
pip3 install --upgrade pip

pip3 install cheerclaw
```

## 使用方法

### 本地 CLI 模式

启动终端交互模式：

```bash
cheerclaw local
```

### 在线/后台模式

启动后台运行模式（启动 QQ Bot 模式）：

```bash
cheerclaw online
```

## 配置

当前支持qwen系列模型；tavily搜索；在线通信支持qq

[qwen模型订阅地址](https://bailian.console.aliyun.com/cn-beijing?spm=5176.12818093_47.resourceCenter.1.3be916d0bQ42Yp&tab=home#/home)

[tavily搜索免费apikey注册地址](https://www.tavily.com/)

[qq bot app_id和secret创建地址](https://q.qq.com/#/)

首次运行后，会在 `~/.cheerclaw/` 目录下创建配置文件 `config.json`。

示例配置：

```json
{
  "provider": {
    "api_key": "your-api-key",
    "api_base": "your-api-url",
    "model": "qwen3.5-plus",
    "timeout": 60
  },
  "agent": {
    "name": "CheerClaw"
  },
  "qq": {
    "app_id": "your-qq-app-id",
    "secret": "your-qq-secret"
  }
}
```


