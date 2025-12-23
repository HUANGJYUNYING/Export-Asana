"""檔案用途：Azure OpenAI 客戶端工廠，提供後續模組重用。"""

from openai import AzureOpenAI

from core import config


def get_azure_openai_client() -> AzureOpenAI:
    """
    建立 Azure OpenAI 客戶端（使用 API Key 認證）。

    Returns:
        AzureOpenAI: 已配置好的 Azure OpenAI 客戶端實例。

    Raises:
        ValueError: 當 endpoint、api_key 或 api_version 未設定時。
    """
    if not config.AZURE_OPENAI_ENDPOINT:
        raise ValueError("AZURE_OPENAI_ENDPOINT 未設定，請在 .env 中填入。")
    if not config.AZURE_OPENAI_API_KEY:
        raise ValueError("AZURE_OPENAI_API_KEY 未設定，請在 .env 中填入。")
    if not config.AZURE_OPENAI_API_VERSION:
        raise ValueError("AZURE_OPENAI_API_VERSION 未設定，請在 .env 中填入。")

    return AzureOpenAI(
        api_key=config.AZURE_OPENAI_API_KEY,
        api_version=config.AZURE_OPENAI_API_VERSION,
        azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
    )


def get_chat_deployment_name() -> str:
    """
    取得聊天模型部署名稱。

    Returns:
        str: chat 部署名稱。

    Raises:
        ValueError: 當部署名稱未設定時。
    """
    if not config.AZURE_OPENAI_CHAT_DEPLOYMENT:
        raise ValueError("AZURE_OPENAI_CHAT_DEPLOYMENT 未設定，請在 .env 中填入。")
    return config.AZURE_OPENAI_CHAT_DEPLOYMENT
