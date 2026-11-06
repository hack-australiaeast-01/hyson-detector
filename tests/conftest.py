"""Offline test set-up: committed Gold snapshot, deterministic copilot, never Fabric or Azure OpenAI (no cost, no secrets)."""
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
os.environ["DATA_SOURCE"] = "local"
os.environ["COPILOT_OFFLINE"] = "1"
for _k in [k for k in os.environ if k.startswith(("AZURE_OPENAI", "FABRIC_"))]:
    os.environ.pop(_k)
sys.path.insert(0, str(APP))
