# 第1回：AIにインシデント対応をさせてみる

電気情報工学セミナーA　テーマ12「AIに任せるか、人間が決めるか」

**今日のゴール**

1. インシデント対応の流れと「アラート」が何かを説明できる
2. Python から OpenAI API を呼び出せる
3. AIにアラートを読ませ、対応の提案を**決められた形式（JSON）**で受け取れる
4. AIの提案を見て、「このまま実行してよいか」を自分の言葉で判断できる

**時間配分の目安（90分）**：説明 20分 → 環境構築 20分 → ステップ1〜3 35分 → 考察・まとめ 15分

---

## 1. インシデント対応とは

組織のネットワークやコンピュータで、攻撃や事故（**インシデント**）が起きたときに、被害を抑えて元に戻す活動を**インシデント対応**と呼びます。

```
 検知 ──▶ 判断（トリアージ）──▶ 封じ込め ──▶ 根絶・復旧 ──▶ 振り返り
 「何か   「本物の攻撃か？      「被害が広がら   「原因を取り除き   「再発防止」
  起きた」  どれくらい危険か？」  ないように止める」 元に戻す」
```

### アラート

監視システムが「怪しい」と判断したときに出す通知が**アラート**です。

- 実際のSOC（セキュリティ運用センター）には、1日に数百〜数千件のアラートが届きます。
- その多くは**誤検知**（本当は攻撃ではない）です。
- 本物の攻撃を見逃すと大きな被害になります。一方で、誤検知に過剰反応して業務を止めても損害が出ます。

### 対応の選択肢（このテーマで使うもの）

| 対応 | 内容 | 副作用 |
|---|---|---|
| `no_action` | 何もしない | 本物の攻撃なら被害が広がる |
| `monitor` | 監視を強めて様子を見る | 対応が遅れる可能性 |
| `block_ip` | 送信元のIPアドレスを遮断 | 正規の通信も止まる可能性 |
| `disable_account` | アカウントを停止 | その人は仕事ができなくなる |
| `isolate_host` | 端末・サーバをネットワークから隔離 | **その機器を使う業務が止まる** |
| `escalate` | 自分では判断せず上位の担当者へ | 人間の手間と時間がかかる |

**どの対応にも副作用がある**ことが、このテーマの出発点です。

## 2. 大規模言語モデル（LLM）のAPI

ChatGPT のような大規模言語モデルは、プログラムから **API** を通じて呼び出せます。

```python
messages = [
    {"role": "system", "content": "あなたは〇〇の担当者です。"},   # AIの役割・ルール
    {"role": "user",   "content": "このアラートを判断して"},        # 依頼内容
]
```

- **system**：AIの役割や守るべきルールを書く
- **user**：毎回の依頼内容を書く
- 料金は、送る文字量と返ってくる文字量（**トークン数**）で決まります。

### 構造化出力（JSON）

文章で返ってきた答えは、人間には読めてもプログラムでは扱いにくいものです。そこで「この項目を、この選択肢から選んで返して」と**形式（JSON Schema）**を指定します。

```json
{
  "verdict": "true_positive",
  "severity": "high",
  "action": "disable_account",
  "target": "yamada.t",
  "confidence": 0.85,
  "reason": "総当たりの後にログインが成功し、直後に転送設定が変更されたため"
}
```

こうしておけば、第2回以降で「`action` が `isolate_host` なら人間に確認する」といった制御をプログラムで書けます。

## 3. 環境構築

> 💡 **3.0節（ソフトのインストール）は、できるだけ授業の前に済ませておいてください。** 授業中に始めると、ダウンロードとインストールだけで時間がなくなります。

### 3.0 必要なソフトをインストールする

次の3つが必要です。すでに入っている人は、バージョンの確認だけでかまいません。

| ソフト | 用途 | 入手先 |
|---|---|---|
| **Git** | 教材（リポジトリ）の取得 | https://git-scm.com/ |
| **Python 3.10 以上** | プログラムの実行 | https://www.python.org/downloads/ |
| **Visual Studio Code**（VS Code） | プログラムの編集と、ターミナルでの実行 | https://code.visualstudio.com/ |

#### Windows の場合

1. **Git**：https://git-scm.com/ から「Download for Windows」を選んでインストーラを実行します。設定はすべて初期値（Next を押し続ける）でかまいません。
2. **Python**：https://www.python.org/downloads/ からインストーラを実行します。
   - ⚠️ **最初の画面の下にある「Add python.exe to PATH」に必ずチェックを入れてください。** これを忘れると、`python` コマンドが見つからなくなります（忘れた場合は、インストーラを再実行して「Modify」から設定し直すか、アンインストールして入れ直す）。
3. **VS Code**：https://code.visualstudio.com/ からインストーラを実行します。途中の「PATH への追加」にチェックを入れておきます。起動後、左の拡張機能アイコンから **「Python」拡張機能（Microsoft 製）** を入れておくと便利です。

