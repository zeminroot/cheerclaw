# CheerClaw

一个灵活的 AI Agent 框架。旨在帮助转型智能体开发的同学，从0-1实现一个claw类智能体。

## 功能特性

- **主从 Agent 架构**：主 Agent 子 Agent 协同配合，天然上下文隔离
- **plan and execute 增强模式**: todo list 给大型任务规划更长的时间和空间跨度
- **工具系统**：tools + skills渐进式披露，给模型装上`手脚`，避免冗长的system message
- **上下文管理**：工具压缩+内容压缩，支持无限扩增的上下文窗口
- **三层记忆系统**：长期记忆 (MEMORY.md) + 对话压缩 (HISTORY.md) + 原始日志(origion.jsonl)
- **主动记忆召回**：react渐进式记忆检索
- **多通道交互**：支持 CLI 终端、QQ Bot、飞书 Bot、定时任务执行


## 效果展示

![视频1](https://github.com/user-attachments/assets/e1749c35-7d92-4af5-a195-9d2bbc141043)

![视频2](https://github.com/user-attachments/assets/26550485-52f7-43e2-a340-10229895763c)

![CLI 终端](assets/videos/_cli.gif)

![QQ Bot 在线](assets/videos/_qq.gif)

## 安装

```bash

python3.12环境

pip3 install --upgrade pip

pip3 install cheerclaw

skills扩展：
1、建议直接向cheerclaw表明功能需求，cheerclaw将自主搜索clawhub，自动下载安装
2、对于手动下载的skills，请询问cheerclaw应该放置的目录位置
3、如需构建自己的专属skills，请告诉cheerclaw业务流程，cheerclaw将根据业务流程为您构建一个专属的skills
```

## 使用方法

### 本地 CLI 模式

启动终端交互模式：

```bash
cheerclaw local
```

### 在线/后台模式

启动后台运行模式（启动 QQ Bot + 飞书 Bot）：

```bash
cheerclaw online
```

> `online` 模式会根据 `config.json` 中的配置自动启动对应的 Bot：
> - 配置了 `qq.app_id` 则启动 QQ Bot
> - 配置了 `feishu.app_id` 则启动飞书 Bot

## 配置

当前支持qwen系列模型；tavily搜索；在线通信支持qq、飞书

[qwen模型订阅地址](https://bailian.console.aliyun.com/cn-beijing?spm=5176.12818093_47.resourceCenter.1.3be916d0bQ42Yp&tab=home#/home)

[tavily搜索免费apikey注册地址](https://www.tavily.com/)

[qq bot app_id和secret创建地址](https://q.qq.com/#/)

[飞书 bot 创建指南](https://open.feishu.cn/document/home/index)

首次运行后，默认会在 `~/.cheerclaw/` 目录下创建配置文件 `config.json`。

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
  },
  "feishu": {
    "app_id": "cli_xxxxxx",
    "app_secret": "xxxxxxxxxx"
  },
  "tavily": {
    "api_key": "tavily-apikey"
  }
}
```

## 飞书 Bot 配置指南

### 1. 创建飞书应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 点击"创建企业自建应用"
3. 填写应用名称Cheerclaw和描述
4. 进入应用管理后台

### 2. 获取凭证

在"凭证与基础信息"页面获取：
- **App ID**: 应用唯一标识（格式如 `cli_xxxxxx`）
- **App Secret**: 应用密钥

### 3. 开启机器人能力

1. 进入"机器人"菜单
2. 打开"启用机器人"开关

### 4. 配置权限

在"权限管理"中开通以下权限：
- `im:chat:readonly` - 获取群组信息
- `im:message:send_as_bot` - 以机器人身份发送消息
- `im:message:send` - 发送消息
- `im:message.group_at_msg:readonly` - 获取群组中用户@机器人消息
- `im:message.p2p_msg:readonly` - 读取用户发给机器人的单聊消息


### 5. 订阅事件

1. 进入"事件订阅"菜单
2. 打开"启用事件订阅"开关
3. 在"订阅方式"中选择 **使用长连接（WebSocket）**
4. 在"订阅事件"中添加：`im.message.receive_v1`（接收消息）

### 6. 发布应用

1. 进入"版本管理与发布"
2. 点击"创建版本"
3. 填写版本信息后发布

### 7. 使用机器人

将机器人添加到工作群或私聊：
- **私聊**: 在飞书中搜索机器人名称，直接对话
- **群聊**: 在群设置中添加机器人


