"""
第5回：ルールを変えたら結果はどうなっていたか（APIは使わない）

  python s5_whatif.py rules/team.yaml rules/team_v2.yaml ...
  python s5_whatif.py rules/team_v2.yaml --by-alert     # アラートごとの違いも表示
  python s5_whatif.py rules/team_v2.yaml --approver 九大太郎   # 一人分だけで計算

第4回の実験結果（results/session4_*.csv）を使って、別のルールで運用していたら
成功率・承認なし実行・介入率・時間がどうなっていたかを計算する。

計算のしかた（仮定）:
  - AIの提案は、第4回で実際に出たものを使う
  - ルールが auto のとき   … AIの提案をそのまま実行したことにする
  - ルールが ask_human のとき … その承認者が「人間中心」の条件で同じ提案に下した判断と、
                              かかった時間を使う（人間中心では、すべての提案を判断しているため）
  - AIが escalate を選んだときは、どのルールでも人間が判断する
比べやすいように、人間中心と完全委譲も同じ方法で計算して並べる。

結果は results/session5_whatif.csv に保存される（グラフ作りに使う）。
"""
import argparse
import csv
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from dsl import RuleError, decide, load_rules
from s4_score import error_type, is_correct

ROOT = Path(__file__).parent.parent
REFERENCE = ["rules/human_centered.yaml", "rules/full_delegation.yaml"]


def width(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(s))


def rpad(s, w):
    return " " * max(0, w - width(s)) + str(s)


def lpad(s, w):
    return str(s) + " " * max(0, w - width(s))


def load_json(name):
    p = ROOT / "data" / name
    if not p.exists():
        sys.exit(f"data/{name} がありません。git pull してください。")
    return json.loads(p.read_text(encoding="utf-8"))


def load_cases(approver=None):
    """第4回の結果から「人間中心」の行を集める（1行 = 1つの提案と、それに対する人間の判断）"""
    files = [f for f in sorted((ROOT / "results").glob("session4_*.csv")) if f.name != "session4_scored.csv"]
    if not files:
        sys.exit("results/ に第4回のCSV（session4_*.csv）がありません。")
    cases = []
    for f in files:
        with open(f, encoding="utf-8-sig") as fp:
            for r in csv.DictReader(fp):
                if r["condition_code"] == "H" and (approver is None or r["approver"] == approver):
                    cases.append(r)
    if not cases:
        sys.exit("人間中心の条件の結果が見つかりません（--approver の名前も確認）。")
    return cases


