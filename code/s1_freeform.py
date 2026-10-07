"""
第1回 ステップ2：アラートを1件読ませて、自由な文章で対応を聞く
  python s1_freeform.py A01
"""
import json
import sys
from pathlib import Path

from llm import ask

alert_id = sys.argv[1] if len(sys.argv) > 1 else "A01"
alerts = json.loads((Path(__file__).parent.parent / "data" / "alerts_session1.json").read_text(encoding="utf-8"))
alert = next(a for a in alerts if a["id"] == alert_id)

messages = [
    {"role": "system", "content": "あなたは企業のセキュリティ運用センター（SOC）の担当者です。"},
    {"role": "user", "content": "次のアラートを読み、何が起きていると考えられるか、"
                                "どう対応すべきかを答えてください。\n\n"
                                + json.dumps(alert, ensure_ascii=False, indent=2)},
]
print(f"=== アラート {alert['id']}: {alert['title']} ===\n")
print(ask(messages))
