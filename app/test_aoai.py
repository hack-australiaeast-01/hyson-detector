"""Connectivity check for Azure OpenAI: python test_aoai.py"""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(Path(__file__).parent / ".env")
client = AzureOpenAI(azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"], api_key=os.environ["AZURE_OPENAI_API_KEY"],
                     api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))
model = os.environ["AZURE_OPENAI_DEPLOYMENT"]
msgs = [{"role": "user", "content": "Réponds juste : OK copilote"}]
if model.lower().startswith(("gpt-5", "o1", "o3", "o4")):
    resp = client.chat.completions.create(model=model, max_completion_tokens=300, reasoning_effort="low", messages=msgs)
else:
    resp = client.chat.completions.create(model=model, max_tokens=30, temperature=0, messages=msgs)
print(resp.choices[0].message.content, "| tokens:", resp.usage.total_tokens)
