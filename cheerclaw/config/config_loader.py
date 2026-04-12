#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   config_loader.py
@Author  :   zemin
@Desc    :   配置
'''

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from loguru import logger
from cheerclaw.config.config_schema import Config, ProviderConfig, AgentConfig


# 默认配置文件路径
DEFAULT_CONFIG_DIR = Path.home() / ".cheerclaw"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"


def get_config_path() -> Path:
    """
    获取配置文件路径
    """
    env_path = os.getenv("CHEERCLAW_CONFIG")
    if env_path:
        return Path(env_path)
    return DEFAULT_CONFIG_PATH


def create_default_config() -> Config:
    """
    创建默认配置
    """
    return Config(
        provider=ProviderConfig(
            api_key="",
            api_base=None,
            model="qwen3.5-plus",
        ),
        agent=AgentConfig(
            name="CheerClaw"
        ),
    )


@lru_cache(maxsize=1)
def load_config(config_path: Optional[Path] = None) -> Config:
    """
    加载配置文件
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 使用 Pydantic 验证配置
            return Config.model_validate(data)

        except json.JSONDecodeError as e:
            logger.error(f"❌ 配置文件格式错误: {e}")
            logger.error(f"   文件路径: {path}")
            logger.error("   将使用默认配置")
            return create_default_config()

        except Exception as e:
            logger.error(f"⚠️  加载配置失败: {e}")
            logger.error("   将使用默认配置")
            return create_default_config()

    logger.info(f"📝 配置文件不存在，创建默认配置")
    logger.info(f"   路径: {path}")

    config = create_default_config()
    save_config(config, path)

    logger.info(f"✅ 默认配置已创建")
    logger.info(f"   请编辑配置文件添加你的 API Key:")
    logger.info(f"   {path}")

    return config


def save_config(config: Config, config_path: Optional[Path] = None) -> None:
    """
    保存配置到文件
    config: 配置对象
    config_path: 保存路径
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(mode="json", by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def validate_config_for_mode(config: Config, mode: str) -> tuple[bool, list[str]]:
    """
    验证配置是否满足指定模式的要求
    config: 配置对象
    mode: 启动模式 "local" 或 "online"
    返回: 是否完整, 缺失的字段列表
    """
    missing = []

    # 检查 provider 配置
    if not config.provider.api_key or config.provider.api_key.strip() == "":
        missing.append("api_key")
    if not config.provider.api_base or config.provider.api_base.strip() == "":
        missing.append("api_base")
    if not config.provider.model or config.provider.model.strip() == "":
        missing.append("model")

    # online 模式检查至少配置一个 Channel QQ或飞书
    if mode == "online":
        # 检查 QQ 配置是否完整
        has_qq = bool(
            config.qq.app_id and config.qq.app_id.strip() and
            config.qq.secret and config.qq.secret.strip()
        )

        # 检查飞书配置是否完整
        has_feishu = bool(
            config.feishu.app_id and config.feishu.app_id.strip() and
            config.feishu.app_secret and config.feishu.app_secret.strip()
        )

        # 至少需要一个 Channel
        if not has_qq and not has_feishu:
            missing.append("channel (qq 或 feishu)")

    return len(missing) == 0, missing


def interactive_config_init(mode: str, config: Config, missing_fields: list[str]) -> Config:
    """
    交互式配置初始化。只让用户填写缺失的必填字段，保留已有配置
    mode: 启动模式 "local" 或 "online"
    config: 当前配置对象
    missing_fields: 缺失的字段列表
    返回: 完整的配置对象
    """
    print("\n" + "=" * 50)
    print("🔧 CheerClaw 配置补全")
    print("=" * 50)
    print(f"模式: {mode}")
    if missing_fields:
        print(f"需要填写的字段: {', '.join(missing_fields)}")
    print("请按提示输入配置参数：\n")

    config_path = get_config_path()

    # 根据缺失字段逐个填写
    if "api_key" in missing_fields:
        api_key = input("请输入 API Key: ").strip()
        while not api_key:
            print("❌ API Key 不能为空")
            api_key = input("请输入 API Key: ").strip()
        config.provider.api_key = api_key

    if "api_base" in missing_fields:
        api_base = input("请输入 API Base URL (例如 https://api.openai.com/v1): ").strip()
        while not api_base:
            print("❌ API Base URL 不能为空")
            api_base = input("请输入 API Base URL: ").strip()
        config.provider.api_base = api_base

    if "model" in missing_fields:
        default_model = config.provider.model or "qwen3.5-plus"
        model = input(f"请输入模型名称 [默认: {default_model}]: ").strip()
        config.provider.model = model if model else default_model

    # Channel 配置 (QQ 或 飞书)
    if "channel (qq 或 feishu)" in missing_fields:
        print("\n" + "=" * 50)
        print("📢 online 模式需要至少配置一个消息通道（QQ 或 飞书）")
        print("=" * 50)

        # QQ 配置
        print("\n--- QQ Bot 配置（跳过按回车）---")
        qq_app_id = input("请输入 QQ App ID: ").strip()
        if qq_app_id:
            config.qq.app_id = qq_app_id
            qq_secret = input("请输入 QQ Secret: ").strip()
            if qq_secret:
                config.qq.secret = qq_secret
        else:
            print("  ⏭️  已跳过 QQ 配置")

        # 飞书配置
        print("\n--- 飞书 Bot 配置（跳过按回车）---")
        feishu_app_id = input("请输入飞书 App ID (cli_xxxxxx): ").strip()
        if feishu_app_id:
            config.feishu.app_id = feishu_app_id
            feishu_secret = input("请输入飞书 App Secret: ").strip()
            if feishu_secret:
                config.feishu.app_secret = feishu_secret
        else:
            print("  ⏭️  已跳过飞书配置")

        # 检查至少配置了一个 Channel
        has_qq = bool(config.qq.app_id and config.qq.secret)
        has_feishu = bool(config.feishu.app_id and config.feishu.app_secret)

        if not has_qq and not has_feishu:
            print("\n" + "⚠️ " * 20)
            print("错误：至少需要一个 Channel 配置（QQ 或 飞书）")
            print("⚠️ " * 20)
            print("\n请重新配置...")
            return interactive_config_init(mode, config, ["channel (qq 或 feishu)"])
        else:
            print("\n✅ Channel 配置完成:")
            if has_qq:
                print("  • QQ Bot 已配置")
            if has_feishu:
                print("  • 飞书 Bot 已配置")

    # Tavily配置
    print("\n--- Tavily 搜索配置 ---")
    if not config.tavily.api_key:
        tavily_key = input("请输入 Tavily API Key (直接回车跳过，默认为空): ").strip()
        config.tavily.api_key = tavily_key  # 允许为空
    else:
        print(f"Tavily API Key 已配置，如需修改请手动编辑配置文件")

    # 保存配置
    save_config(config, config_path)

    print("\n" + "=" * 50)
    print("✅ 配置已保存到:", config_path)
    print("=" * 50 + "\n")

    return config
