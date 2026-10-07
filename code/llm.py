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

import openai
from openai import OpenAI

LOG_FILE = Path(__file__).parent / "logs" / "api_calls.jsonl"


def _model():
    model = os.environ.get("OPENAI_MODEL")
    if not model:
        sys.exit("環境変数 OPENAI_MODEL が設定されていません。マニュアルの「環境構築」を見てください。")
    return model


def model_name():
    """使っているモデル名（結果のCSVに記録する）"""
    return _model()


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


def _create(**kwargs):
    """APIを呼ぶ。よくあるエラーは、対処が分かる日本語のメッセージにして終了する"""
    try:
        return _get_client().chat.completions.create(model=_model(), **kwargs)
    except openai.AuthenticationError:
        sys.exit("[APIエラー 401] APIキーが正しくありません。写し間違いや前後の空白を確認してください。")
    except openai.NotFoundError:
        sys.exit(f"[APIエラー 404] モデル「{_model()}」が見つかりません。OPENAI_MODEL を確認してください。")
    except openai.RateLimitError as e:
        if "insufficient_quota" in str(e) or "credit" in str(e):
            sys.exit("[APIエラー 429] APIの利用残高（クレジット）がありません。教員に連絡してください。")
        sys.exit("[APIエラー 429] 呼び出しが多すぎます。1分ほど待ってから再実行してください。続く場合は教員へ。")
    except openai.BadRequestError as e:
        sys.exit(f"[APIエラー 400] リクエストが受け付けられませんでした。モデルが構造化出力（json_schema）に"
                 f"対応していない可能性があります。教員に連絡してください。\n詳細: {e}")
    except openai.APIConnectionError:
        sys.exit("[接続エラー] OpenAI に接続できません。ネットワークを確認してください。")


def ask(messages):
    """messages を送り、AIの返答（文字列）を返す"""
    t0 = time.time()
    res = _create(messages=messages)
    text = res.choices[0].message.content
    _log("text", messages, text, res.usage, time.time() - t0)
    return text


def ask_json(messages, schema, name="answer"):
    """messages を送り、schema（JSON Schema）に従った返答を dict で返す"""
    t0 = time.time()
    res = _create(
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": name, "schema": schema, "strict": True},
        },
    )
    text = res.choices[0].message.content
    _log("json", messages, text, res.usage, time.time() - t0)
    return json.loads(text)