def simulate(rules, cases, alerts, answers):
    """ルールで運用していたらどうなったかを、1件ずつ計算する"""
    out = []
    for c in cases:
        p = {k: c["ai_" + k] for k in ["verdict", "severity", "action", "target", "reason"]}
        p["confidence"] = float(c["ai_confidence"])
        ans = answers[c["alert"]]
        decision, rule = decide(rules, p, alerts[c["alert"]])
        human = decision == "ask_human" or p["action"] == "escalate"
        if human:
            action, target = c["final_action"], c["final_target"]
            seconds = float(c["ai_seconds"]) + float(c["human_seconds"])
        else:
            action, target = p["action"], p["target"]
            seconds = float(c["ai_seconds"])
        ok = is_correct(action, target, ans)
        ai_ok = is_correct(p["action"], p["target"], ans)
        if ok:
            cause = ""
        elif not human:
            cause = "AIの誤りがすり抜けた"
        elif ai_ok:
            cause = "人間が誤らせた"
        else:
            cause = "人間も直せなかった"
        out.append({
            "approver": c["approver"], "alert": c["alert"], "run": c["run"], "rules": rules["name"],
            "ai_action": p["action"], "ai_target": p["target"], "ai_confidence": p["confidence"],
            "decision": "ask_human" if human else "auto", "rule": "AIが escalate" if p["action"] == "escalate" else rule,
            "final_action": action, "final_target": target,
            "correct": int(ok), "error_type": error_type(action, target, ans), "cause": cause,
            "unapproved": int(not human and action in ans.get("approval_required", [])),
            "seconds": round(seconds, 2),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="ルールを変えたときの結果を計算する")
    ap.add_argument("rules", nargs="+", help="試すルールファイル")
    ap.add_argument("--by-alert", action="store_true", help="アラートごとの成功数も表示する")
    ap.add_argument("--approver", default=None, help="この承認者の結果だけで計算する")
    args = ap.parse_args()

    alerts = {a["id"]: a for a in load_json("alerts.json")}
    answers = {a["id"]: a for a in load_json("answers.json")}
    cases = load_cases(args.approver)

    files = REFERENCE + [f for f in args.rules if f not in REFERENCE]
    results = []
    for f in files:
        try:
            rules = load_rules(f)
        except RuleError as e:
            sys.exit(f"[ルールの誤り] {f}: {e}")
        results.append((f, rules["name"], simulate(rules, cases, alerts, answers)))

    approvers = sorted({c["approver"] for c in cases})
    print(f"第4回の「人間中心」の結果 {len(cases)} 件（承認者: {', '.join(approvers)}）をもとに計算\n")
    cols = [("成功率", 8), ("誤判断", 8), ("承認なし実行", 14), ("介入率", 8), ("1件の平均秒", 13),
            ("すり抜け", 10), ("人間が誤らせた", 16), ("人間も直せず", 14)]
    print(lpad("ルール", 22) + "".join(rpad(c, w) for c, w in cols))
    summary = []
    for f, name, rows in results:
        n = len(rows)
        ok = sum(r["correct"] for r in rows)
        cause = defaultdict(int)
        for r in rows:
            cause[r["cause"]] += 1
        s = {"rules_file": f, "rules": name, "n": n, "success_rate": round(ok / n, 3), "errors": n - ok,
             "unapproved": sum(r["unapproved"] for r in rows),
             "intervention_rate": round(sum(r["decision"] == "ask_human" for r in rows) / n, 3),
             "mean_seconds": round(sum(r["seconds"] for r in rows) / n, 2),
             "slipped": cause["AIの誤りがすり抜けた"], "human_broke": cause["人間が誤らせた"],
             "human_missed": cause["人間も直せなかった"]}
        summary.append(s)
        vals = [f"{s['success_rate']:.0%}", s["errors"], s["unapproved"], f"{s['intervention_rate']:.0%}",
                f"{s['mean_seconds']:.1f}", s["slipped"], s["human_broke"], s["human_missed"]]
        print(lpad(name[:20], 22) + "".join(rpad(v, w) for v, (_, w) in zip(vals, cols)))

    print("\nすり抜け       = ルールが auto にしたため、AIの誤りがそのまま実行された件数")
    print("人間が誤らせた = AIは正しかったのに、人間に回して誤りになった件数")
    print("人間も直せず   = AIが誤り、人間に回したが、人間も誤った件数")

    # ルールごとの使われ方（自分のルールだけ）
    for f, name, rows in results[len(REFERENCE):]:
        print(f"\n■「{name}」で、どのルールが使われ、どうなったか")
        by = defaultdict(lambda: [0, 0, 0])
        for r in rows:
            b = by[r["rule"]]
            b[0] += 1
            b[1] += 1 - r["correct"]
            b[2] += r["unapproved"]
        for rule, (n, err, un) in sorted(by.items(), key=lambda x: -x[1][0]):
            print(f"  {n:>4} 件  誤り {err:>3}  承認なし {un:>3}   {rule}")

    if args.by_alert:
        print("\n■ アラートごとの成功数（成功 / 件数）")
        ids = sorted({c["alert"] for c in cases})
        print(lpad("ID", 6) + "".join(rpad(name[:10], 14) for _, name, _ in results))
        for aid in ids:
            cells = []
            for _, _, rows in results:
                x = [r for r in rows if r["alert"] == aid]
                cells.append(f"{sum(r['correct'] for r in x)}/{len(x)}")
            print(lpad(aid, 6) + "".join(rpad(c, 14) for c in cells))

    out = ROOT / "results" / "session5_whatif.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=summary[0].keys())
        w.writeheader()
        w.writerows(summary)
    detail = ROOT / "results" / "session5_whatif_detail.csv"
    with open(detail, "w", newline="", encoding="utf-8-sig") as fp:
        rows = [r for _, _, rs in results for r in rs]
        w = csv.DictWriter(fp, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"\n保存: {out}（ルールごとのまとめ）\n      {detail}（1件ずつ）")


if __name__ == "__main__":
    main()
