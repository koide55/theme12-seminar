"""
第1回 ステップ1：OpenAI API を呼んでみる
  python s1_hello.py
"""
from llm import ask

messages = [
    {"role": "system", "content": "あなたは大学1年生にも分かるように説明する先生です。"},
    {"role": "user", "content": "サイバー攻撃の「インシデント対応」とは何ですか？3行で説明してください。"},
]
print(ask(messages))
