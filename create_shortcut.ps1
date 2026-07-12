$WshShell = New-Object -ComObject WScript.Shell
$Desktop = [System.Environment]::GetFolderPath('Desktop')
$ShortcutPath = "$Desktop\Jarvis AI.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = 'd:\jarvis ai2\run_jarvis.bat'
$Shortcut.WorkingDirectory = 'd:\jarvis ai2'
$Shortcut.Description = 'Start Jarvis Voice Assistant'
$Shortcut.WindowStyle = 1
$Shortcut.IconLocation = 'd:\jarvis ai2\jarvis_icon.ico, 0'
$Shortcut.Save()

# Set Run as Administrator flag in the .lnk file
$bytes = [System.IO.File]::ReadAllBytes($ShortcutPath)
$bytes[21] = $bytes[21] -bor 0x20
[System.IO.File]::WriteAllBytes($ShortcutPath, $bytes)

Write-Host "Shortcut updated with JARVIS icon and configured to run as Administrator."