> 参考：`winget` が使える人は、PowerShell で次のようにまとめてインストールすることもできます。
> ```powershell
> winget install --id Git.Git -e
> winget install --id Python.Python.3.12 -e
> winget install --id Microsoft.VisualStudioCode -e
> ```

4. **PowerShell のスクリプト実行を許可する**（Windows だけ・最初に1回だけ）

   Windows の初期設定では、PowerShell でスクリプト（`.ps1` ファイル）を実行できません。このままだと、3.1節で仮想環境を有効にする `venv\Scripts\Activate.ps1` が「このシステムではスクリプトの実行が無効になっているため…」というエラーで止まります。

   1. スタートメニューで「PowerShell」と検索し、**右クリック →「管理者として実行」** で開きます（「このアプリがデバイスに変更を加えることを許可しますか？」には「はい」）。
   2. 次のコマンドを実行します。確認を求められたら `Y` を入力して Enter を押します。
      ```powershell
      Set-ExecutionPolicy RemoteSigned
      ```
   3. 設定を確認します。`RemoteSigned` と表示されればOKです。
      ```powershell
      Get-ExecutionPolicy
      ```
   4. **管理者の PowerShell はここで閉じてください。** 以降の作業は、通常の PowerShell か VS Code のターミナルで行います（管理者のままで作業を続けないこと）。

   > `RemoteSigned` は「自分のPCで作ったスクリプトは実行してよい。インターネットから取ってきたスクリプトは署名付きのものだけ実行する」という設定です。
   > 大学や会社の管理下にあるPCで、管理者として実行できない・設定が変わらない場合は、教員に相談してください。

#### macOS の場合

1. **Git**：ターミナルで `git --version` を実行します。入っていなければ、インストールを促す画面が出るので「インストール」を押します（または `xcode-select --install`）。
2. **Python**：ターミナルで `python3 --version` を実行し、3.10 以上ならそのまま使えます。古い場合は https://www.python.org/downloads/ からインストールします。
3. **VS Code**：https://code.visualstudio.com/ からダウンロードし、「アプリケーション」フォルダに移動します。「Python」拡張機能を入れておくと便利です。

#### インストールできたか確認する

**新しく開いた**ターミナル（VS Code では「ターミナル」→「新しいターミナル」）で、次を実行します。インストール前から開いていたターミナルでは、コマンドが見つからないことがあります。

```powershell
# Windows
git --version
python --version
code --version
```

```bash
# macOS
git --version
python3 --version
code --version
```

3つともバージョン番号が表示されればOKです（Python は 3.10 以上）。

### 3.1 リポジトリを取得して仮想環境を作る

VS Code を開き、メニューの「ターミナル」→「新しいターミナル」でターミナルを開いて、次を実行します。**Windows と macOS でコマンドが少し違う**ので注意してください。

```powershell
# Windows (PowerShell)
git clone <教員から指示されたURL> theme12
cd theme12
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# macOS / Linux
git clone <教員から指示されたURL> theme12
cd theme12
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

仮想環境が有効になると、プロンプトの先頭に `(venv)` と表示されます。**ターミナルを開き直したときは、`venv\Scripts\Activate.ps1`（macOS は `source venv/bin/activate`）をもう一度実行してください。**

> Windows では `python3` ではなく **`python`** を使います。`python3` と打つと Microsoft Store が開くことがあります。
>
> VS Code で `theme12` フォルダを開いておくと（「ファイル」→「フォルダーを開く」）、ファイルの編集と実行が同じ画面でできます。

### 3.2 APIキーとモデル名を設定する

APIキーとモデル名は、教員から個別に伝えます。

```bash
# macOS / Linux（端末を開くたびに必要）
export OPENAI_API_KEY="sk-...（配布されたキー）"
export OPENAI_MODEL="（指示されたモデル名）"
```

```powershell
# Windows (PowerShell)
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_MODEL="（指示されたモデル名）"
```

> ⚠️ **APIキーの取り扱い**
> - APIキーは「お金を使える鍵」です。**他人に渡さない、プログラムに書き込まない、GitHub や Slack に貼らない。**
> - 誤って公開してしまったら、**すぐに教員へ連絡**してください（キーを無効化します）。

### 3.3 確認

```bash
cd code
python check_setup.py
```

最後に `準備完了です。` と表示されればOKです。

## 4. ステップ1：APIを呼んでみる

```bash
python s1_hello.py
```

AIが「インシデント対応とは何か」を3行で説明すれば成功です。`s1_hello.py` の system と user の文章を書き換えて、答えがどう変わるか試してみましょう。

## 5. ステップ2：アラートを読ませる（自由な文章で）

アラートは `data/alerts_session1.json` に5件入っています（すべて架空のものです）。まずは中身を読んでみましょう。

| ID | 内容 |
|---|---|
| A01 | 同一アカウントへのログイン失敗が多発し、その後成功 |
| A02 | 業務端末で不審な PowerShell の実行 |
| A03 | 社内からのポートスキャン |
| A04 | 共有フォルダで短時間に大量のファイル名変更 |
| A05 | 退職予定者によるクラウドストレージへの大容量アップロード |

```bash
python s1_freeform.py A01
python s1_freeform.py A03
```

AIの回答は長い文章で返ってきます。**AIが最終的に何をすべきだと言っているのか、一言で言えますか？**　プログラムでこの答えを扱うのが難しいことを実感してください。

## 6. ステップ3：決められた形式で提案させる

```bash
python s1_agent.py
```

5件のアラートそれぞれについて、次のような1行が表示されます（内容は毎回変わります）。

```
A01 #1  true_positive   high     disable_account yamada.t            自信=0.85
      理由: ……
