import ctypes
import os
import subprocess
import time
import requests
import datetime

# ── Window Control ──

def get_active_window_title() -> str:
    """Get the title of the currently focused/active window."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    return "Unknown"

def minimize_active_window() -> str:
    """Minimize the currently active window."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if hwnd:
        # SW_MINIMIZE = 6
        ctypes.windll.user32.ShowWindow(hwnd, 6)
        return "Active window minimized, Sir."
    return "No active window found."

def maximize_active_window() -> str:
    """Maximize the currently active window."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if hwnd:
        # SW_MAXIMIZE = 3
        ctypes.windll.user32.ShowWindow(hwnd, 3)
        return "Active window maximized, Sir."
    return "No active window found."

def restore_active_window() -> str:
    """Restore the active window to its normal size."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if hwnd:
        # SW_RESTORE = 9
        ctypes.windll.user32.ShowWindow(hwnd, 9)
        return "Active window restored, Sir."
    return "No active window found."

def close_active_window() -> str:
    """Close the currently active window."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if hwnd:
        # WM_CLOSE = 0x0010
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
        return "Closing active window, Sir."
    return "No active window found."

def always_on_top(enable: bool = True) -> str:
    """Set or remove the 'always on top' flag for the active window."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if hwnd:
        # HWND_TOPMOST = -1, HWND_NOTOPMOST = -2
        # SWP_NOSIZE = 1, SWP_NOMOVE = 2
        hwnd_insert = -1 if enable else -2
        ctypes.windll.user32.SetWindowPos(hwnd, hwnd_insert, 0, 0, 0, 0, 1 | 2)
        status = "enabled" if enable else "disabled"
        return f"Always on top {status} for this window, Sir."
    return "No active window found."

def show_desktop() -> str:
    """Minimize all windows to show the desktop."""
    import keyboard
    keyboard.send("windows+d")
    return "Showing desktop, Sir."

def snap_active_window(direction: str) -> str:
    """Snap the active window. direction can be: 'left', 'right', 'up', 'down'."""
    import keyboard
    if direction == "left":
        keyboard.send("windows+left")
    elif direction == "right":
        keyboard.send("windows+right")
    elif direction == "up":
        keyboard.send("windows+up")
    elif direction == "down":
        keyboard.send("windows+down")
    return f"Active window snapped {direction}, Sir."

def focus_window_by_title(title: str) -> str:
    """Find and focus a window matching a specific title substring."""
    cmd = f"""
    $wshell = New-Object -ComObject wscript.shell;
    $proc = Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}} | Select-Object -First 1;
    if ($proc) {{
        $wshell.AppActivate($proc.Id)
        "Focused window: " + $proc.MainWindowTitle
    }} else {{
        "NotFound"
    }}
    """
    try:
        out = subprocess.check_output(["powershell", "-Command", cmd]).decode().strip()
        if "NotFound" in out or not out:
            return f"I couldn't find a window with title containing '{title}', Sir."
        return f"Focused window containing '{title}', Sir."
    except Exception as e:
        return f"Failed to focus window: {e}"


# ── Mouse Control ──

def move_mouse_to(x: int, y: int) -> str:
    """Move the mouse cursor to specific screen coordinates (x, y)."""
    ctypes.windll.user32.SetCursorPos(x, y)
    return f"Mouse cursor moved to {x}, {y}, Sir."

