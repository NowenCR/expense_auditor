from dotenv import load_dotenv
load_dotenv()

import os
from openai import AzureOpenAI

endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").strip()
key = os.getenv("AZURE_FOUNDRY_API_KEY", "").strip()
model = os.getenv("AZURE_FOUNDRY_MODEL", "").strip()
api_version = os.getenv("AZURE_FOUNDRY_API_VERSION", "2024-10-21").strip()

print("ENDPOINT:", endpoint)
print("MODEL/DEPLOYMENT:", model)
print("API_VERSION:", api_version)
print("KEY PRESENT:", bool(key))

client = AzureOpenAI(
    azure_endpoint=endpoint,
    api_key=key,
    api_version=api_version,
)

resp = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "Say 'ok'."},
        {"role": "user", "content": "ok"},
    ],
    temperature=0,
)

print("SUCCESS:", resp.choices[0].message.content)
