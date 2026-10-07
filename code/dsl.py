"""
dsl.py — 判断DSL（人間を呼ぶ条件を書くルール）の読み込みと評価

ルールは YAML で書く（書き方は docs/dsl_spec.md）。

  python dsl.py rules/example.yaml                     # ルールの書き方が正しいか確かめる
  python dsl.py rules/example.yaml results/session1_XXXX.csv
        # 第1回の結果（AIの提案）にルールを当てはめ、どれが人間に回るかを表示（APIは使わない）

プログラムから使うとき:
  from dsl import load_rules, decide
  rules = load_rules("rules/example.yaml")
  decision, rule_name = decide(rules, proposal, alert)   # decision は "auto" か "ask_human"
"""
import csv
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent

DECISIONS = ["auto", "ask_human"]
ACTIONS = ["no_action", "monitor", "block_ip", "disable_account", "isolate_host", "escalate"]
SEVERITY_ORDER = ["low", "medium", "high", "critical"]   # 大小比較ができるように順番を決めておく

# 条件に使える項目と、取りうる値（None は自由な文字列）
FIELDS = {
    "action": ACTIONS,
    "verdict": ["true_positive", "false_positive", "uncertain"],
    "severity": SEVERITY_ORDER,
    "confidence": "number",
    "target": None,
    "source": None,
    "asset.host": None,
    "asset.importance": ["低", "中", "高"],
    "asset.owner": None,
}

_CMP = re.compile(r"^\s*(<=|>=|!=|<|>|==)\s*(.+?)\s*$")


class RuleError(Exception):
    """ルールファイルの書き方の誤り"""


# ---- 読み込みと書き方のチェック ------------------------------------------------

def _check_value(field, value, where):
    allowed = FIELDS[field]
    values = value if isinstance(value, list) else [value]
    for v in values:
        op, x = "==", v
        if isinstance(v, str):
            m = _CMP.match(v)
            if m:
                op, x = m.group(1), m.group(2)
        if isinstance(value, list) and op != "==":
            raise RuleError(f"{where}: リスト [...] の中では比較（< など）は使えません: {v!r}")
        if allowed == "number":
            try:
                float(x)
            except (TypeError, ValueError):
                raise RuleError(f"{where}: {field} には数値を書きます（例: \"< 0.7\"）: {v!r}")
        elif op in ("<", "<=", ">", ">="):
            if field != "severity":
                raise RuleError(f"{where}: 大小の比較（{op}）が使えるのは confidence と severity だけです")
        if isinstance(allowed, list) and str(x) not in allowed:
            raise RuleError(f"{where}: {field} の値 {x!r} は使えません。使える値: {', '.join(allowed)}")


def load_rules(path):
    """YAML のルールファイルを読み、書き方を確かめて返す"""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuleError(f"ファイルが見つかりません: {path}")
    except yaml.YAMLError as e:
        raise RuleError("YAML の書き方に誤りがあります。字下げ（スペース2つ）とコロンの後ろの空白を確認してください。\n"
                        "比較（< や >）を使うときは \"< 0.7\" のように必ず \" \" で囲みます。\n"
                        f"詳細: {e}")

    if not isinstance(data, dict):
        raise RuleError("ファイルの一番外側には rules: と default: を書きます")
    unknown = set(data) - {"name", "rules", "default"}
    if unknown:
        raise RuleError(f"知らない項目があります: {', '.join(unknown)}（使えるのは name, rules, default）")
    if data.get("default") not in DECISIONS:
        raise RuleError("default: には auto か ask_human を書きます（どのルールにも当てはまらないときの扱い）")

    rules = data.get("rules") or []
    if not isinstance(rules, list):
        raise RuleError("rules: の下は「- 」で始まるリストにします")
    for i, r in enumerate(rules, 1):
        where = f"ルール{i}"
        if not isinstance(r, dict):
            raise RuleError(f"{where}: name / if / then を持つ形で書きます")
        where = f"ルール{i}（{r.get('name', '名前なし')}）"
        unknown = set(r) - {"name", "if", "then"}
        if unknown:
            raise RuleError(f"{where}: 知らない項目があります: {', '.join(unknown)}")
        if r.get("then") not in DECISIONS:
            raise RuleError(f"{where}: then: には auto か ask_human を書きます")
        cond = r.get("if")
        if not isinstance(cond, dict) or not cond:
            raise RuleError(f"{where}: if: の下に条件を1つ以上書きます（例: action: isolate_host）")
        for field, value in cond.items():
            if field not in FIELDS:
                raise RuleError(f"{where}: 条件に使えない項目です: {field}。使える項目: {', '.join(FIELDS)}")
            _check_value(field, value, where)
        r.setdefault("name", f"ルール{i}")
    return {"name": data.get("name", path.stem), "rules": rules, "default": data["default"]}


