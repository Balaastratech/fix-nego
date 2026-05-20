Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class InputStateReader {
    [DllImport("user32.dll")]
    public static extern short GetAsyncKeyState(int vKey);
}
"@

$vkSpace   = 0x20  # VK_SPACE  - immediate hold-to-ask
$vkLButton = 0x01  # VK_LBUTTON - 3-second hold-to-ask

$spaceLastPressed = $false
$mouseLastPressed = $false
$mousePressTime   = [DateTime]::MinValue
$mouseHoldFired   = $false
$holdThresholdMs  = 3000

while ($true) {
    $spacePressed = ([InputStateReader]::GetAsyncKeyState($vkSpace) -band 0x8000) -ne 0
    $mousePressed = ([InputStateReader]::GetAsyncKeyState($vkLButton) -band 0x8000) -ne 0

    # Space key: immediate hold-to-ask activation
    if ($spacePressed -ne $spaceLastPressed) {
        if ($spacePressed) {
            Write-Output "space_down"
        } else {
            Write-Output "space_up"
        }
        [Console]::Out.Flush()
        $spaceLastPressed = $spacePressed
    }

    # Left mouse: activate hold-to-ask after 3 seconds
    if ($mousePressed -ne $mouseLastPressed) {
        if ($mousePressed) {
            $mousePressTime = [DateTime]::UtcNow
            $mouseHoldFired = $false
        } else {
            if ($mouseHoldFired) {
                Write-Output "mouse_up"
                [Console]::Out.Flush()
            }
            $mousePressTime = [DateTime]::MinValue
            $mouseHoldFired = $false
        }
        $mouseLastPressed = $mousePressed
    }

    # Emit hold start once 3 s threshold crossed
    if ($mousePressed -and (-not $mouseHoldFired) -and ($mousePressTime -ne [DateTime]::MinValue)) {
        $elapsed = ([DateTime]::UtcNow - $mousePressTime).TotalMilliseconds
        if ($elapsed -ge $holdThresholdMs) {
            Write-Output "mouse_hold_start"
            [Console]::Out.Flush()
            $mouseHoldFired = $true
        }
    }

    Start-Sleep -Milliseconds 30
}