```

結果は `results/session1_<日時>.csv` に保存されます（Excelで開けます）。

`s1_agent.py` の中身を読んで、次の3つを確認しましょう。

- `SCHEMA`：AIに返させる項目と選択肢
- `SYSTEM_PROMPT`：AIへの指示
- `propose()`：1件のアラートをAIに送る関数

### 同じ質問を繰り返すと？

```bash
python s1_agent.py --repeat 3
```

同じアラートを3回ずつ判断させます。**毎回同じ答えになるでしょうか？**

## 7. 演習：あなたはこの提案を承認しますか？

下の表を埋めましょう（3人で話し合ってかまいません）。

| ID | AIの判定 | AIの対応 | 3回とも同じ？ | あなたなら承認する？（はい／いいえ／条件付き） | その理由 |
|---|---|---|---|---|---|
| A01 | | | | | |
| A02 | | | | | |
| A03 | | | | | |
| A04 | | | | | |
| A05 | | | | | |

考えるヒント：

- **A03**：アラートの `detail` を最後までよく読むと、何が分かりますか？　AIはそれに気づいていましたか？
- **A04**：これが本物なら、一刻を争います。人間の承認を待っている間に何が起きるでしょうか？
- **A05**：技術的な判断だけで済む問題でしょうか？　AIが `disable_account` を提案したら、そのまま実行してよいですか？

## 8. 今日のまとめと次回予告

今日の演習で、次の3つのタイプがあることに気づいたはずです。

- AIにそのまま任せてもよさそうな判断
- 必ず人間が確認すべき判断
- 急ぐので、人間を待っていられない判断

**次回**は、AIの提案を「人間がすべて承認する」「AIがすべて実行する」「条件に合うときだけ人間が確認する」という3つの方式で動かすプログラムを作ります。今日の表の「承認する／しない」の理由が、その「条件」の元になります。**表は捨てずに持ってきてください。**

## 提出物（今日の分）

- [ ] `results/` に保存されたCSV（`--repeat 3` で実行したもの）
- [ ] 第7節の表（レポートの材料になります）

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `環境変数 OPENAI_API_KEY が設定されていません` | 3.2節の設定（macOS は `export`、Windows は `$env:...`）を、今使っている端末で実行し直す。ターミナルを開き直すと消えます |
| `AuthenticationError` / `401` | APIキーの写し間違い。前後に空白が入っていないか確認する |
| `NotFoundError` / `model ... does not exist` | `OPENAI_MODEL` のモデル名を確認する |
| `RateLimitError` / `429` | 呼び出しが多すぎます。少し待ってから再実行する。続く場合は教員へ |
| `ModuleNotFoundError: No module named 'openai'` | 仮想環境が有効になっていない → `source venv/bin/activate`（Windows は `venv\Scripts\Activate.ps1`） |
| （Windows）`このシステムではスクリプトの実行が無効になっているため、ファイル ...Activate.ps1 を読み込むことができません` | スクリプトの実行が許可されていない → 3.0節の手順4（管理者の PowerShell で `Set-ExecutionPolicy RemoteSigned`）を行い、ターミナルを開き直す |
| （Windows）`git` / `python` / `code` が「認識されません」 | インストール後に開き直していないターミナルを使っている → ターミナル（VS Code ごと）を開き直す。それでもだめなら、インストール時に PATH への追加を忘れている（3.0節） |
| （Windows）`python3` と打つと Microsoft Store が開く | Windows では `python` を使う |
| （Windows）`python` と打つと Microsoft Store が開く | Python のインストール時に「Add python.exe to PATH」にチェックを入れ忘れている → 3.0節を見てインストールし直す。または「設定」→「アプリ」→「アプリ実行エイリアス」で `python.exe` / `python3.exe` をオフにする |
| `error: externally-managed-environment`（pip のとき） | 仮想環境の外の Python が動いている。`python check_setup.py` の1行目を確認する。`(venv)` と出ているのに直らないときは、`python` に別名（alias）が付いていることがある → `venv/bin/python -m pip install -r requirements.txt` のように venv の Python を直接指定する（`type python` で確認できる） |
| `[notice] A new release of pip is available` | 気にしなくてよい（エラーではない） |

すべての呼び出しは `code/logs/api_calls.jsonl` に記録されます（送った内容、返答、トークン数、かかった時間）。おかしな結果が出たときは、まずここを見ましょう。
