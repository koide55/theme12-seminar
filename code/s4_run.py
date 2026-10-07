"""
第4回：比較実験（3条件 × 10件 × 反復。あなたが承認者）

  python s4_run.py --name 九大太郎 --order HFD
      --order : 3条件を行う順番（H=人間中心, F=完全委譲, D=判断DSL）。班の中で人ごとに変える（マニュアル参照）
      --dsl   : 判断DSLのルールファイル（省略時は rules/team.yaml）
      --repeat: 同じアラートを何回ずつ判断させるか（省略時は 2）

しくみ:
  1. 最初に、すべてのアラートについてAIの提案を作っておく（10件 × repeat 回だけAPIを呼ぶ）
  2. 同じ提案を3つの条件で使う（条件ごとにAIの答えが変わると、条件の違いが比べられないため）
  3. 条件ごとに、アラートの順番をばらばらに並べ替えて出す

結果は results/session4_<名前>_<日時>.csv に、1件処理するごとに保存される。
※ 対応はすべて「記録上のシミュレーション」です。実際の機器は一切操作しません。
"""
import argparse
import csv
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from dsl import RuleError, load_rules
from s1_agent import propose
from s2_run import LINE, handle

ROOT = Path(__file__).parent.parent
CONDITIONS = {"H": "rules/human_centered.yaml", "F": "rules/full_delegation.yaml"}   # D は --dsl で指定


def main():
    ap = argparse.ArgumentParser(description="第4回の比較実験")
    ap.add_argument("--name", required=True, help="承認者の名前")
    ap.add_argument("--order", required=True, help="条件の順番（H, F, D を1回ずつ。例: HFD）")
    ap.add_argument("--dsl", default="rules/team.yaml", help="判断DSLのルールファイル")
    ap.add_argument("--repeat", type=int, default=2, help="同じアラートを何回ずつ判断させるか")
    ap.add_argument("--seed", type=int, default=None, help="並べ替えの乱数の種（省略時はランダム）")
    args = ap.parse_args()

    order = args.order.upper()
    if sorted(order) != ["D", "F", "H"]:
        sys.exit("--order には H, F, D を1回ずつ並べます（例: HFD, FDH, DHF）")
    files = {**CONDITIONS, "D": args.dsl}
    rules = {}
    for c in order:
        try:
            rules[c] = load_rules(files[c])
        except RuleError as e:
            sys.exit(f"[ルールの誤り] {files[c]}: {e}")

    alerts = json.loads((ROOT / "data" / "alerts.json").read_text(encoding="utf-8"))
    if len(alerts) < 10:
        print(f"⚠ アラートが {len(alerts)} 件しかありません。新しいアラートが配布されているか、git pull を確認してください。")
        if input("このまま続けますか？ [y/n] > ").strip().lower() != "y":
            return

    seed = args.seed if args.seed is not None else random.randrange(10**6)
    rng = random.Random(seed)
    started = datetime.now()
    (ROOT / "results").mkdir(exist_ok=True)
    out = ROOT / "results" / f"session4_{args.name}_{started:%Y%m%d_%H%M%S}.csv"

    # ---- 1. AIの提案を先に作っておく ----------------------------------------------
    print(f"承認者: {args.name}   条件の順番: {' → '.join(rules[c]['name'] for c in order)}   seed={seed}")
    print(f"\nAIに提案を作らせています（{len(alerts)} 件 × {args.repeat} 回）。しばらく待ってください。")
    proposals = {}
    n = 0
    for r in range(1, args.repeat + 1):
        for a in alerts:
            t0 = time.monotonic()
            proposals[(a["id"], r)] = (propose(a), time.monotonic() - t0)
            n += 1
            print(f"  {n}/{len(alerts) * args.repeat}", end="\r")
    print("\n準備ができました。")

    # ---- 2. 条件ごとに実行する ----------------------------------------------------
    f = None
    w = None
    count = 0
    try:
        for pos, c in enumerate(order, 1):
            input(f"\n{LINE}\n条件 {pos}/3：{rules[c]['name']}（{files[c]}）\n"
                  f"準備ができたら Enter を押してください > ")
            trials = [(a, r) for r in range(1, args.repeat + 1) for a in alerts]
            rng.shuffle(trials)
            for i, (a, r) in enumerate(trials, 1):
                print(f"\n［{rules[c]['name']}  {i}/{len(trials)}］")
                p, ai_sec = proposals[(a["id"], r)]
                row = handle(a, rules[c], proposal=dict(p), ai_sec=ai_sec)
                row = {"approver": args.name, "condition": rules[c]["name"], "condition_code": c,
                       "condition_pos": pos, "trial": i, "run": r, "seed": seed, **row}
                if w is None:
                    f = open(out, "w", newline="", encoding="utf-8-sig")   # Excel で文字化けしないよう BOM 付き
                    w = csv.DictWriter(f, fieldnames=row.keys())
                    w.writeheader()
                w.writerow(row)
                f.flush()                                                  # 1件ごとに保存する
                count += 1
    except (KeyboardInterrupt, EOFError):
        print("\n\n中断しました。ここまでの結果は保存されています。")
    finally:
        if f:
            f.close()
            print(f"\n{LINE}\n{count} 件を記録しました。保存: {out}")
            print("集計は python s4_score.py（正解が配布されてから）")


if __name__ == "__main__":
    main()
