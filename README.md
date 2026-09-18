# Codex Minecraft Gameplay — Astra向け日本語サバイバル環境

Codexが画面を観察し、Windowsのキー・マウス入力でMinecraftを操作するためのリポジトリです。Minecraft本体、AIモデル、ワールド、自動攻略ボットは含みません。ゲームメモリではなく、スクリーンショットと通常の入力を使います。

設計方針は、**Minecraft外とリポジトリ外への作用を低層で防ぎ、その内側ではエージェントが攻略・分析・ツール改良を自律的に行う**ことです。シングルプレイ／サバイバル／ノーマルでエンダードラゴン討伐を目指します。

## 構成

| 場所 | 役割 |
| --- | --- |
| `AGENTS.md` | 目的、外部境界、境界内の裁量 |
| `.agents/skills/minecraft-gameplay/SKILL.md` | Minecraft能力の短い入口 |
| `references/game-rules.md` | 守るゲームルール |
| `references/runtime-api.md` | Astra向けコード実行API |
| `runtime/input_boundary.py` | Minecraft限定のWin32入力境界 |
| `runtime/minecraft.py` | ループ・条件分岐・画像分析から使う高層API |
| `runtime/minecraft_control.py` | 既存単発CLIの互換入口 |
| `runtime/minecraft_sequence.py` | 必要な場合だけ使う画像チェック付き操作列 |
| `runtime/AGENTS.md` | runtime変更時に守る不変条件 |
| `scripts/start_gameplay.py` | リポジトリ限定権限でCodexを起動 |

エージェントは必要に応じて、skill、指示、操作、観察、画像分析、計画、記録用ツールを変更・追加できます。安全性は特定の実装を変更禁止にするのではなく、`input_boundary.py` の性質とモックテストで維持します。

## Quick start

必要なものはWindows Python、Pillow、Codex CLI、Minecraftです。Java版の通常のシングルプレイを想定します。

1. Minecraftを通常権限で起動し、チートなし・サバイバル・ノーマルのシングルプレイワールドに入ります。
2. リポジトリのルートでセットアップし、モックテストを実行します。

```powershell
Set-Location D:\Codex\Codex-Minecraft-Gameplay
py -3 scripts/setup_repository.py
Push-Location .agents/skills/minecraft-gameplay/runtime
py -3 -m pip install -r requirements.txt
py -3 -m unittest -q
Pop-Location
```

3. 専用Codexセッションを開始します。

```powershell
python scripts/start_gameplay.py
```

`python scripts/start_gameplay.py --check` で起動引数だけ確認できます。

## コード実行型の操作

主役は構造化された単発アクションではなく、`minecraft.py` を使うPythonコードです。

```python
from minecraft import Minecraft

with Minecraft(focus=True) as game:
    image = game.frame()
    game.hold(keys=("w",), seconds=8)
    result = game.frame()
```

`hold` は長い論理操作を、低層の短い安全leaseへ自動分割します。総手数や総操作時間には固定上限を置きません。Python側で観察、条件分岐、ループ、画像処理を構成できます。詳しくは [runtime API](.agents/skills/minecraft-gameplay/references/runtime-api.md) を参照してください。

単発診断には [controller CLI](.agents/skills/minecraft-gameplay/references/commands.md)、宣言的な画像チェックが役立つ場合には [sequence runner](.agents/skills/minecraft-gameplay/references/sequences.md) も使えます。

## 安全境界

専用起動は `workspace-write` を使い、追加の書き込み先を与えません。シェル側のネットワークは無効のまま、CodexのWeb検索だけを有効にします。プレイ状態、キャプチャ、計画、報告はリポジトリ内のignore対象へ置きます。

実デスクトップへ接続するため、起動時だけ `windows.sandbox_private_desktop=false` を指定します。ファイルとネットワークのサンドボックスは維持されます。

低層入力境界は次を強制します。

- Minecraftのタイトル、実行プロセス、HWND、PIDを照合
- 前面状態と最小化状態を入力中も継続確認
- Minecraftクライアント外や他ウィンドウ上のクリックを拒否
- F8、stopファイル、フォーカス喪失で停止
- 例外時のキー・ボタン解放と独立watchdog
- mutexによる単一入力所有者

Windows入力には検査と送信の間の競合があり、完全なOS隔離ではありません。Minecraft以外のウィンドウを重ねないことが、誤操作の機会をさらに減らします。

## 中断

- F8を押し続けるか、Minecraftからフォーカスを外すと現在の入力を中断できます。
- 永続停止はruntimeで `python minecraft_control.py stop`。
- `stop` は入力を止めますが、ゲーム自体をポーズしません。
- ユーザーによる意図的中断後は、再開指示までフォーカスを奪い返しません。
- watchdog由来の停止は、状態を確認したうえで `reset-stop` し、自律復旧できます。

## 開発・配布

runtime変更後は、同ディレクトリで次を実行します。

```powershell
python -m unittest -q
```

skillはCodex標準位置の `.agents/skills/minecraft-gameplay` が正本であり、登録用コピーは生成しません。配布ZIPは `python scripts/package_gameplay.py` で作成し、明示allowlistのソースだけを含めます。
