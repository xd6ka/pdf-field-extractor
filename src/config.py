"""Configuration, env-overridable."""
import os

MODEL = os.getenv("PDF_MODEL", "qwen2.5:3b")
MAX_REPAIRS = int(os.getenv("PDF_MAX_REPAIRS", "2"))
