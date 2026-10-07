# 判断DSL の書き方（リファレンス）

「AIの提案を、そのまま実行してよいか（`auto`）、人間が確認するか（`ask_human`）」を決めるルールを、YAML というファイル形式で書きます。第2回から第6回まで、このページを見ながら使います。

## 1. 全体の形

```yaml
name: 私のルール          # ルール集の名前（省略可）
rules:                    # ルールを上から順に並べる
  - name: 重要な機器の隔離は人間が確認する
    if:
      action: isolate_host
      asset.importance: 高
    then: ask_human

  - name: AIの自信が低いときは人間が確認する
    if:
      confidence: "< 0.7"
    then: ask_human

default: auto             # どのルールにも当てはまらないとき
```

- `then:` と `default:` に書けるのは **`auto`（AIに任せる）** か **`ask_human`（人間が確認する）** の2つだけです。
- 字下げは**スペース2つ**です（タブは使わない）。`-` の後ろと `:` の後ろには空白を1つ入れます。
- `#` から行末まではコメントです。

## 2. ルールの調べ方：上から順に、最初に当てはまったものだけ

```
AIの提案 ──▶ ルール1 に当てはまる？ ─はい─▶ ルール1 の then で決定
               │いいえ
               ▼
             ルール2 に当てはまる？ ─はい─▶ ルール2 の then で決定
               │いいえ
               ▼
              ...
               ▼
             default で決定
```

**順番が大事です。** 「すぐ戻せる対応は任せる（`auto`）」を一番上に置くと、その下にある「自信が低いときは人間」は、戻せる対応については使われなくなります。

## 3. 条件（`if:`）の書き方

`if:` の下に書いた条件は、**すべて満たしたとき**に当てはまります（「かつ」）。
「または」にしたいときは、ルールを2つに分けます。

### 使える項目

| 項目 | 中身 | 取りうる値 |
|---|---|---|
| `action` | AIが選んだ対応 | `no_action` `monitor` `block_ip` `disable_account` `isolate_host` `escalate` |
| `verdict` | AIの判定 | `true_positive` `false_positive` `uncertain` |
| `severity` | AIが見積もった深刻度 | `low` `medium` `high` `critical`（この順に大きい） |
| `confidence` | AIの自信 | 0.0〜1.0 の数値 |
| `target` | AIが選んだ対象 | 文字列 |
| `source` | アラートを出した装置 | 文字列（例：`認証サーバ`） |
| `asset.host` | アラートの機器名 | 文字列 |
| `asset.importance` | 機器の重要度 | `低` `中` `高` |
| `asset.owner` | 機器の担当部署 | 文字列 |

`action` から `target` までは**AIの提案**の値、`source` と `asset.〜` は**アラート**の値です。

### 値の書き方

| 書き方 | 意味 | 例 |
|---|---|---|
| `値` | 等しい | `action: isolate_host` |
| `[値, 値, ...]` | どれか1つに等しい | `action: [no_action, monitor]` |
| `"!= 値"` | 等しくない | `verdict: "!= false_positive"` |
| `"< 数"` `"<= 数"` `"> 数"` `">= 数"` | 大小の比較 | `confidence: "< 0.7"`、`severity: ">= high"` |

- 大小の比較が使えるのは `confidence` と `severity` だけです。
- **比較は必ず `" "` で囲みます。** 囲まないと YAML の書き方の誤りになります。

## 4. 書いたルールを確かめる

```
python dsl.py rules/自分のルール.yaml
```

書き方に誤りがあれば、どのルールのどこが違うかが表示されます。

第1回の結果（AIの提案を保存したCSV）に当てはめて、どれが人間に回るかを見ることもできます。APIは使わないので、何度試しても料金はかかりません。

```
python dsl.py rules/自分のルール.yaml ../results/session1_20261020_103000.csv
```

第3回からは、**自分の判断（承認するか）と比べて**確かめられます（第3回マニュアル参照）。

```
python s3_check.py rules/自分のルール.yaml
```

## 5. 用意してあるルール

| ファイル | 内容 |
|---|---|
| `rules/human_centered.yaml` | 条件1「人間中心」：ルールなし、すべて `ask_human` |
| `rules/full_delegation.yaml` | 条件2「完全委譲」：ルールなし、すべて `auto` |
| `rules/example.yaml` | 条件3「判断DSL」の例。第3回はこれを写して自分のルールを作る |
| `rules/team.yaml` | 第3回で班ごとに作る。第4回の実験で条件3として使う |

3つの条件は、どれも同じ仕組みで動きます。違うのはルールだけです。
