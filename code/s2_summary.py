"""
第2回：結果のCSVを条件ごとに集計する（APIは使わない）

  python s2_summary.py                       # results/session2_*.csv をすべて集計
  python s2_summary.py ../results/a.csv ...  # ファイルを指定して集計
"""
import csv
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent

files = [Path(f) for f in sys.argv[1:]] or sorted((ROOT / "results").glob("session2_*.csv"))
if not files:
    sys.exit("集計するCSVがありません。先に s2_run.py を実行してください。")

groups = defaultdict(list)
for f in files:
    with open(f, encoding="utf-8-sig") as fp:
        for row in csv.DictReader(fp):
            groups[row["condition"]].append(row)


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def pad(text, width):
    """全角文字を幅2として、右寄せでそろえる（1列目だけ左寄せ）"""
    w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(text))
    return " " * max(0, width - w) + str(text)


print(f"{len(files)} 個のCSVを集計\n")
cols = [("件数", 6), ("人間の確認", 12), ("うちルール", 12), ("うちescalate", 14),
        ("却下", 6), ("AIを変更", 10), ("人間の平均秒", 14), ("1件の平均秒", 13)]
print("条件" + " " * 12 + "".join(pad(c, w) for c, w in cols))
for cond, rows in groups.items():
    n = len(rows)
    rule = sum(r["intervention_via"] == "rule" for r in rows)
    esc = sum(r["intervention_via"] == "escalate" for r in rows)
    rej = sum(r["human_response"] == "reject" for r in rows)
    changed = sum((r["final_action"], r["final_target"]) != (r["ai_action"], r["ai_target"]) for r in rows)
    h = [float(r["human_seconds"]) for r in rows if r["intervention"] == "1"]
    tot = [float(r["total_seconds"]) for r in rows]
    vals = [n, rule + esc, rule, esc, rej, changed, f"{mean(h):.1f}", f"{mean(tot):.1f}"]
    name_w = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in cond)
    print(cond + " " * max(1, 16 - name_w) + "".join(pad(v, w) for v, (_, w) in zip(vals, cols)))

print("\n人間の確認 = ルールで人間に回った回数 + AIが escalate を選んだ回数")
print("AIを変更   = 最終的な対応・対象が、AIの提案と違った件数")