def click_mouse(button: str = "left", click_count: int = 1) -> str:
    """Click the mouse. button can be 'left', 'right', or 'middle'. click_count can be 1 or 2."""
    if button == "right":
        down, up = 0x0008, 0x0010
    elif button == "middle":
        down, up = 0x0020, 0x0040
    else:
        down, up = 0x0002, 0x0004
        
    for _ in range(click_count):
        ctypes.windll.user32.mouse_event(down, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(up, 0, 0, 0, 0)
        if click_count > 1:
            time.sleep(0.1)
            
    click_str = "Double clicked" if click_count == 2 else f"Clicked {button} button"
    return f"{click_str}, Sir."

def scroll_mouse(direction: str, amount: int = 120) -> str:
    """Scroll the mouse wheel. direction can be 'up' or 'down'."""
    val = amount if direction == "up" else -amount
    ctypes.windll.user32.mouse_event(0x0800, 0, 0, val, 0)
    return f"Scrolled mouse wheel {direction}, Sir."


# ── Keyboard Control ──

def type_text(text: str) -> str:
    """Type the specified text at the current cursor position."""
    import keyboard
    keyboard.write(text)
    return f"I have typed: {text}, Sir."

def press_key_combination(keys: str) -> str:
    """Press a key or combination of keys. e.g., 'ctrl+c', 'ctrl+v', 'alt+tab', 'enter', 'escape'."""
    import keyboard
    keyboard.send(keys)
    return f"Pressed key combination {keys}, Sir."


# ── Clipboard Control ──

def set_clipboard_text(text: str) -> str:
    """Copy text to the system clipboard."""
    try:
        p = subprocess.Popen(["powershell", "-Command", "Set-Clipboard"], stdin=subprocess.PIPE, text=True)
        p.communicate(input=text)
        return "Text copied to clipboard, Sir."
    except Exception as e:
        return f"Failed to set clipboard: {e}"

def get_clipboard_text() -> str:
    """Retrieve text from the system clipboard."""
    try:
        out = subprocess.check_output(["powershell", "-Command", "Get-Clipboard"]).decode().strip()
        return f"Clipboard contents: {out}" if out else "Clipboard is empty, Sir."
    except Exception as e:
        return f"Failed to get clipboard: {e}"


# ── System Information & Uptime ──

def get_system_telemetry() -> str:
    """Get system resource usage statistics (CPU, RAM, Disk, and Battery)."""
    cpu_cmd = "(Get-CimInstance Win32_Processor).LoadPercentage"
    ram_cmd = "$os = Get-CimInstance Win32_OperatingSystem; [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize * 100, 1)"
    disk_cmd = "$disk = Get-CimInstance Win32_LogicalDisk -Filter \"DeviceID='C:'\"; [math]::Round(($disk.Size - $disk.FreeSpace) / $disk.Size * 100, 1)"
    
    battery_pct = 100
    is_charging = True
    try:
        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ('ACLineStatus', ctypes.c_byte),
                ('BatteryFlag', ctypes.c_byte),
                ('BatteryLifePercent', ctypes.c_byte),
                ('Reserved1', ctypes.c_byte),
                ('BatteryLifeTime', ctypes.c_int),
                ('BatteryFullLifeTime', ctypes.c_int)
            ]
        status = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            battery_pct = status.BatteryLifePercent
            is_charging = status.ACLineStatus == 1
    except Exception:
        pass

    try:
        cpu = subprocess.check_output(["powershell", "-Command", cpu_cmd]).decode().strip() or "0"
        ram = subprocess.check_output(["powershell", "-Command", ram_cmd]).decode().strip() or "0"
        disk = subprocess.check_output(["powershell", "-Command", disk_cmd]).decode().strip() or "0"
    except Exception:
        cpu, ram, disk = "N/A", "N/A", "N/A"
        
    charge_status = "charging" if is_charging else "on battery"
    return f"System telemetry: CPU usage is {cpu}%, Memory usage is {ram}%, C: drive storage usage is {disk}%, Battery level is {battery_pct}% ({charge_status}), Sir."

def get_boot_and_uptime() -> str:
    """Get the system boot time and elapsed uptime."""
    import jarvis_state
    uptime_secs = int(time.time() - jarvis_state.state.start_time)
    hours = uptime_secs // 3600
    minutes = (uptime_secs % 3600) // 60
    
    boot_cmd = "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"
    try:
        boot_time = subprocess.check_output(["powershell", "-Command", boot_cmd]).decode().strip().split(".")[0]
    except Exception:
        boot_time = "Unknown"
        
    return f"Jarvis uptime is {hours} hours and {minutes} minutes. System boot time was {boot_time}, Sir."


# ── File Operations ──

