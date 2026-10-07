"""
第4回：実験結果を正解と照らし合わせて採点・集計する（APIは使わない）

  python s4_score.py                      # results/session4_*.csv をすべて集計
  python s4_score.py ../results/a.csv ... # ファイルを指定して集計
  python s4_score.py --by-approver        # 承認者ごとにも表示する

正解（data/answers.json）は、全員の実験が終わってから配布されます。
採点結果は results/session4_scored.csv に保存されます（第5回の分析で使う）。
"""
import argparse
import csv
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent

# 対応の「強さ」（業務への影響の大きさ）。誤判断が過剰か不足かを見分けるのに使う
STRENGTH = {"no_action": 0, "monitor": 1, "block_ip": 2, "disable_account": 3, "isolate_host": 3}
NEEDS_TARGET = {"block_ip", "disable_account", "isolate_host"}   # 対象まで合っている必要がある対応


def target_ok(target, answer):
    t, a = target.strip().lower(), answer.strip().lower()
    return bool(t) and (a in t or (len(t) >= 3 and t in a))


def is_correct(action, target, ans):
    if action not in ans["acceptable_actions"]:
        return False
    return action not in NEEDS_TARGET or target_ok(target, ans["target"])


def error_type(action, target, ans):
    """誤判断の種類"""
    if is_correct(action, target, ans):
        return ""
    if action in ans["acceptable_actions"]:
        return "対象違い"
    if action == "escalate":
        return "判断の先送り"
    rec = ans["recommended_action"]
    if rec == "escalate":
        return "独断（人に任せるべきものを実行）"
    a, b = STRENGTH[action], STRENGTH[rec]
    return "過剰対応" if a > b else "対応不足（見逃し）" if a < b else "対応の種類違い"


def effect(ai_ok, final_ok, intervened):
    if not intervened:
        return ""
    return {(True, True): "人間も正解", (False, True): "人間が直した",
            (True, False): "人間が誤らせた", (False, False): "人間も直せず"}[(ai_ok, final_ok)]


def width(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(s))


def rpad(s, w):
    return " " * max(0, w - width(s)) + str(s)


def lpad(s, w):
    return str(s) + " " * max(0, w - width(s))


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def summarize(rows, label_w=14):
    cols = [("件数", 6), ("成功率", 8), ("誤判断", 8), ("介入回数", 10), ("介入率", 8), ("人間が直した", 14),
            ("人間が誤らせた", 16), ("人間の平均秒", 14), ("1件の平均秒", 13)]
    print(lpad("条件", label_w) + "".join(rpad(c, w) for c, w in cols))
    groups = defaultdict(list)
    for r in rows:
        groups[(r["condition_code"], r["condition"])].append(r)
    for (code, cond), rs in sorted(groups.items(), key=lambda x: "HDF".index(x[0][0]) if x[0][0] in "HDF" else 9):
        n = len(rs)
        ok = sum(r["correct"] == "1" for r in rs)
        inter = sum(r["intervention"] == "1" for r in rs)
        fixed = sum(r["effect"] == "人間が直した" for r in rs)
        broke = sum(r["effect"] == "人間が誤らせた" for r in rs)
        h = [float(r["human_seconds"]) for r in rs if r["intervention"] == "1"]
        t = [float(r["total_seconds"]) for r in rs]
        vals = [n, f"{ok / n:.0%}", n - ok, inter, f"{inter / n:.0%}", fixed, broke, f"{mean(h):.1f}", f"{mean(t):.1f}"]
        print(lpad(cond, label_w) + "".join(rpad(v, w) for v, (_, w) in zip(vals, cols)))


def main():
    ap = argparse.ArgumentParser(description="第4回の採点・集計")
    ap.add_argument("files", nargs="*", help="集計するCSV（省略時は results/session4_*.csv）")
    ap.add_argument("--by-approver", action="store_true", help="承認者ごとにも表示する")
    args = ap.parse_args()

    ans_file = ROOT / "data" / "answers.json"
    if not ans_file.exists():
        sys.exit("正解（data/answers.json）はまだ配布されていません。全員の実験が終わってから git pull してください。")
    answers = {a["id"]: a for a in json.loads(ans_file.read_text(encoding="utf-8"))}

    files = [Path(f) for f in args.files] or sorted((ROOT / "results").glob("session4_*.csv"))
    files = [f for f in files if f.name != "session4_scored.csv"]
    if not files:
        sys.exit("集計するCSVがありません。先に s4_run.py を実行してください。")

    rows = []
    for f in files:
        with open(f, encoding="utf-8-sig") as fp:
            for r in csv.DictReader(fp):
                ans = answers.get(r["alert"])
                if not ans:
                    continue
                final_ok = is_correct(r["final_action"], r["final_target"], ans)
                ai_ok = is_correct(r["ai_action"], r["ai_target"], ans)
                r.update({
                    "answer_truth": ans["truth"], "answer_action": "/".join(ans["acceptable_actions"]),
                    "answer_target": ans["target"],
                    "correct": "1" if final_ok else "0", "ai_correct": "1" if ai_ok else "0",
                    "error_type": error_type(r["final_action"], r["final_target"], ans),
                    "ai_error_type": error_type(r["ai_action"], r["ai_target"], ans),
                    "effect": effect(ai_ok, final_ok, r["intervention"] == "1"),
                    "source_file": f.name,
                })
                rows.append(r)
    if not rows:
        sys.exit("採点できる行がありませんでした。")

    approvers = sorted({r["approver"] for r in rows})
    print(f"{len(files)} 個のCSV（承認者: {', '.join(approvers)}）を集計\n")
    print("■ 条件ごとの結果（全員分）")
    summarize(rows)
    if args.by_approver:
        for a in approvers:
            print(f"\n■ {a}")
            summarize([r for r in rows if r["approver"] == a])

    # 誤判断の種類
    print("\n■ 誤判断の種類（最終的に実行された対応）")
    kinds = sorted({r["error_type"] for r in rows if r["error_type"]})
    conds = sorted({(r["condition_code"], r["condition"]) for r in rows}, key=lambda x: "HDF".index(x[0]) if x[0] in "HDF" else 9)
    print(lpad("種類", 34) + "".join(rpad(c, 14) for _, c in conds))
    for k in kinds:
        print(lpad(k, 34) + "".join(rpad(sum(r["error_type"] == k and r["condition_code"] == code for r in rows), 14)
                                     for code, _ in conds))

    # アラートごと
    print("\n■ アラートごとの成功数（成功 / 試行）")
    print(lpad("ID", 6) + "".join(rpad(c, 14) for _, c in conds) + "   AI単独の成功")
    for aid in sorted({r["alert"] for r in rows}):
        rs = [r for r in rows if r["alert"] == aid]
        cells = []
        for code, _ in conds:
            x = [r for r in rs if r["condition_code"] == code]
            cells.append(f"{sum(r['correct'] == '1' for r in x)}/{len(x)}")
        ai = f"{sum(r['ai_correct'] == '1' for r in rs)}/{len(rs)}"
        print(lpad(aid, 6) + "".join(rpad(c, 14) for c in cells) + rpad(ai, 15))

    out = ROOT / "results" / "session4_scored.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fp:
        fields = list(dict.fromkeys(k for r in rows for k in r))
        w = csv.DictWriter(fp, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("\n成功 = 最終的に実行された対応が正解の範囲に入り、対象も合っている")
    print("人間が直した／誤らせた = 人間が介入した件のうち、AIの提案と最終結果で正誤が変わったもの")
    print(f"採点結果: {out}")


if __name__ == "__main__":
    main()
