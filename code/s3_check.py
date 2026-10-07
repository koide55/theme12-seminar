"""
第3回：自分の判断DSLを、自分の判断と比べて確かめる（APIは使わない）

  python s3_check.py rules/my_rules.yaml
  python s3_check.py rules/my_rules.yaml --no-ask      # まだ判断していない提案を聞かずに飛ばす

1. results/ にある第1回・第2回のCSVから、AIの提案をすべて集める
2. それぞれの提案を「あなたなら承認するか」を results/my_judgments.csv に記録する
   （第2回で承認・却下したものは自動で入る。まだのものはここで聞かれる）
3. ルールを当てはめ、あなたの判断とのずれを表示する

              ルール → auto（任せる）       ルール → ask_human（人間を呼ぶ）
  あなた承認    ○ 任せてよい                △ 余計な確認（手間が増える）
  あなた却下    × 危険（誤りが実行される）   ○ 正しく止めた
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from dsl import RuleError, decide, load_rules, proposal_from_row

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "results"
JUDGE_FILE = RESULTS / "my_judgments.csv"
JUDGE_FIELDS = ["alert", "action", "target", "judgment", "note"]
LINE = "─" * 64


def load_alerts():
    alerts = {}
    for f in ("alerts.json", "alerts_session1.json"):
        p = ROOT / "data" / f
        if p.exists():
            for a in json.loads(p.read_text(encoding="utf-8")):
                alerts.setdefault(a["id"], a)
    return alerts


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def key(alert, action, target):
    return (alert, action, target.strip())


# ---- あなたの判断（承認するか）の表 ---------------------------------------------

def load_judgments(session2_rows):
    judg = {}
    if JUDGE_FILE.exists():
        for r in read_csv(JUDGE_FILE):
            judg[key(r["alert"], r["action"], r["target"])] = r
    # 第2回で承認・却下した提案は、その判断を使う（表にまだないものだけ）
    for r in session2_rows:
        if r.get("human_response") in ("approve", "reject"):
            k = key(r["alert"], r["ai_action"], r["ai_target"])
            judg.setdefault(k, {"alert": k[0], "action": k[1], "target": k[2],
                                "judgment": r["human_response"], "note": r.get("human_note", "")})
    return judg


def save_judgments(judg):
    RESULTS.mkdir(exist_ok=True)
    with open(JUDGE_FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=JUDGE_FIELDS)
        w.writeheader()
        for k in sorted(judg):
            w.writerow({x: judg[k].get(x, "") for x in JUDGE_FIELDS})


def ask_judgment(p, alert):
    print(f"\n{LINE}\n【{p['alert']}】{alert.get('title', '')}")
    if alert:
        a = alert["asset"]
        print(f"  機器: {a['host']}（重要度 {a['importance']}）  詳細: {alert['detail']}")
    print(f"  AIの提案: {p['action']} → {p['target']}（判定 {p['verdict']}、自信 {p['confidence']:.2f}）")
    print(f"  理由: {p['reason']}")
    while True:
        ans = input("  あなたはこの提案を承認しますか？ [y/n] > ").strip().lower()
        if ans in ("y", "n"):
            break
        print("  y か n で答えてください。")
    note = input("  理由をひとこと（任意） > ").strip()
    return {"alert": p["alert"], "action": p["action"], "target": p["target"].strip(),
            "judgment": "approve" if ans == "y" else "reject", "note": note}


# ---- メイン --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="判断DSLを自分の判断と比べる")
    ap.add_argument("rules", help="ルールファイル（例: rules/my_rules.yaml）")
    ap.add_argument("--no-ask", action="store_true", help="まだ判断していない提案を聞かずに飛ばす")
    args = ap.parse_args()

    try:
        rules = load_rules(args.rules)
    except RuleError as e:
        sys.exit(f"[ルールの誤り] {e}")

    files = sorted(RESULTS.glob("session1_*.csv")) + sorted(RESULTS.glob("session2_*.csv"))
    if not files:
        sys.exit("results/ に第1回・第2回のCSVがありません。code フォルダで実行しているか確認してください。")
    alerts = load_alerts()

    # AIの提案を集める（まったく同じ提案は1つにまとめる）
    proposals, seen, s2_rows = [], set(), []
    for f in files:
        rows = read_csv(f)
        if f.name.startswith("session2_"):
            s2_rows += rows
        for row in rows:
            p = proposal_from_row(row)
            sig = (p["alert"], p["verdict"], p["severity"], p["action"], p["target"].strip(), p["confidence"])
            if sig not in seen:
                seen.add(sig)
                proposals.append(p)

    judg = load_judgments(s2_rows)
    escalated = [p for p in proposals if p["action"] == "escalate"]
    cases = [p for p in proposals if p["action"] != "escalate"]   # escalate はどのルールでも人間が決めるので除く

    # まだ判断していない提案を聞く
    todo = [p for p in cases if key(p["alert"], p["action"], p["target"]) not in judg]
    todo_keys = list(dict.fromkeys(key(p["alert"], p["action"], p["target"]) for p in todo))
    if todo_keys and not args.no_ask:
        print(f"まだあなたが判断していない提案が {len(todo_keys)} 種類あります。先に判断してください。")
        try:
            for k in todo_keys:
                p = next(x for x in todo if key(x["alert"], x["action"], x["target"]) == k)
                judg[k] = ask_judgment(p, alerts.get(p["alert"], {}))
                save_judgments(judg)
        except (KeyboardInterrupt, EOFError):
            print("\n中断しました。ここまでの判断は保存しました。")
    save_judgments(judg)

    # ルールを当てはめて、あなたの判断と比べる
    table = Counter()
    by_rule = Counter()
    danger, extra, unjudged = [], [], 0
    for p in cases:
        j = judg.get(key(p["alert"], p["action"], p["target"]))
        if not j:
            unjudged += 1
            continue
        decision, name = decide(rules, p, alerts.get(p["alert"], {}))
        by_rule[name] += 1
        table[(j["judgment"], decision)] += 1
        if j["judgment"] == "reject" and decision == "auto":
            danger.append((p, name, j))
        if j["judgment"] == "approve" and decision == "ask_human":
            extra.append((p, name, j))

    n = sum(table.values())
    print(f"\n{LINE}\nルール「{rules['name']}」を、AIの提案 {n} 件に当てはめた結果")
    print(f"（同じ提案はまとめています。AIが escalate した {len(escalated)} 件は除外"
          + (f"、未判断の {unjudged} 件も除外" if unjudged else "") + "）\n")
    print("                ルール → auto         ルール → ask_human")
    print(f"  あなた承認     ○ 任せてよい  {table[('approve', 'auto')]:>3}   △ 余計な確認  {table[('approve', 'ask_human')]:>3}")
    print(f"  あなた却下     × 危険        {table[('reject', 'auto')]:>3}   ○ 正しく止めた {table[('reject', 'ask_human')]:>3}")
    asked = table[("approve", "ask_human")] + table[("reject", "ask_human")]
    if n:
        print(f"\n  人間を呼ぶ割合: {asked}/{n}（{asked / n:.0%}）    危険: {len(danger)} 件")

    if danger:
        print("\n× 危険：あなたなら却下するのに、そのまま実行されるもの")
        for p, name, j in danger:
            print(f"  {p['alert']}  {p['action']} → {p['target']}  自信={p['confidence']:.2f}  [{name}]  あなたの理由: {j['note'] or '-'}")
    if extra:
        print("\n△ 余計な確認：あなたなら承認するのに、人間が呼ばれるもの")
        for p, name, j in extra:
            print(f"  {p['alert']}  {p['action']} → {p['target']}  自信={p['confidence']:.2f}  [{name}]")

    print("\nどのルールが何回使われたか（上から順に調べて最初に当たったもの）")
    for r in rules["rules"]:
        print(f"  {by_rule[r['name']]:>3} 回  {r['name']}  → {r['then']}")
    print(f"  {by_rule['default']:>3} 回  （どれにも当てはまらない）→ {rules['default']}")
    print(f"\nあなたの判断の記録: {JUDGE_FILE}（Excel で開いて直せます）")


if __name__ == "__main__":
    main()