def create_directory_or_file(path: str, is_dir: bool = False) -> str:
    """Create a new file or directory at the specified absolute or relative path."""
    try:
        if is_dir:
            os.makedirs(path, exist_ok=True)
            return f"Directory created at {path}, Sir."
        else:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w") as f:
                pass
            return f"File created at {path}, Sir."
    except Exception as e:
        return f"Failed to create: {e}"

def list_directory_contents(path: str = ".") -> str:
    """List all files and subdirectories inside the specified directory path."""
    try:
        items = os.listdir(path)
        if not items:
            return f"The directory {path} is empty, Sir."
        return f"Contents of {path}: " + ", ".join(items[:30])
    except Exception as e:
        return f"Failed to list directory: {e}"

def get_file_or_folder_size(path: str) -> str:
    """Get the size in megabytes of a file or folder."""
    try:
        if os.path.isfile(path):
            sz = os.path.getsize(path)
            return f"File size is {sz / (1024*1024):.2f} MB, Sir."
        elif os.path.isdir(path):
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.exists(fp):
                        total_size += os.path.getsize(fp)
            return f"Folder size is {total_size / (1024*1024):.2f} MB, Sir."
        return "Path does not exist, Sir."
    except Exception as e:
        return f"Error getting size: {e}"


# ── Network Controls ──

def get_network_info() -> str:
    """Get local IP address, public IP address, and connection status."""
    try:
        local_ip = subprocess.check_output(["powershell", "-Command", "(Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi', 'Ethernet' | Select-Object -First 1).IPAddress"]).decode().strip()
    except Exception:
        local_ip = "Unknown"
        
    try:
        public_ip = requests.get("https://api.ipify.org", timeout=3).text.strip()
    except Exception:
        public_ip = "Offline"
        
    return f"Local IP Address is {local_ip}. Public IP Address is {public_ip}, Sir."

def ping_host(host: str) -> str:
    """Ping a host (e.g. 'google.com', '1.1.1.1') to test internet connectivity."""
    try:
        out = subprocess.run(["ping", "-n", "1", host], capture_output=True, text=True)
        if out.returncode == 0:
            return f"Ping to {host} succeeded, Sir. Connection is stable."
        else:
            return f"Ping to {host} failed, Sir. Host is unreachable."
    except Exception as e:
        return f"Failed to run ping: {e}"


# ── Windows Services & Process Control ──

def kill_process_by_name(name: str) -> str:
    """Kill a process by its name (e.g. 'notepad', 'chrome')."""
    try:
        subprocess.run(["taskkill", "/f", "/im", f"{name}.exe" if not name.endswith(".exe") else name], capture_output=True)
        return f"Sent termination signal to process '{name}', Sir."
    except Exception as e:
        return f"Failed to stop process: {e}"

def list_running_processes() -> str:
    """Get a list of the top running processes sorted by memory usage."""
    cmd = "Get-Process | Sort-Object WS -Descending | Select-Object -First 10 -Property ProcessName, @{Name='MemoryMB';Expression={[math]::Round($_.WS / 1MB, 1)}} | Out-String"
    try:
        out = subprocess.check_output(["powershell", "-Command", cmd]).decode().strip()
        return f"Top active processes:\n{out}"
    except Exception as e:
        return f"Failed to list processes: {e}"


# ── Screen Control ──

def capture_and_save_screenshot() -> str:
    """Capture the current screen and save it to the dashboard static folder so the user can open it."""
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "static")
    filename = f"screenshot_{int(time.time())}.png"
    save_path = os.path.join(static_dir, filename)
    
    cmd = f"""
    Add-Type -AssemblyName System.Drawing, System.Windows.Forms;
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;
    $bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height;
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap);
    $graphics.CopyFromScreen($screen.X, $screen.Y, 0, 0, $bitmap.Size);
    $bitmap.Save('{save_path}');
    $graphics.Dispose();
    $bitmap.Dispose();
    """
    try:
        os.makedirs(static_dir, exist_ok=True)
        subprocess.run(["powershell", "-Command", cmd], capture_output=True, check=True)
        if os.path.exists(save_path):
            return f"Screenshot saved successfully, Sir. You can view it at http://127.0.0.1:5000/{filename}"
        return "Failed to save the screenshot, Sir."
    except Exception as e:
        return f"Failed to capture screenshot: {e}"

