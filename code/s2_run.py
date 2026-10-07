"""
第2回：3つの条件でAIエージェントを動かす（あなたが承認者になる）

  python s2_run.py rules/human_centered.yaml      # 条件1 人間中心：すべて人間が承認
  python s2_run.py rules/full_delegation.yaml     # 条件2 完全委譲：AIがすべて決める
  python s2_run.py rules/example.yaml             # 条件3 判断DSL：ルールに当てはまるときだけ人間

オプション:
  --alerts A01,A02   判断させるアラート（省略時は A01〜A05）
  --repeat 2         同じアラートを何回ずつ判断させるか（省略時は1）
  --name 九大太郎     承認者の名前（CSVに記録される）

結果は results/session2_<条件名>_<日時>.csv に保存される。
※ 対応はすべて「記録上のシミュレーション」です。実際の機器は一切操作しません。
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dsl import RuleError, decide, load_rules
from llm import model_name
from s1_agent import ACTIONS, propose   # 第1回で作った「AIに提案させる」部品をそのまま使う

ROOT = Path(__file__).parent.parent
LINE = "─" * 64


# ---- 画面表示 ------------------------------------------------------------------

def show_alert(alert):
    a = alert["asset"]
    print(f"\n{LINE}\n【アラート {alert['id']}】{alert['title']}")
    print(f"  発生: {alert['time']}   検知元: {alert['source']}")
    print(f"  機器: {a['host']}（重要度 {a['importance']}、担当 {a['owner']}）")
    print(f"  詳細: {alert['detail']}")


def show_proposal(p):
    print(f"\n【AIの提案】 {p['action']}  →  対象: {p['target']}")
    print(f"  判定: {p['verdict']}   深刻度: {p['severity']}   自信: {p['confidence']:.2f}")
    print(f"  理由: {p['reason']}")


# ---- 人間に確認する ------------------------------------------------------------

def ask_yes_no(prompt):
    while True:
        ans = input(prompt).strip().lower()
        if ans in ("y", "yes", "はい"):
            return True
        if ans in ("n", "no", "いいえ"):
            return False
        print("  y か n で答えてください。")


def choose_action(default_target):
    """人間が自分で対応と対象を選ぶ"""
    for i, a in enumerate(ACTIONS, 1):
        print(f"    {i}. {a}")
    while True:
        s = input("  実行する対応の番号 > ").strip()
        if s.isdigit() and 1 <= int(s) <= len(ACTIONS):
            action = ACTIONS[int(s) - 1]
            break
        print(f"  1〜{len(ACTIONS)} の番号で答えてください。")
    target = input(f"  対象（Enter で「{default_target}」のまま） > ").strip() or default_target
    return action, target


def ask_human(p, via):
    """承認者に確認する。戻り値: (人間の返答, 最終的な対応, 対象, 人間がかけた秒数)"""
    t0 = time.monotonic()
    if via == "escalate":
        # AI自身が「判断できない」と人間に引き継いできた。承認ではなく、人間が対応を選ぶ
        print("\n▶ AIは判断を人間に引き継ぎました（escalate）。あなたが対応を選んでください。")
        action, target = choose_action(p["target"])
        return "decide", action, target, time.monotonic() - t0
    print("\n▶ あなたの承認が必要です。")
    if ask_yes_no("  この提案を実行してよいですか？ [y/n] > "):
        return "approve", p["action"], p["target"], time.monotonic() - t0
    print("  却下しました。代わりに実行する対応を選んでください。")
    action, target = choose_action(p["target"])
    return "reject", action, target, time.monotonic() - t0


def _rule_label(rule_name):
    return "どのルールにも当てはまらない → default" if rule_name == "default" else f"ルール「{rule_name}」"


# ---- 1件のアラートを処理する ----------------------------------------------------

def handle(alert, rules, proposal=None, ai_sec=None):
    """1件のアラートを処理する。proposal を渡したときは、APIを呼ばずにその提案を使う（第4回で使用）"""
    show_alert(alert)

    if proposal is None:
        t0 = time.monotonic()
        p = propose(alert)                     # AIに提案させる（APIを呼ぶ）
        ai_sec = time.monotonic() - t0
    else:
        p = proposal
    show_proposal(p)

    decision, rule_name = decide(rules, p, alert)   # 判断DSL：人間を呼ぶかどうか
    if p["action"] == "escalate":
        via = "escalate"                       # AI自身が「判断できない」と人間に引き継いだ（どの条件でも人間が決める）
    elif decision == "ask_human":
        via = "rule"                           # ルールによって人間に回った
    else:
        via = ""

    if via:
        reason = "AIが escalate を選んだ" if via == "escalate" else _rule_label(rule_name)
        print(f"  （人間に確認する理由: {reason}）")
        response, action, target, human_sec = ask_human(p, via)
        note = input("  判断の理由をひとこと（任意・Enter で省略） > ").strip()
    else:
        print(f"\n▶ 人間の確認なしで実行します（{_rule_label(rule_name)}）。")
        response, action, target, human_sec, note = "", p["action"], p["target"], 0.0, ""

    print(f"\n  [シミュレーション] {action} を {target} に実行しました（実際の機器は操作していません）")
    return {
        "alert": alert["id"],
        "ai_verdict": p["verdict"], "ai_severity": p["severity"], "ai_action": p["action"],
        "ai_target": p["target"], "ai_confidence": p["confidence"], "ai_reason": p["reason"],
        "decision": decision, "rule": rule_name,
        "intervention": 1 if via else 0, "intervention_via": via,
        "human_response": response, "human_note": note,
        "final_action": action, "final_target": target,
        "ai_seconds": round(ai_sec, 2), "human_seconds": round(human_sec, 2),
        "total_seconds": round(ai_sec + human_sec, 2),
    }


# ---- メイン --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="3つの条件でAIエージェントを動かす")
    ap.add_argument("rules", help="ルールファイル（例: rules/human_centered.yaml）")
    ap.add_argument("--alerts", default="A01,A02,A03,A04,A05", help="アラートIDをカンマ区切りで")
    ap.add_argument("--repeat", type=int, default=1, help="同じアラートを何回ずつ判断させるか")
    ap.add_argument("--name", default="", help="承認者の名前")
    args = ap.parse_args()

    try:
        rules = load_rules(args.rules)
    except RuleError as e:
        sys.exit(f"[ルールの誤り] {e}")

    all_alerts = {a["id"]: a for a in json.loads((ROOT / "data" / "alerts.json").read_text(encoding="utf-8"))}
    ids = [s.strip() for s in args.alerts.split(",") if s.strip()]
    unknown = [i for i in ids if i not in all_alerts]
    if unknown:
        sys.exit(f"知らないアラートIDです: {', '.join(unknown)}")

    (ROOT / "results").mkdir(exist_ok=True)
    started = datetime.now()
    out = ROOT / "results" / f"session2_{Path(args.rules).stem}_{started:%Y%m%d_%H%M%S}.csv"
    print(f"条件: {rules['name']}（{args.rules}）  アラート: {', '.join(ids)} × {args.repeat}回")

    rows = []
    try:
        for r in range(args.repeat):
            for aid in ids:
                row = handle(all_alerts[aid], rules)
                rows.append({"condition": rules["name"], "rules_file": Path(args.rules).name,
                             "approver": args.name, "run": r + 1, "model": model_name(), **row})
    except (KeyboardInterrupt, EOFError):
        print("\n\n中断しました。ここまでの結果を保存します。")
    finally:
        if rows:
            with open(out, "w", newline="", encoding="utf-8-sig") as f:   # Excel で文字化けしないよう BOM 付き
                w = csv.DictWriter(f, fieldnames=rows[0].keys())
                w.writeheader()
                w.writerows(rows)
            n = sum(x["intervention"] for x in rows)
            t = sum(x["total_seconds"] for x in rows)
            print(f"\n{LINE}\n{len(rows)} 件を処理  人間の確認: {n} 回  合計時間: {t:.1f} 秒")
            print(f"保存: {out}")


if __name__ == "__main__":
    main()
