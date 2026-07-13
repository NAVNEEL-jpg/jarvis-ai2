import webbrowser
import subprocess
import os
import ctypes

def open_url(url):
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opening {url}"

def change_volume(direction, steps=5):
    # VK_VOLUME_UP = 0xAF, VK_VOLUME_DOWN = 0xAE
    key_code = 0xAF if direction == "up" else 0xAE
    for _ in range(steps):
        ctypes.windll.user32.keybd_event(key_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key_code, 0, 2, 0)
    return f"Adjusted volume {direction}, Sir."

def set_system_volume(percentage):
    percentage = max(0, min(100, percentage))
    # Each key press is 2% volume. So we need 50 down commands to guarantee 0% first.
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_UP = 0xAF
    for _ in range(50):
        ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
    steps = percentage // 2
    for _ in range(steps):
        ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
    return f"I have set the system volume to {percentage} percent, Sir."

def toggle_mute(action="toggle"):
    # VK_VOLUME_MUTE = 0xAD, VK_VOLUME_UP = 0xAF, VK_VOLUME_DOWN = 0xAE
    if action == "unmute":
        # Force unmute by toggling volume up and down
        ctypes.windll.user32.keybd_event(0xAF, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0xAF, 0, 2, 0)
        ctypes.windll.user32.keybd_event(0xAE, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0xAE, 0, 2, 0)
        return "I have unmuted the system volume, Sir."
    elif action == "mute":
        # Since we don't know the exact mute state, we toggle it
        ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
        return "I have muted the system volume, Sir."
    else:
        ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
        return "Toggled the system mute status, Sir."

def shutdown_pc():
    subprocess.Popen(["shutdown", "/s", "/t", "5"])
    return "Shutting down the system in five seconds. Goodbye, Sir."

def reboot_pc():
    subprocess.Popen(["shutdown", "/r", "/t", "5"])
    return "Rebooting the systems in five seconds, Sir."

def open_app(name_or_path):
    if os.path.exists(name_or_path) or "\\" in name_or_path or "/" in name_or_path or name_or_path.endswith(".exe"):
        try:
            subprocess.Popen(name_or_path)
            return f"Opening {os.path.basename(name_or_path)}."
        except Exception as e:
            return f"Could not launch path: {e}"

    common_apps = {
        "chrome": "chrome.exe",
        "browser": "chrome.exe",
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "powershell": "powershell.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "task manager": "taskmgr.exe",
        "settings": "start ms-settings:"
    }

    app_query = name_or_path.lower().strip()
    
    if app_query in common_apps:
        target = common_apps[app_query]
        try:
            if target.startswith("start "):
                subprocess.Popen(target, shell=True)
            else:
                subprocess.Popen(target)
            return f"Opening {app_query}."
        except Exception:
            pass

    try:
        start_menu_paths = [
            os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "Microsoft\\Windows\\Start Menu\\Programs"),
            os.path.join(os.environ.get("APPDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs")
        ]
        
        matches = []
        for base_path in start_menu_paths:
            if not os.path.isdir(base_path):
                continue
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    if file.lower().endswith(".lnk") and app_query in file.lower():
                        matches.append(os.path.join(root, file))
        
        if matches:
            os.startfile(matches[0])
            app_name = os.path.splitext(os.path.basename(matches[0]))[0]
            return f"Opening {app_name}."
    except Exception as e:
        print(f"Error searching start menu: {e}")

    try:
        subprocess.Popen(app_query, shell=True)
        return f"Attempting to launch {app_query}."
    except Exception as e:
        return f"Could not find or open application '{name_or_path}': {e}"


# ── VirtualBox Automation ───────────────────────────────────────────────────

def _run_vbox_cmd(args):
    vbox_path = "VBoxManage"
    default_path = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
    if os.path.exists(default_path):
        vbox_path = default_path
        
    try:
        cmd = [vbox_path] + args
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
        return out
    except Exception as e:
        return f"VirtualBox error: {e}"

def list_vms():
    out = _run_vbox_cmd(["list", "vms"])
    if "VirtualBox error" in out:
        return "VirtualBox is not installed or VBoxManage is not accessible."
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if not lines:
        return "There are no virtual machines configured, Sir."
    names = []
    for l in lines:
        parts = l.split('"')
        if len(parts) >= 2:
            names.append(parts[1])
    return "Configured virtual machines: " + ", ".join(names)

def list_running_vms():
    out = _run_vbox_cmd(["list", "runningvms"])
    if "VirtualBox error" in out:
        return "VirtualBox is not installed or VBoxManage is not accessible."
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if not lines:
        return "No virtual machines are currently running, Sir."
    names = []
    for l in lines:
        parts = l.split('"')
        if len(parts) >= 2:
            names.append(parts[1])
    return "Currently running virtual machines: " + ", ".join(names)

def start_vm(name):
    out = _run_vbox_cmd(["startvm", name, "--type", "headless"])
    if "successfully started" in out.lower() or "started" in out.lower():
        return f"Virtual machine {name} has been started headlessly, Sir."
    return f"Could not start virtual machine: {out}"

def stop_vm(name):
    out = _run_vbox_cmd(["controlvm", name, "savestate"])
    if "100%" in out or "state saved" in out.lower() or "saved" in out.lower():
        return f"Virtual machine {name} state has been saved, Sir."
    return f"Could not save state for virtual machine: {out}"

def sleep_pc():
    try:
        # Parameter 1: Suspend (0 for Suspend, 1 for Hibernate)
        # Parameter 2: Force (1 to force immediately)
        # Parameter 3: DisableWake (0 to allow wake events)
        ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        return "Putting the system to sleep, Sir."
    except Exception as e:
        return f"Failed to sleep: {e}"

def hibernate_pc():
    try:
        # Parameter 1: Suspend (1 for Hibernate)
        ctypes.windll.powrprof.SetSuspendState(1, 1, 0)
        return "Hibernating the system, Sir."
    except Exception as e:
        subprocess.Popen(["shutdown", "/h"])
        return "Hibernating the system, Sir."
