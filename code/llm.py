"""
llm.py — OpenAI API を呼び出すための共通部品（全コマで使う）

  ask(messages)                 : 文章で答えを返す
  ask_json(messages, schema)    : 決められた形式（JSON）で答えを返す

すべての呼び出しは logs/api_calls.jsonl に記録される（入力・出力・トークン数・時間）。
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI

LOG_FILE = Path(__file__).parent / "logs" / "api_calls.jsonl"


def _model():
    model = os.environ.get("OPENAI_MODEL")
    if not model:
        sys.exit("環境変数 OPENAI_MODEL が設定されていません。マニュアルの「環境構築」を見てください。")
    return model


_client = None


def _get_client():
    global _client
    if _client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            sys.exit("環境変数 OPENAI_API_KEY が設定されていません。マニュアルの「環境構築」を見てください。")
        _client = OpenAI()  # キーは環境変数 OPENAI_API_KEY から自動で読まれる
    return _client


def _log(kind, messages, output, usage, seconds):
    LOG_FILE.parent.mkdir(exist_ok=True)
    rec = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "model": _model(),
        "messages": messages,
        "output": output,
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
        "seconds": round(seconds, 2),
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ask(messages):
    """messages を送り、AIの返答（文字列）を返す"""
    t0 = time.time()
    res = _get_client().chat.completions.create(model=_model(), messages=messages)
    text = res.choices[0].message.content
    _log("text", messages, text, res.usage, time.time() - t0)
    return text


def ask_json(messages, schema, name="answer"):
    """messages を送り、schema（JSON Schema）に従った返答を dict で返す"""
    t0 = time.time()
    res = _get_client().chat.completions.create(
        model=_model(),
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": name, "schema": schema, "strict": True},
        },
    )
    text = res.choices[0].message.content
    _log("json", messages, text, res.usage, time.time() - t0)
    return json.loads(text)
