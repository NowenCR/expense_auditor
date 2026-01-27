from dotenv import load_dotenv
load_dotenv()

import os, requests

endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").rstrip("/")
key = os.getenv("AZURE_FOUNDRY_API_KEY", "")
api_version = os.getenv("AZURE_FOUNDRY_API_VERSION", "2024-06-01")

url = f"{endpoint}/openai/deployments?api-version={api_version}"
r = requests.get(url, headers={"api-key": key}, timeout=20)
print("STATUS:", r.status_code)
print(r.text[:2000])
