# Code-execution runtime API

`runtime/minecraft.py` は、PythonコードからMinecraftを観察・操作する主APIです。低層の `input_boundary.py` が、送信のたびに対象ウィンドウ、プロセス、前面状態、停止状態、ポインター位置を検査します。

## 基本形

runtimeディレクトリを作業場所にして、必要な処理をPythonスクリプトとして書きます。

```python
from minecraft import Minecraft

with Minecraft(focus=True) as game:
    before = game.frame()
    game.hold(keys=("w",), seconds=8)
    after = game.frame()
    after.save("captures/after.png")
```

`hold` は長い操作を低層の安全leaseへ自動分割します。固定の総時間・手数上限はありません。各分割の間も前面状態と停止信号を再確認します。

## 利用できる操作

- `game.frame()`：ネイティブ解像度のPillow画像を返す。
- `game.capture(path, max_width=...)`：画像を保存し、寸法とパスを返す。
- `game.hold(keys=(), buttons=(), seconds=..., dx=0, dy=0)`：キー、ボタン、相対視点移動を組み合わせる。
- `game.press(*keys, seconds=...)`：キーを短く押す。
- `game.look(dx, dy, seconds=...)`：視点を相対移動する。
- `game.click(x, y, button="left", seconds=...)`：現在のMinecraftクライアント内の座標をクリックする。
- `game.wait(seconds)`：入力せず、前面・停止条件を監視しながら待つ。
- `game.focus()`：選択済みMinecraftだけを前面化する。ユーザーが他アプリへ移動した後に無断で呼ばない。

座標はネイティブのゲームクライアント座標です。GUIが見えており、目的の項目を現在の画像から特定できる場合に使います。

## ループと観察

Python側で自由にループや条件分岐を構成できます。連続操作の長さは、地形、戦闘、GUI、画面解析の確度に応じて決めます。正常な既知経路では長く、危険または不明な状態では短くし、想定外の画像や停止例外が出たら再観察します。

画面状態を意味的に判定する処理はこの高層側へ置きます。`input_boundary.py` には、Minecraft外へ作用しないための機構だけを置きます。

## 採掘中の画面監視

`runtime/survival_watch.py` の `SurvivalWatch` は、現在確認している1920×1009のHUD配置に基づき、探索操作の前後で体力表示の減少と炎らしい画面の覆いを検知します。採掘中に溶岩へ触れた場合、次の移動まで検査を遅らせないための補助です。地形の安全を保証するものではなく、GUIやHUD設定変更後には使えません。

```python
from minecraft import Minecraft
from survival_watch import SurvivalWatch

def main():
    with Minecraft() as raw:
        try:
            game = SurvivalWatch(raw)  # 生存HUDが見えるプレイ中に作成
            game.hold(buttons=('left',), seconds=.5)
            game.frame()
        finally:
            raw.press('f3', 'esc')  # 監視例外時も元のAPIでポーズする
            raw.capture('captures/exploration-paused.png')

if __name__ == '__main__':  # Windowsのwatchdog子プロセスから再実行させない
    main()
```

標準では1回の保持を1.5秒までにし、待機は0.2秒ごとに撮影します。この値は探索用の選択で、入力境界の制限ではありません。アラート後はポーズ画面から地形・体力・退路を再確認します。採掘対象だけでなく、掘った直後の流体や足場も観察してください。
