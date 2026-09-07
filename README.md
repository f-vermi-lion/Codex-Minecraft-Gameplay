# Codex Minecraft Gameplay — 日本語サバイバル用フォーク

**Codexが画面を見て判断し、Windowsのキー・マウス入力でMinecraftを操作する道具**です。Minecraft本体、AIモデル、ワールド、自動攻略ボットは含みません。ゲームメモリは読まず、スクリーンショットと通常の操作を使います。

このフォークは、日本語で相談・ネット調査・Obsidianへの記録をしながら、**ポーズあり／シングルプレイ／サバイバル／ノーマルでエンダードラゴン討伐を目指す**運用にしています。攻略成功や完全自動化を保証するものではありません。

## 全体の構成

| 場所 | 役割 |
| --- | --- |
| `AGENTS.md` | Codex向けの入口と操作対象の制限 |
| `agents/skills/minecraft-gameplay/SKILL.md` | 画面観察→短い操作→確認という基本手順 |
| `agents/skills/minecraft-gameplay/references/survival-ja.md` | 日本語・ポーズ・攻略段階・書庫への引き継ぎ |
| `agents/skills/minecraft-gameplay/runtime/minecraft_control.py` | ウィンドウ検出、キャプチャ、最長5秒の入力、緊急停止 |
| `agents/skills/minecraft-gameplay/runtime/minecraft_sequence.py` | 画像チェック付きの短い操作列（最大32手・30秒） |
| `scripts/start_gameplay.py` | 作業場所・検索・権限を指定して専用Codexセッションを開始 |
| `../Codexs-obsidian-vault/P文書/Minecraftエンドラ攻略.md` | 目的と方針。書庫の「スケジュール → 当面継続」からたどる入口 |
| `../Codexs-obsidian-vault/Minecraft攻略の現在地.md` | 最新の再開情報と、後で役立つ判断・調査の記録 |

既存の操作コード・テスト・配布用スクリプトを再利用しています。変更は日本語運用の追加、専用起動、ゲーム外クリックの抑止です。元の著作権表示とApache-2.0ライセンスは保持しています。

## Quick start / 最初の準備

Windows PythonとPillow、Codex CLI、Minecraft、Obsidian CLIを使います。Java版の通常のシングルプレイを想定します。既存のPythonにPillowがあれば再インストール不要です。

1. このリポジトリと `Codexs-obsidian-vault` を同じ親フォルダに置きます。このPCでは `D:\Codex` です。
2. Minecraftを通常権限で起動し、チートなし・サバイバル・ノーマルのシングルプレイワールドに入り、Escでポーズします。LANには公開しません。既存ワールドは削除しません。
3. Obsidianで `Codexs-obsidian-vault` を開き、設定→一般のCLIを有効にします。別のアプリがゲーム画面を覆わないようにします。
4. 初回だけ、リポジトリのルートでセットアップとテストを行います。

```powershell
Set-Location D:\Codex\Codex-Minecraft-Gameplay
py -3 scripts/setup_repository.py
Push-Location agents/skills/minecraft-gameplay/runtime
python -m unittest -q
Pop-Location
```

5. ゲーム用の新しいCodexセッションを起動します。

```powershell
python scripts/start_gameplay.py
```

起動引数を確認するだけなら `python scripts/start_gameplay.py --check` を使えます。組織設定などで拒否される場合は、ポリシーを変更して回避せず原因を確認してください。

起動後、Codexは書庫の記録を読み、`status` と新しいゲーム画像から現在の状態を確認します。まだ記録ノートがない別環境では、指定書庫内に攻略用ノートを作成します。最初は短い移動・視点変更で操作感を確かめます。現在開いているCodexの会話には起動引数の設定は遡って適用されません。

## 操作範囲を狭める仕組みと限界

専用起動は `workspace-write` と `on-request` を使い、リポジトリを作業場所、指定書庫を追加の書き込み先にします。継承された追加書き込み先リストを空にしてから書庫だけを追加します。ネットはCodexの内蔵Web検索を有効にし、シェル側のネット許可は無効にします。グローバル設定は書き換えません。

画面操作には実際のデスクトップへの接続が必要なので、公式の互換設定 `windows.sandbox_private_desktop=false` をこの起動だけ指定します。**ファイル・ネットワークのサンドボックスは維持しますが、GUIの隔離は弱くなります。** 管理設定などがこれを拒む場合や、それでもゲーム・Obsidianに接続できない場合は停止して説明します。Full accessや独自の操作ブリッジには切り替えません。[公式Windows資料](https://learn.chatgpt.com/docs/windows/windows-sandbox)、[設定リファレンス](https://learn.chatgpt.com/docs/config-file/config-reference)

ゲーム入力にはウィンドウ・プロセスの確認、前面確認、時間上限、ゲーム外クリック抑止、キー解放、watchdogが働きます。Codexの指示でも無関係のファイル・アプリ・連携ツールに触れないよう制限しています。ただし、**この構成は読み取り先や全ツールを完全に隔離する許可リストではありません**。Windows入力はグローバルであり、判定と送信の隙間も残ります。不要なアプリを閉じ、ゲームを単独で見える状態にすると誤操作の機会を減らせます。追加の恒久許可を求められたら、汎用Python／PowerShell全体を許可する形にはしません。

## ポーズと中断

調査・長考・記録・返答待ちの前にポーズメニューを確認します。インベントリを開いただけ、キーを離しただけではポーズになりません。Escは状態によって再開にもなるため、画面確認なしの自動連打はしません。Bedrock版やMOD環境でポーズが効くか不明なら、版を確認してから進めます。

- `F8`を押し続ける、またはゲームからフォーカスを外すと入力を中断できます。
- 永続停止: runtimeで `python minecraft_control.py stop`。
- `stop`やF8はゲーム自体をポーズしません。必要なら手動でEscを押してください。
- ユーザーが中断した後は、再開指示まで自動再開しません。

詳細は [日本語の運用方針](agents/skills/minecraft-gameplay/references/survival-ja.md)、コマンドは [commands](agents/skills/minecraft-gameplay/references/commands.md)、操作列は [sequences](agents/skills/minecraft-gameplay/references/sequences.md) を参照してください。

## Manual setup / 不足している場合

Python環境がなければ先にWindows用Pythonを用意します。Pillowだけが不足している場合はruntime内で仮想環境を作ります。

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest -q
```

以後のゲーム操作もそのPythonを使います。Obsidian CLIの接続にはObsidian本体が必要です。[公式CLI手順](https://obsidian.md/help/cli)

`Unable to enumerate game windows` は実行環境の問題として扱い、「ゲームが閉じている」と判断しません。`games: []` はその実行環境で候補が見つからないという結果です。まずMinecraftのゲーム画面が起動済みか確認します。デスクトップアクセスが不足している場合はその旨を報告します。

## 開発・配布

入力動作を変更したらruntimeで `python -m unittest -q` を実行します。実ゲームを操作しないモックテストです。スキルのメタデータを変更したら `py -3 scripts/setup_repository.py` を再実行します。

配布ZIPは `python scripts/package_gameplay.py` で作成します。明示したソースのみを含み、書庫・画像・個人用計画・設定は含めません。手動でブラウザへフォルダをアップロードする場合、Gitのignoreでは個人ファイルを除外できない点に注意してください。
