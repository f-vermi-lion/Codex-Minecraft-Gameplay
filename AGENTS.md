# Working in this repository

## このフォークの用途

ユーザーへの応答・計画・記録は日本語。目的は **シングルプレイ、サバイバル、難易度ノーマルで、ポーズを使いながらエンダードラゴン討伐を目指す** こと。
ゲームプレイ前に [日本語の運用方針](agents/skills/minecraft-gameplay/references/survival-ja.md) を読む。書庫は兄弟ディレクトリ `../Codexs-obsidian-vault`。その `AGENTS.md` と `P文書/Minecraftエンドラ攻略.md` を読み、現在地・次の一手・調査結果を引き継ぐ。過去の記録より新しいゲーム画面を優先する。

操作対象はこのリポジトリのゲーム操作用コードと生成物、指定書庫、Minecraft、Codexバックエンドの必要な機能のみ。ネット調査はCodexのWeb検索・取得を使い、デスクトップブラウザや無関係のアプリ・コネクター・個人ファイルを操作しない。ゲーム入力は同梱Pythonアダプターだけを使う。Obsidianは必ず `obsidian vault="Codexs-obsidian-vault" ...` と対象ノートの `path=` を指定する。書庫のプラグイン設定、任意コード実行、他Vaultには触れない。

プレイ用には [README](README.md) の専用起動を使う。権限不足をFull access、独自の常駐サーバー、別の入力APIで回避しない。通常のセットアップで解決しない場合は具体的な制約を報告する。プレイ中は操作コード・安全チェックを自己改変しない。以下の開発手順はセットアップや明示された改修に適用する。

For a gameplay task, read [agents/skills/minecraft-gameplay/SKILL.md](agents/skills/minecraft-gameplay/SKILL.md). Resolve the current game state from fresh observations.

For first use, follow the Quick start and Manual setup in [README.md](README.md). Run `py -3 scripts/setup_repository.py` from the repository root with a suitable Windows Python interpreter, then set up the runtime requirements and run the mock tests within the task's permissions. Setup creates local Git ignore rules and registers the skill for Codex's skill picker; the visible `agents/` directory remains the canonical source. If registration is unavailable, these project instructions still route gameplay to the visible skill. Verify window detection and inspect a fresh screenshot before attempting gameplay. Report any missing local tool or desktop access clearly.

The runtime and its mock-only tests are in `agents/skills/minecraft-gameplay/runtime`. Run `python -m unittest -q` from that directory with Pillow installed after changing controller or sequence behavior. Test execution must remain independent of a running game.

Keep reusable workflow instructions and schema guidance in the visible skill and its references. Rerun setup after changing the skill metadata or `gitignore.template`. Keep user captures, custom plans, reports, generated `.agents/` registration, and local configuration outside the public source list. The package builder in `scripts/package_gameplay.py` is the authoritative release allowlist. Browser uploads must use that source list or a fresh source copy; Git ignore rules do not filter files dragged into a browser.
