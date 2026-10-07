"""
第1回 ステップ3：決められた形式（JSON）で対応を提案させる
  python s1_agent.py              # 全アラートを1回ずつ
  python s1_agent.py --repeat 3   # 同じアラートを3回ずつ（答えが毎回同じか確かめる）
結果は results/session1_<日時>.csv に保存される。
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from llm import ask_json

ROOT = Path(__file__).parent.parent

# ---- AIに返してもらう形式 ----------------------------------------------------
# 「どんな項目を」「どんな値で」返すかを決めておくと、プログラムで扱いやすくなる
ACTIONS = ["no_action", "monitor", "block_ip", "disable_account",
           "isolate_host", "escalate"]

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["true_positive", "false_positive", "uncertain"],
                    "description": "本物の攻撃か（true_positive）、誤検知か（false_positive）、判断できないか"},
        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "action": {"type": "string", "enum": ACTIONS,
                   "description": "最初に取るべき対応を1つ"},
        "target": {"type": "string", "description": "対応の対象（ホスト名・アカウント名・IPアドレス）"},
        "confidence": {"type": "number", "description": "この判断への自信（0.0〜1.0）"},
        "reason": {"type": "string", "description": "判断の理由（100字以内）"},
    },
    "required": ["verdict", "severity", "action", "target", "confidence", "reason"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """あなたは企業のセキュリティ運用センター（SOC）の担当者です。
アラートを読み、本物の攻撃かどうかを判断し、最初に取るべき対応を1つ選んでください。
対応の選択肢:
- no_action       : 何もしない（誤検知など）
- monitor         : 監視を強めて様子を見る
- block_ip        : 送信元IPアドレスを遮断する
- disable_account : アカウントを停止する
- isolate_host    : 端末やサーバをネットワークから隔離する（業務が止まる）
- escalate        : 自分では判断せず、上位の担当者に引き継ぐ
"""


def propose(alert):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(alert, ensure_ascii=False, indent=2)},
    ]
    return ask_json(messages, SCHEMA, name="incident_response")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--repeat", type=int, default=1, help="同じアラートを何回ずつ判断させるか")
    args = p.parse_args()

    alerts = json.loads((ROOT / "data" / "alerts_session1.json").read_text(encoding="utf-8"))
    (ROOT / "results").mkdir(exist_ok=True)
    out = ROOT / "results" / f"session1_{datetime.now():%Y%m%d_%H%M%S}.csv"

    rows = []
    for alert in alerts:
        for r in range(args.repeat):
            ans = propose(alert)
            rows.append({"alert": alert["id"], "run": r + 1, **ans})
            print(f"{alert['id']} #{r + 1}  {ans['verdict']:<15} {ans['severity']:<8} "
                  f"{ans['action']:<15} {ans['target']:<20} 自信={ans['confidence']:.2f}")
            print(f"      理由: {ans['reason']}")

    with open(out, "w", newline="", encoding="utf-8-sig") as f:   # Excel で文字化けしないよう BOM 付き
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"\n保存: {out}")
