"""
環境の確認（APIは呼ばない）
  python check_setup.py
"""
import os
import sys

ok = True
print(f"Python {sys.version.split()[0]}", "OK" if sys.version_info >= (3, 10) else "← 3.10以上が必要です")
try:
    import openai
    print(f"openai ライブラリ {openai.__version__} OK")
except ImportError:
    print("openai ライブラリがありません → pip install -r requirements.txt"); ok = False
try:
    import yaml
    print(f"pyyaml ライブラリ {yaml.__version__} OK（第2回から使用）")
except ImportError:
    print("pyyaml ライブラリがありません → pip install -r requirements.txt"); ok = False
for var in ["OPENAI_API_KEY", "OPENAI_MODEL"]:
    v = os.environ.get(var)
    if v:
        shown = v[:7] + "..." if var == "OPENAI_API_KEY" else v
        print(f"{var} = {shown} OK")
    else:
        print(f"{var} が設定されていません"); ok = False
print("\n準備完了です。" if ok else "\n上の指示に従って設定してください。")
