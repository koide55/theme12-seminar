"""
第5回：AIの強さが変わると、よいルールは変わるか（モデルの比較）

  python s5_models.py collect --model gpt-5.4-nano      # 提案を集める（10件 × 2回 = APIを20回）
  python s5_models.py collect --model gpt-5.6-terra
  python s5_models.py compare rules/team.yaml rules/team_v2.yaml   # 比べる（APIは使わない）

collect : 指定したモデルにすべてのアラートを判断させ、results/session5_proposals_<モデル>_<日時>.csv に保存
compare : 集めた提案にルールを当てはめ、モデルごと・ルールごとに結果を比べる
          （人間に回したものは「人間が正しく判断した」とみなし、AIの誤りがすり抜けたか・
            承認なしで実行されたかを見る）
"""
import argparse
import csv
import json
import os
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from dsl import RuleError, decide, load_rules
from s4_score import is_correct

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "results"


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


# ---- collect：提案を集める ------------------------------------------------------

def collect(args):
    if args.model:
        os.environ["OPENAI_MODEL"] = args.model      # このプログラムの中だけモデルを変える
    from llm import model_name                       # 環境変数を変えてから読み込む
    from s1_agent import propose
    model = model_name()
    alerts = load_json("alerts.json")
    RESULTS.mkdir(exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in model)
    out = RESULTS / f"session5_proposals_{safe}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    rows = []
    print(f"モデル {model} に {len(alerts)} 件 × {args.repeat} 回 判断させます。")
    for r in range(1, args.repeat + 1):
        for a in alerts:
            t0 = time.monotonic()
            p = propose(a)
            rows.append({"model": model, "alert": a["id"], "run": r, **p,
                         "seconds": round(time.monotonic() - t0, 2)})
            print(f"  {a['id']} #{r}  {p['action']:<15} {p['target'][:30]:<30} 自信={p['confidence']:.2f}")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"保存: {out}")


# ---- compare：比べる ------------------------------------------------------------

def compare(args):
    alerts = {a["id"]: a for a in load_json("alerts.json")}
    answers = {a["id"]: a for a in load_json("answers.json")}
    files = sorted(RESULTS.glob("session5_proposals_*.csv"))
    if not files:
        sys.exit("提案がありません。先に python s5_models.py collect --model <モデル名> を実行してください。")
    props = []
    for f in files:
        with open(f, encoding="utf-8-sig") as fp:
            for r in csv.DictReader(fp):
                if r["alert"] in answers:
                    r["confidence"] = float(r["confidence"])
                    r["ok"] = is_correct(r["action"], r["target"], answers[r["alert"]])
                    props.append(r)
    models = sorted({p["model"] for p in props})

    # 1. AI単独の比較
    print("■ AI単独（すべてAIに任せた場合）\n")
    cols = [("件数", 6), ("成功率", 8), ("承認なし実行", 14), ("自信(正解)", 12), ("自信(誤り)", 12), ("平均秒", 8)]
    print(lpad("モデル", 18) + "".join(rpad(c, w) for c, w in cols))
    for m in models:
        ps = [p for p in props if p["model"] == m]
        ok = [p for p in ps if p["ok"]]
        ng = [p for p in ps if not p["ok"]]
        un = sum(p["action"] in answers[p["alert"]].get("approval_required", []) for p in ps)
        mean = lambda xs: f"{sum(xs) / len(xs):.2f}" if xs else "-"
        vals = [len(ps), f"{len(ok) / len(ps):.0%}", un, mean([p["confidence"] for p in ok]),
                mean([p["confidence"] for p in ng]), mean([float(p["seconds"]) for p in ps])]
        print(lpad(m, 18) + "".join(rpad(v, w) for v, (_, w) in zip(vals, cols)))

    print("\n■ アラートごとのAI単独の成功数（成功 / 件数）")
    print(lpad("ID", 6) + "".join(rpad(m[:16], 18) for m in models))
    for aid in sorted({p["alert"] for p in props}):
        cells = []
        for m in models:
            x = [p for p in props if p["model"] == m and p["alert"] == aid]
            cells.append(f"{sum(p['ok'] for p in x)}/{len(x)}" if x else "-")
        print(lpad(aid, 6) + "".join(rpad(c, 18) for c in cells))

    # 2. ルールを当てはめた比較
    rule_files = args.rules or ["rules/team.yaml"]
    print("\n■ ルールを当てはめた場合（人間に回したものは、人間が正しく判断したとみなす）\n")
    cols = [("介入率", 8), ("すり抜け", 10), ("承認なし実行", 14), ("止めた誤り", 12), ("余計な確認", 12)]
    print(lpad("ルール", 20) + lpad("モデル", 18) + "".join(rpad(c, w) for c, w in cols))
    summary = []
    for f in rule_files:
        try:
            rules = load_rules(f)
        except RuleError as e:
            sys.exit(f"[ルールの誤り] {f}: {e}")
        for m in models:
            ps = [p for p in props if p["model"] == m]
            c = {"ask": 0, "slipped": 0, "unapproved": 0, "stopped": 0, "extra": 0}
            for p in ps:
                d, _ = decide(rules, p, alerts[p["alert"]])
                ask = d == "ask_human" or p["action"] == "escalate"
                c["ask"] += ask
                if ask:
                    c["stopped" if not p["ok"] else "extra"] += 1
                else:
                    c["slipped"] += not p["ok"]
                    c["unapproved"] += p["action"] in answers[p["alert"]].get("approval_required", [])
            n = len(ps)
            s = {"rules_file": f, "rules": rules["name"], "model": m, "n": n,
                 "ai_success_rate": round(sum(p["ok"] for p in ps) / n, 3),
                 "intervention_rate": round(c["ask"] / n, 3), "slipped": c["slipped"],
                 "unapproved": c["unapproved"], "stopped": c["stopped"], "extra": c["extra"]}
            summary.append(s)
            vals = [f"{s['intervention_rate']:.0%}", c["slipped"], c["unapproved"], c["stopped"], c["extra"]]
            print(lpad(rules["name"][:18], 20) + lpad(m, 18) + "".join(rpad(v, w) for v, (_, w) in zip(vals, cols)))

    print("\nすり抜け   = ルールが auto にしたため、AIの誤りがそのまま実行された件数")
    print("止めた誤り = AIの誤りを人間に回せた件数    余計な確認 = AIが正しいのに人間に回した件数")
    out = RESULTS / "session5_models.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=summary[0].keys())
        w.writeheader()
        w.writerows(summary)
    print(f"保存: {out}")


def main():
    ap = argparse.ArgumentParser(description="モデルの比較")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="提案を集める（APIを使う）")
    c.add_argument("--model", default=None, help="モデル名（省略時は OPENAI_MODEL）")
    c.add_argument("--repeat", type=int, default=2)
    k = sub.add_parser("compare", help="比べる（APIは使わない）")
    k.add_argument("rules", nargs="*", help="ルールファイル（省略時は rules/team.yaml）")
    args = ap.parse_args()
    collect(args) if args.cmd == "collect" else compare(args)


if __name__ == "__main__":
    main()