def describe_screen() -> str:
    """Capture the current screen and describe what is visible on it in detail."""
    temp_path = os.path.join(os.environ.get("TEMP", "."), f"jarvis_screen_{int(time.time())}.png")
    cmd = f"""
    Add-Type -AssemblyName System.Drawing, System.Windows.Forms;
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;
    $bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height;
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap);
    $graphics.CopyFromScreen($screen.X, $screen.Y, 0, 0, $bitmap.Size);
    $bitmap.Save('{temp_path}');
    $graphics.Dispose();
    $bitmap.Dispose();
    """
    try:
        subprocess.run(["powershell", "-Command", cmd], capture_output=True, check=True)
        if not os.path.exists(temp_path):
            return "Failed to capture the screen, Sir."
            
        from google import genai
        from google.genai import types
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return "Gemini API key is not configured, Sir."
            
        client = genai.Client(api_key=api_key)
        with open(temp_path, "rb") as f:
            img_bytes = f.read()
            
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type='image/png',
                ),
                "Describe what is currently visible on my laptop screen in detail. Focus on active applications, text, and layout, Sir."
            ]
        )
        
        try:
            os.remove(temp_path)
        except Exception:
            pass
            
        return response.text
    except Exception as e:
        return f"Failed to access the screen: {e}"

def ocr_screen() -> str:
    """Capture the current screen and perform optical character recognition (OCR) to extract all text on it."""
    temp_path = os.path.join(os.environ.get("TEMP", "."), f"jarvis_screen_{int(time.time())}.png")
    cmd = f"""
    Add-Type -AssemblyName System.Drawing, System.Windows.Forms;
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;
    $bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height;
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap);
    $graphics.CopyFromScreen($screen.X, $screen.Y, 0, 0, $bitmap.Size);
    $bitmap.Save('{temp_path}');
    $graphics.Dispose();
    $bitmap.Dispose();
    """
    try:
        subprocess.run(["powershell", "-Command", cmd], capture_output=True, check=True)
        if not os.path.exists(temp_path):
            return "Failed to capture the screen, Sir."
            
        from google import genai
        from google.genai import types
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return "Gemini API key is not configured, Sir."
            
        client = genai.Client(api_key=api_key)
        with open(temp_path, "rb") as f:
            img_bytes = f.read()
            
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type='image/png',
                ),
                "Perform Optical Character Recognition (OCR) on this screen capture. Return only the extracted text in a clear layout, Sir."
            ]
        )
        
        try:
            os.remove(temp_path)
        except Exception:
            pass
            
        return response.text
    except Exception as e:
        return f"Failed to perform screen OCR: {e}"

def find_text_on_screen(query: str) -> str:
    """Search for a specific word, phrase, or element on the current screen and describe where it is located."""
    temp_path = os.path.join(os.environ.get("TEMP", "."), f"jarvis_screen_{int(time.time())}.png")
    cmd = f"""
    Add-Type -AssemblyName System.Drawing, System.Windows.Forms;
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds;
    $bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height;
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap);
    $graphics.CopyFromScreen($screen.X, $screen.Y, 0, 0, $bitmap.Size);
    $bitmap.Save('{temp_path}');
    $graphics.Dispose();
    $bitmap.Dispose();
    """
    try:
        subprocess.run(["powershell", "-Command", cmd], capture_output=True, check=True)
        if not os.path.exists(temp_path):
            return "Failed to capture the screen, Sir."
            
        from google import genai
        from google.genai import types
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return "Gemini API key is not configured, Sir."
            
        client = genai.Client(api_key=api_key)
        with open(temp_path, "rb") as f:
            img_bytes = f.read()
            
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type='image/png',
                ),
                f"Find the text or element '{query}' on my screen. Describe where it is located (e.g. top-left, center, inside an application window) and what context surrounds it, Sir."
            ]
        )
        
        try:
            os.remove(temp_path)
        except Exception:
            pass
            
        return response.text
    except Exception as e:
        return f"Failed to search screen: {e}"
