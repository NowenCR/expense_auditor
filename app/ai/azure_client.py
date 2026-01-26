from __future__ import annotations
import os
from openai import AzureOpenAI

def get_azure_client() -> AzureOpenAI:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )
