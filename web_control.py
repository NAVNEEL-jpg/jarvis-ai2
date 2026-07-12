from flask import Flask, request, render_template_string
from intent_router import handle_command
from supabase_client import log_command

app = Flask(__name__)

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>J.A.R.V.I.S. Mobile Control Link</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #050811;
            --panel-bg: rgba(10, 16, 30, 0.9);
            --accent: #00f0ff;
            --accent-glow: rgba(0, 240, 255, 0.3);
            --danger: #ff3c4a;
            --success: #26ff7b;
            --warning: #ffb834;
            --font-primary: 'Orbitron', sans-serif;
            --font-mono: 'Share Tech Mono', monospace;
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            background-color: var(--bg-dark);
            background-image: 
                linear-gradient(rgba(0, 240, 255, 0.02) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 240, 255, 0.02) 1px, transparent 1px);
            background-size: 20px 20px;
            font-family: var(--font-primary);
            color: #d6e8f4;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
        }
        .container {
            width: 100%;
            max-width: 480px;
            background: var(--panel-bg);
            border: 1px solid rgba(0, 240, 255, 0.15);
            box-shadow: 0 0 20px rgba(0, 240, 255, 0.05);
            border-radius: 12px;
            padding: 25px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        header {
            text-align: center;
            border-bottom: 1px solid rgba(0, 240, 255, 0.1);
            padding-bottom: 15px;
        }
        h1 {
            font-size: 1.4rem;
            color: var(--accent);
            letter-spacing: 2px;
            text-shadow: 0 0 10px var(--accent-glow);
        }
        .subtitle {
            font-size: 0.75rem;
            font-family: var(--font-mono);
            color: #5e7e90;
            margin-top: 4px;
        }
        .response-box {
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(0, 240, 255, 0.08);
            border-radius: 6px;
            padding: 15px;
            min-height: 70px;
            font-family: var(--font-mono);
            font-size: 0.85rem;
            line-height: 1.4;
            color: #eee;
            word-wrap: break-word;
        }
        .response-box.empty {
            color: #5e7e90;
            font-style: italic;
        }
        .console-input-row {
            display: flex;
            gap: 10px;
        }
        input {
            flex-grow: 1;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(0, 240, 255, 0.2);
            border-radius: 6px;
            padding: 12px;
            color: #fff;
            font-family: var(--font-mono);
            font-size: 0.95rem;
            outline: none;
            transition: all 0.2s ease;
        }
        input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 8px var(--accent-glow);
        }
        .btn-submit {
            background: var(--accent);
            border: none;
            border-radius: 6px;
            color: #000;
            font-family: var(--font-primary);
            font-weight: 700;
            padding: 0 20px;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .btn-submit:active {
            transform: scale(0.95);
        }
        .section-title {
            font-size: 0.8rem;
            font-family: var(--font-mono);
            color: var(--accent);
            letter-spacing: 1px;
            border-left: 2px solid var(--accent);
            padding-left: 8px;
            margin-bottom: 10px;
        }
        .shortcuts-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
        .shortcut-btn {
            background: rgba(10, 20, 40, 0.5);
            border: 1px solid rgba(0, 240, 255, 0.15);
            border-radius: 6px;
            color: #d6e8f4;
            padding: 15px 10px;
            font-family: var(--font-mono);
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 5px;
        }
        .shortcut-btn:hover {
            background: rgba(0, 240, 255, 0.08);
            border-color: var(--accent);
            box-shadow: 0 0 8px rgba(0, 240, 255, 0.05);
        }
        .shortcut-btn:active {
            transform: scale(0.95);
        }
        .shortcut-btn.danger {
            border-color: rgba(255, 60, 74, 0.2);
        }
        .shortcut-btn.danger:hover {
            background: rgba(255, 60, 74, 0.08);
            border-color: var(--danger);
        }
        .shortcut-btn.success {
            border-color: rgba(38, 255, 123, 0.2);
        }
        .shortcut-btn.success:hover {
            background: rgba(38, 255, 123, 0.08);
            border-color: var(--success);
        }
        .btn-icon {
            font-size: 1.1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>J.A.R.V.I.S. MOBILE REMOTE</h1>
            <div class="subtitle">SECURE COM LINK // SERVER: PORT 5001</div>
        </header>

        <div class="section-title">SYSTEM RESPONSE</div>
        <div class="response-box {% if not response %}empty{% endif %}">
            {{ response or "AWAITING TELEMETRY UPLINK DIRECTIVE..." }}
        </div>

        <form method="POST" class="console-input-row">
            <input type="text" name="command" placeholder="TRANSMIT DIRECTIVE PATHWAY..." autocomplete="off" autofocus>
            <button type="submit" class="btn-submit">SEND</button>
        </form>

        <div>
            <div class="section-title">VM AUTOMATION SHORTCUTS</div>
            <div class="shortcuts-grid">
                <button type="button" class="shortcut-btn success" onclick="sendCmd('start vm Home Assistant')">
                    <span class="btn-icon">⚡</span>
                    <span>START HA VM</span>
                </button>
                <button type="button" class="shortcut-btn danger" onclick="sendCmd('stop vm Home Assistant')">
                    <span class="btn-icon">⏹</span>
                    <span>STOP HA VM</span>
                </button>
                <button type="button" class="shortcut-btn" onclick="sendCmd('list vms')">
                    <span class="btn-icon">📋</span>
                    <span>LIST ALL VMS</span>
                </button>
                <button type="button" class="shortcut-btn" onclick="sendCmd('list running vms')">
                    <span class="btn-icon">🟢</span>
                    <span>LIST RUNNING</span>
                </button>
            </div>
        </div>

        <div>
            <div class="section-title">SYSTEM SHORTCUTS</div>
            <div class="shortcuts-grid">
                <button type="button" class="shortcut-btn" onclick="sendCmd('lock systems')">
                    <span class="btn-icon">🔒</span>
                    <span>LOCK SYSTEM</span>
                </button>
                <button type="button" class="shortcut-btn" onclick="sendCmd('4598')">
                    <span class="btn-icon">🔓</span>
                    <span>UNLOCK CODE</span>
                </button>
                <button type="button" class="shortcut-btn" onclick="sendCmd('what is the system load')">
                    <span class="btn-icon">📈</span>
                    <span>SYS DIAGS</span>
                </button>
                <button type="button" class="shortcut-btn" onclick="sendCmd('what is the weather')">
                    <span class="btn-icon">☁</span>
                    <span>WEATHER</span>
                </button>
            </div>
        </div>
    </div>

    <script>
        function sendCmd(cmd) {
            const input = document.querySelector('input[name="command"]');
            input.value = cmd;
            document.querySelector('form').submit();
        }
    </script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    response = ""
    if request.method == "POST":
        command = request.form.get("command", "")
        response = handle_command(command)
        log_command(command, "phone_command", response, source="phone")
    return render_template_string(PAGE, response=response)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)