# ---- 評価 ----------------------------------------------------------------------

def _get(field, proposal, alert):
    """項目の値を取り出す。asset.* と source はアラートから、それ以外はAIの提案から"""
    if field.startswith("asset."):
        return (alert.get("asset") or {}).get(field.split(".", 1)[1])
    if field == "source":
        return alert.get("source")
    return proposal.get(field)


def _match_one(field, actual, expected):
    if isinstance(expected, list):                   # リスト: どれか1つに一致
        return actual in expected
    op, x = "==", expected
    if isinstance(expected, str):
        m = _CMP.match(expected)
        if m:
            op, x = m.group(1), m.group(2)
    if actual is None:
        return op == "!="
    if field == "confidence":
        a, b = float(actual), float(x)
    elif field == "severity" and op in ("<", "<=", ">", ">="):
        a, b = SEVERITY_ORDER.index(actual), SEVERITY_ORDER.index(x)
    else:
        a, b = str(actual), str(x)
    return {"==": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]


def decide(rules, proposal, alert):
    """上から順にルールを調べ、最初に当てはまったルールの then を返す。
    戻り値: (判断 "auto" または "ask_human", 当てはまったルールの名前)"""
    for r in rules["rules"]:
        if all(_match_one(f, _get(f, proposal, alert), v) for f, v in r["if"].items()):
            return r["then"], r["name"]
    return rules["default"], "default"


def proposal_from_row(row):
    """結果CSVの1行から、AIの提案を取り出す（第1回の形式と第2回の形式の両方に対応）"""
    keys = ["verdict", "severity", "action", "target", "confidence", "reason"]
    if "ai_action" in row:                      # 第2回の形式（列名が ai_ で始まる）
        p = {k: row["ai_" + k] for k in keys}
    else:                                       # 第1回の形式
        p = {k: row[k] for k in keys}
    p["confidence"] = float(p["confidence"])
    p["alert"] = row.get("alert") or row.get("id")
    p["run"] = row.get("run", "-")
    return p


# ---- コマンドとして使うとき --------------------------------------------------

def _main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    try:
        rules = load_rules(argv[1])
    except RuleError as e:
        print(f"[ルールの誤り] {e}")
        return 1
    print(f"OK: 「{rules['name']}」 ルール {len(rules['rules'])} 個、どれにも当てはまらないときは {rules['default']}")
    for i, r in enumerate(rules["rules"], 1):
        print(f"  {i}. {r['name']}  →  {r['then']}")
    if len(argv) < 3:
        return 0

    alerts = {}
    for f in ("alerts.json", "alerts_session1.json"):
        p = ROOT / "data" / f
        if p.exists():
            for a in json.loads(p.read_text(encoding="utf-8")):
                alerts.setdefault(a["id"], a)
    with open(argv[2], encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"\n{argv[2]} の {len(rows)} 件の提案に当てはめた結果:")
    n_human = 0
    for row in rows:
        row = proposal_from_row(row)
        aid = row["alert"]
        decision, name = decide(rules, row, alerts.get(aid, {}))
        if row["action"] == "escalate":       # AI自身が人間に引き継いだものは、ルールに関係なく人間が決める
            decision, name = "ask_human", "AIが escalate を選んだ"
        n_human += decision == "ask_human"
        mark = "人間" if decision == "ask_human" else "自動"
        print(f"  {aid} #{row.get('run', '-')}  {row['action']:<15} 自信={row['confidence']:.2f}  → {mark}（{name}）")
    print(f"\n人間に回る: {n_human} / {len(rows)} 件")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
