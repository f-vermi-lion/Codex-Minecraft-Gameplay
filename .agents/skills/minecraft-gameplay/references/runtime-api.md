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
