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
- `game.hold_async(keys=(), buttons=(), seconds=..., dx=0, dy=0)`：`with` 内で同じ保持を非同期に実行し、同一セッションの撮影・解析と並行させる。
- `game.press(*keys, seconds=...)`：キーを短く押す。
- `game.look(dx, dy, seconds=...)`：視点を相対移動する。
- `game.click(x, y, button="left", seconds=...)`：現在のMinecraftクライアント内の座標をクリックする。
- `game.wait(seconds)`：入力せず、前面・停止条件を監視しながら待つ。
- `game.focus()`：選択済みMinecraftだけを前面化する。ユーザーが他アプリへ移動した後に無断で呼ばない。

座標はネイティブのゲームクライアント座標です。GUIが見えており、目的の項目を現在の画像から特定できる場合に使います。

## ループと観察

Python側で自由にループや条件分岐を構成できます。連続操作の長さは、地形、戦闘、GUI、画面解析の確度に応じて決めます。正常な既知経路では長く、危険または不明な状態では短くし、想定外の画像や停止例外が出たら再観察します。

画面状態を意味的に判定する処理はこの高層側へ置きます。`input_boundary.py` には、Minecraft外へ作用しないための機構だけを置きます。

## 入力保持と観察の並行実行

同一Minecraftセッション内の安全な非同期・並行動作は許可されています。`hold_async` は `with` に入ると入力用のワーカースレッドを起動し、呼び出し側を撮影・解析へ戻します。`frame()` と `capture()` は保持中にも使えます。画像を取得した後の解析は別スレッド等へ渡してもかまいません。複数の画面取得はAPI内で直列化されますが、入力の監視・解放はその待ち時間に依存しません。

```python
from minecraft import Minecraft
from survival_watch import SurvivalWatch
from pause_guard import ensure_game_menu

def main():
    # 生存HUDが見え、事前に足場を確認した通路で実行する例。
    with Minecraft() as raw:
        try:
            watch = SurvivalWatch(raw)
            with raw.hold_async(keys=("w",), seconds=1.2) as movement:
                while not movement.done():
                    watch.frame()  # 保持中の撮影と体力・炎の画像解析
                    raw.wait(.1)
                movement.result()  # 入力側の失敗も呼び出し側へ伝える
        finally:
            # 非同期スコープの解放完了後に通常のポーズ入力を送る。
            ensure_game_menu(raw)
            raw.capture("captures/observed-movement-paused.png")

if __name__ == "__main__":  # Windowsのwatchdog子プロセスから再実行しない
    main()
```

- `action.done()` は完了の有無、`action.result(timeout=...)` は完了待ちと結果・例外の取得です。`action.cancel()` は次の境界検査で解放するよう要求します。明示キャンセル後の `result()` は `input_boundary.ActionCancelled` を送出します。
- `with` の終了は、未完了の保持をキャンセルして入力ワーカーとwatchdogの終了を待ちます。正常に時間満了まで実行したい場合はスコープ内で `result()` を待ちます。解析の例外で抜けても解放され、撮影API自体の失敗も実行中の入力をキャンセルします。別スレッドへ渡した解析の例外は、その結果をスコープ内で受け取ってください。
- 非同期スコープ内の追加の `hold`、`press`、`look`、`click`、`focus` は競合として拒否されます。入力を切り替えるときは現在のスコープを抜け、解放完了後に次を送ります。キーとボタン、視点移動を同時に使う場合は1つの `hold_async` の引数で組み合わせます。
- `Minecraft` の外側のスコープも残った入力を停止してからmutexを返します。外側のスコープは開始したスレッドで閉じます。別の `Minecraft` インスタンスやCLIプロセスを並列の入力所有者にしません。
- 保持は正の有限時間を指定します。長い保持は従来と同じ安全leaseに分割され、lease間には解放・再取得があります。撮影・解析の遅延を理由に保持を無期限に延長しません。F8、永続stop、前面・HWND/PID・ポインター検査と独立watchdogは保持中も有効です。

取得画像は撮影時点の観察です。解析終了時点の状態と同じとは限らないため、次の判断には経過時間と新しい画面を考慮します。入力停止とゲーム内のポーズも別であり、コード編集や長い中断へ移る際は実画面でポーズを確認します。

## GUIと終了時のポーズ確認

インベントリ中のEscはインベントリを閉じるため、Escを1回送ったことだけではポーズを確認できません。現在の日本語・1920×1009・GUIスケール4の画面では、`pause_guard.ensure_game_menu(raw)` がタイトル画像を照合し、必要なら最大3回Escを送り、実際のゲームメニューを確認します。既にゲームメニューなら入力しません。異なる表示設定や確認できない画面では例外を返すので、画像から状態を確認してください。

この関数は非同期入力スコープを抜けた後、元の `Minecraft` インスタンスを使って呼びます。`SurvivalWatch` はインベントリやメニューで隠れたHUDを体力減少と誤認するため、GUIを開く操作から閉じ終わるまでは元のAPIを使い、生存HUDに戻ってから監視を再開してください。

## 採掘中の画面監視

`runtime/survival_watch.py` の `SurvivalWatch` は、現在確認している1920×1009のHUD配置に基づき、探索操作の前後で体力表示の減少と炎らしい画面の覆いを検知します。採掘中に溶岩へ触れた場合、次の移動まで検査を遅らせないための補助です。地形の安全を保証するものではなく、GUIやHUD設定変更後には使えません。

```python
from minecraft import Minecraft
from survival_watch import SurvivalWatch
from pause_guard import ensure_game_menu

def main():
    with Minecraft() as raw:
        try:
            game = SurvivalWatch(raw)  # 生存HUDが見えるプレイ中に作成
            game.hold(buttons=('left',), seconds=.5)
            game.frame()
        finally:
            ensure_game_menu(raw)  # 監視例外時も元のAPIで実際のメニューを確認する
            raw.capture('captures/exploration-paused.png')

if __name__ == '__main__':  # Windowsのwatchdog子プロセスから再実行させない
    main()
```

標準では1回の保持を1.5秒までにし、待機は0.2秒ごとに撮影します。この値は探索用の選択で、入力境界の制限ではありません。アラート後はポーズ画面から地形・体力・退路を再確認します。採掘対象だけでなく、掘った直後の流体や足場も観察してください。
