---
name: minecraft-gameplay
description: Windows上のMinecraftを画面から観察し、安全境界付きのPython APIで操作する。日本語で相談・記録し、シングルプレイのサバイバル攻略、採集、クラフト、探索、建築を行うときに使う。
license: Apache-2.0
---

# Minecraft gameplay

現在の画面から状態を判断し、ユーザーのゲーム内目標が達成されるまで自律的に進める。過去の記録や計画より新しい観察を優先する。

プレイ前に [game-rules.md](references/game-rules.md) を読む。入力は `runtime/input_boundary.py` の境界を通す。

## 操作方法

主な操作には、Astra向けのコード実行API `runtime/minecraft.py` を使う。Pythonのループ、条件分岐、画像処理、短い操作群を組み合わせられる。利用時に [runtime-api.md](references/runtime-api.md) を読む。

単発CLIが適する場合だけ [commands.md](references/commands.md) を、参照画像による決定的なチェック列が適する場合だけ [sequences.md](references/sequences.md) を読む。これらは必須手順ではない。

まず画面を取得し、ゲーム画面、GUI、ポーズ、死亡画面などを区別する。操作後は、行動の危険度、不確実性、予想外の変化に応じて再観察する。安全な既知経路と、戦闘・崖・未知GUIを同じ粒度で扱う必要はない。

セッションをまたぐ再開情報が必要なら、リポジトリ内のignore対象 `local-state/current.md` に、現在地、装備、危険、次の候補、最後に確認した画面状態だけを簡潔に保存する。

## 自律的な改善

境界内で目標達成に役立つなら、このskill、参照資料、操作・観察・分析コードを改善してよい。Minecraftが前面で動いている最中にコード編集へ移る場合は、入力を解放し、必要なら実画面でポーズを確認する。

変更後はruntimeのモックテストを実行する。入力境界を変更した場合は、その不変条件をテストで示す。ゲームやデスクトップへ接続できない場合は、回避策で境界を破らず、欠けている能力を具体的に報告する。
