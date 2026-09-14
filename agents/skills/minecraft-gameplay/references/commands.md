# Controller command reference

Run these commands from the skill's `runtime` directory using Windows Python with Pillow. Examples assume a local virtual environment:

```powershell
$mcPython = (Resolve-Path '.\.venv\Scripts\python.exe').Path
& $mcPython .\minecraft_control.py --help
```

## Window and observation

```powershell
& $mcPython .\minecraft_control.py status
& $mcPython .\minecraft_control.py capture --focus --capture captures\current.png --max-width 7680
```

`status` returns matching windows and stop state without sending input. Window detection checks the title and process executable. If there is more than one match, add `--hwnd NUMBER` to `capture` or `act`; obtain the number from current status output. Handles change when a game restarts.

`--focus` asks Windows to focus the game. Without it, Minecraft must already be foreground. Restore a minimized window manually. The process executing the adapter must be able to access the game's desktop; a private desktop or incompatible privilege level can prevent enumeration, input, or capture.

Capture output contains `source_size` (native client dimensions), `image_size` (saved dimensions), and the saved file path. The default maximum width is 1600. For sequence reference images, use `--max-width 7680` to preserve supported native dimensions. The captured rectangle must remain visible; overlapping windows can appear in its pixels.

## Individual actions

`act` combines supported keys, mouse buttons, and relative motion for a bounded hold. Inspect the game before choosing an action and inspect its result afterward. The following are independent command-shape examples, not a sequence to paste and run together.

```powershell
# Walk a short distance after checking the path.
& $mcPython .\minecraft_control.py act --focus --keys w --seconds 0.2 --capture captures\move.png

# Move and jump over an observed obstacle.
& $mcPython .\minecraft_control.py act --focus --keys w space --seconds 0.3 --capture captures\jump.png

# Look using relative mouse deltas; calibrate the resulting angle.
& $mcPython .\minecraft_control.py act --focus --dx 40 --dy 10 --seconds 0.15 --capture captures\look.png

# Mine a visibly targeted block with the selected tool.
& $mcPython .\minecraft_control.py act --focus --buttons left --seconds 0.5 --capture captures\mine.png

# Use the selected item against a visibly inspected target.
& $mcPython .\minecraft_control.py act --focus --buttons right --seconds 0.1 --capture captures\use.png
```

Durations are between 0.02 and 5 seconds. `--settle` waits between 0 and 2 seconds after release before capture; it defaults to 0.15. Each relative mouse total is an integer between -2000 and 2000. Motion is distributed over the hold, so changing the view and holding attack at the same time sweeps across targets.

Supported key names:

```text
w a s d e q f t h space shift ctrl esc enter tab
f3 f5 f6 up down left right 1 2 3 4 5 6 7 8 9
```

Buttons: `left`, `right`, `middle`. Names assume matching in-game bindings; the adapter does not remap the user's controls. `F8` is the interrupt key. Individual actions do not inspect inventory, hazards, or item identity.

画面上に `F3+F6` の案内が出ている場合は、`--keys f3 f6` でデバッグ表示の設定を開ける。操作後は実際の画面を確認する。F6も通常のキーと同じ停止・前面確認・キー解放処理を通る。

## Menu coordinates

Use `--at X Y` only when a menu is visibly open. The point uses native game-client pixels. Inspect the desired slot or button rather than reusing example coordinates.

For a point picked from a resized image, calculate:

```text
native_x = round(displayed_x * source_width / image_width)
native_y = round(displayed_y * source_height / image_height)
```

Set the coordinates from the actual observed target:

```powershell
# $menuX and $menuY must be established from the current screenshot.
& $mcPython .\minecraft_control.py act --focus --at $menuX $menuY --buttons left --seconds 0.08 --capture captures\menu-result.png
```

`--at` cannot be combined with nonzero `--dx` or `--dy`. For a drag, first position the pointer with a separate `--at` action, then perform the held-button relative movement. Recheck layout and cursor state afterward.

## Interruption and reports

Hold F8, change focus, or issue a persistent stop:

```powershell
& $mcPython .\minecraft_control.py stop
# For a confirmed runtime timeout after checking the target and foreground state:
& $mcPython .\minecraft_control.py reset-stop
```

A stop file alone does not identify a user interruption: a sequence watchdog can also create it after a timeout. Follow [中断・エラーからの復旧](survival-ja.md#中断エラーからの復旧) to distinguish intentional user stops from runtime errors. For a confirmed timeout, no additional permission is needed to clear the flag and inspect the foreground game; inspect a fresh screenshot before sending gameplay input.

The adapter checks window identity and focus, refuses conflicting physical key/button state, and uses a mutex to prevent overlapping actions. It releases inputs in cleanup and uses a separate watchdog as backup. Cleanup depends on Windows accepting the release events.

This fork also checks that the pointer is inside the selected game client and over that window (or a child) before pressing a mouse button and during held-button motion. A pointer outside the client, on the title bar, or over another window stops the action. Releases still run on abort. These checks reduce accidental clicks; Windows input remains global and checks are not an isolation boundary.

Commands emit JSON. Failures produce a nonzero exit status. A completed action describes input delivery, not game success. Save observations under `captures/`; paths and screen contents in generated output can identify the local user and are not release assets.

The checked runner is documented in [sequences.md](sequences.md).
