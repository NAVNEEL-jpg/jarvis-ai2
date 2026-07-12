// J.A.R.V.I.S. Core Controller JavaScript

// ── Permanent ngrok static domain — never changes between restarts ──
const FIXED_TUNNEL_URL = "https://probation-tiptoeing-evade.ngrok-free.dev";

document.addEventListener("DOMContentLoaded", () => {
    // ── Dynamic API Base Setup for Cloud Deployment (Vercel) ──
    const isLocalhost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
    const isFileProtocol = window.location.protocol === "file:";

    let API_BASE;
    if (isLocalhost) {
        // Running locally — talk directly to Flask, no tunnel needed
        API_BASE = "";
    } else if (isFileProtocol) {
        API_BASE = "http://localhost:5000";
    } else {
        // Running on Vercel or any remote host.
        // Use the manually stored override first, otherwise fall back to the
        // fixed tunnel URL so the page just works with no manual setup.
        API_BASE = localStorage.getItem("jarvis_api_base") || FIXED_TUNNEL_URL;
    }

    // Intercept all /api/ fetches and prefix with the correct base URL.
    // Also inject the localtunnel bypass header so API calls skip the
    // "click to continue" splash page that localtunnel shows in browsers.
    const originalFetch = window.fetch;
    window.fetch = function (url, options) {
        if (typeof url === "string" && url.startsWith("/api/")) {
            url = API_BASE + url;
            options = options || {};
            options.headers = Object.assign(
                { "bypass-tunnel-reminder": "true" },
                options.headers || {}
            );
        }
        return originalFetch(url, options);
    };

    // Add [LINK] config button on the lock screen
    const lockScreen = document.getElementById("lock-screen");
    if (lockScreen) {
        const btnConfig = document.createElement("button");
        btnConfig.style.position = "absolute";
        btnConfig.style.top = "15px";
        btnConfig.style.right = "15px";
        btnConfig.style.background = "transparent";
        btnConfig.style.border = "1px solid rgba(0, 240, 255, 0.3)";
        btnConfig.style.color = "var(--text-primary)";
        btnConfig.style.fontSize = "0.6rem";
        btnConfig.style.padding = "4px 8px";
        btnConfig.style.cursor = "pointer";
        btnConfig.style.fontFamily = "var(--font-mono)";
        btnConfig.textContent = "LINK UPLINK";
        
        lockScreen.style.position = "relative";
        lockScreen.appendChild(btnConfig);

        btnConfig.addEventListener("click", () => {
            const newBase = prompt("Enter J.A.R.V.I.S. Tunnel Endpoint URL (e.g., https://your-tunnel.ngrok-free.app):", API_BASE);
            if (newBase !== null) {
                localStorage.setItem("jarvis_api_base", newBase.trim());
                window.location.reload();
            }
        });
    }

    // ── Dynamic Theme Engine ──────────────────────────────────────────────────
    // Converts a hex color into a full HSL-derived palette and applies it to
    // all CSS custom properties so the entire HUD shifts color in real time.

    let _currentThemeHex = "#00f0ff"; // default cyan (Jarvis startup color)

    function hexToHsl(hex) {
        // Expand shorthand #abc to #aabbcc
        hex = hex.replace(/^#?([a-f\d])([a-f\d])([a-f\d])$/i, (_, r, g, b) => r+r+g+g+b+b);
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        if (!result) return { h: 180, s: 100, l: 50 };
        let r = parseInt(result[1], 16) / 255;
        let g = parseInt(result[2], 16) / 255;
        let b = parseInt(result[3], 16) / 255;
        const max = Math.max(r, g, b), min = Math.min(r, g, b);
        let h, s, l = (max + min) / 2;
        if (max === min) { h = s = 0; }
        else {
            const d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            switch (max) {
                case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
                case g: h = ((b - r) / d + 2) / 6; break;
                case b: h = ((r - g) / d + 4) / 6; break;
            }
        }
        return { h: Math.round(h * 360), s: Math.round(s * 100), l: Math.round(l * 100) };
    }

    function hslToHex(h, s, l) {
        s /= 100; l /= 100;
        const k = n => (n + h / 30) % 12;
        const a = s * Math.min(l, 1 - l);
        const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
        return '#' + [f(0), f(8), f(4)].map(x => Math.round(x * 255).toString(16).padStart(2, '0')).join('');
    }

    function applyTheme(hex) {
        if (!hex || hex === _currentThemeHex) return;
        _currentThemeHex = hex;

        const { h, s, l } = hexToHsl(hex);
        const root = document.documentElement;

        // Primary = the color itself (vivid)
        const primary       = hslToHex(h, Math.min(s, 100), Math.min(Math.max(l, 55), 70));
        // Secondary = slightly shifted hue, a bit dimmer
        const secondary     = hslToHex((h + 15) % 360, Math.max(s - 10, 60), Math.max(l - 15, 40));
        // Muted = very desaturated, dark version for subtle text
        const muted         = hslToHex(h, Math.max(s - 40, 15), 35);
        // Glow = very transparent version for borders
        const glowAlpha     = hex + "30";
        const glowFocusAlpha = hex + "90";
        // Background grid tint — barely visible
        const gridAlpha     = hex + "08";
        // Dark bg tint with a hint of hue
        const bgDark        = hslToHex(h, Math.min(s, 25), 3);
        const panelBg       = `rgba(${parseInt(hex.slice(1,3),16)*0.04|0}, ${parseInt(hex.slice(3,5),16)*0.04|0}, ${parseInt(hex.slice(5,7),16)*0.06|0}, 0.88)`;

        root.style.setProperty('--text-primary',       primary);
        root.style.setProperty('--text-sec',           secondary);
        root.style.setProperty('--text-muted',         muted);
        root.style.setProperty('--border-glow',        glowAlpha);
        root.style.setProperty('--border-glow-focus',  glowFocusAlpha);
        root.style.setProperty('--bg-dark',            bgDark);

        // Update the CSS grid background pattern
        document.body.style.backgroundImage = `
            linear-gradient(${gridAlpha} 1px, transparent 1px),
            linear-gradient(90deg, ${gridAlpha} 1px, transparent 1px)
        `;
    }

    // Apply the default startup theme immediately
    applyTheme(_currentThemeHex);

    // Custom recording state variables
    let isCustomRecording = false;
    let customAudioContext = null;
    let customAudioStream = null;
    let customAudioProcessor = null;
    let customAudioSource = null;
    let customAudioChunks = [];
    let customAudioLength = 0;
    let customRecordingTimeout = null;

    // ── Web Speech Recognition for Mobile Remote ──
    function startMobileSpeechRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                startCustomAudioRecording();
            } else {
                const errDiv = document.createElement("div");
                errDiv.className = "log-entry system";
                errDiv.innerHTML = `[MIC ERROR] SPEECH RECOGNITION NOT SUPPORTED ON THIS BROWSER/DEVICE. EXPORT HTTPS URL AND ALLOW PERMISSIONS.`;
                logFeed.appendChild(errDiv);
                logFeed.scrollTop = logFeed.scrollHeight;
                
                commandInput.focus();
                commandInput.placeholder = "AWAITING CORE DIRECTIVES...";
                setTimeout(() => {
                    commandInput.placeholder = "TRANSMIT INTENT PATHWAY TO CORE...";
                }, 3000);
            }
            return;
        }

        try {
            const activeRecog = new SpeechRecognition();
            activeRecog.continuous = false;
            activeRecog.interimResults = false;
            activeRecog.lang = "en-US";

            activeRecog.onstart = () => {
                playBeep("click");
                reactorContainer.classList.add("listening");
                reactorStatus.textContent = "LISTENING VIA MOBILE...";
            };

            activeRecog.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                commandInput.value = transcript;
                commandForm.dispatchEvent(new Event("submit"));
            };

            activeRecog.onerror = (e) => {
                console.error("Speech recognition error:", e);
                playBeep("error");
                reactorContainer.classList.remove("listening");
                reactorStatus.textContent = "MOBILE MIC ERROR";
                
                const errDiv = document.createElement("div");
                errDiv.className = "log-entry system";
                errDiv.innerHTML = `[MIC ERROR] CODE: ${e.error || "UNKNOWN"}. CHECK PERMISSIONS & HTTPS.`;
                logFeed.appendChild(errDiv);
                logFeed.scrollTop = logFeed.scrollHeight;
            };

            activeRecog.onend = () => {
                reactorContainer.classList.remove("listening");
                if (reactorStatus.textContent === "LISTENING VIA MOBILE...") {
                    reactorStatus.textContent = "SYSTEM STANDBY";
                }
            };

            activeRecog.start();
        } catch (err) {
            console.error("Failed to start SpeechRecognition:", err);
            commandInput.focus();
        }
    }

    // ── Custom Audio Recording Fallback (WAV encoder for iOS Chrome) ──
    function startCustomAudioRecording() {
        if (isCustomRecording) return;

        navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
            customAudioStream = stream;
            customAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            customAudioSource = customAudioContext.createMediaStreamSource(stream);
            customAudioProcessor = customAudioContext.createScriptProcessor(4096, 1, 1);
            
            customAudioChunks = [];
            customAudioLength = 0;
            
            customAudioProcessor.onaudioprocess = (e) => {
                const inputData = e.inputBuffer.getChannelData(0);
                customAudioChunks.push(new Float32Array(inputData));
                customAudioLength += inputData.length;
            };
            
            customAudioSource.connect(customAudioProcessor);
            customAudioProcessor.connect(customAudioContext.destination);
            
            isCustomRecording = true;
            reactorContainer.classList.add("listening");
            reactorStatus.textContent = "RECORDING (TAP CORE TO SEND)";
            playBeep("click");
            
            customRecordingTimeout = setTimeout(() => {
                if (isCustomRecording) {
                    stopCustomAudioRecording();
                }
            }, 10000);
        })
        .catch(err => {
            console.error("Custom audio recording permission denied/failed:", err);
            playBeep("error");
            
            const errDiv = document.createElement("div");
            errDiv.className = "log-entry system";
            errDiv.innerHTML = `[MIC ERROR] UNABLE TO ACCESS MICROPHONE. PLEASE GRANT PERMISSION.`;
            logFeed.appendChild(errDiv);
            logFeed.scrollTop = logFeed.scrollHeight;
            
            reactorStatus.textContent = "MOBILE MIC ERROR";
            setTimeout(() => {
                if (reactorStatus.textContent === "MOBILE MIC ERROR") {
                    reactorStatus.textContent = "SYSTEM STANDBY";
                }
            }, 3000);
        });
    }

    function stopCustomAudioRecording() {
        if (!isCustomRecording) return;
        isCustomRecording = false;
        
        if (customRecordingTimeout) {
            clearTimeout(customRecordingTimeout);
            customRecordingTimeout = null;
        }
        
        playBeep("click");
        reactorContainer.classList.remove("listening");
        reactorStatus.textContent = "PROCESSING CORE DIRECTIVES...";

        if (customAudioProcessor) {
            customAudioProcessor.disconnect();
            customAudioProcessor.onaudioprocess = null;
        }
        if (customAudioSource) {
            customAudioSource.disconnect();
        }
        if (customAudioContext) {
            customAudioContext.close();
        }
        if (customAudioStream) {
            customAudioStream.getTracks().forEach(track => track.stop());
        }

        const flatBuffer = flattenArray(customAudioChunks, customAudioLength);
        const wavBlob = exportWAV(flatBuffer, 16000);

        const formData = new FormData();
        formData.append("audio", wavBlob, "mobile_command.wav");

        fetch("/api/transcribe_mobile", {
            method: "POST",
            body: formData
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                commandInput.value = data.transcript;
                
                const userEntry = document.createElement("div");
                userEntry.className = "log-entry user";
                userEntry.innerHTML = `<span class="timestamp">[${new Date().toLocaleTimeString()}]</span> SIR: ${data.transcript.toUpperCase()}`;
                logFeed.appendChild(userEntry);
                
                const jarvisEntry = document.createElement("div");
                jarvisEntry.className = "log-entry jarvis";
                jarvisEntry.innerHTML = `<span class="timestamp">[${new Date().toLocaleTimeString()}]</span> JARVIS: ${data.response.toUpperCase()}`;
                logFeed.appendChild(jarvisEntry);
                
                logFeed.scrollTop = logFeed.scrollHeight;
                reactorStatus.textContent = "SYSTEM STANDBY";
                playTTSAudio(data.speech_id);
                if (data.open_url) {
                    window.open(data.open_url, "spotify_player");
                }
            } else if (data.status === "empty") {
                reactorStatus.textContent = "SYSTEM STANDBY";
                const errDiv = document.createElement("div");
                errDiv.className = "log-entry system";
                errDiv.innerHTML = `[AUDIO INFRASTRUCTURE] NO SPEECH CAPTURED.`;
                logFeed.appendChild(errDiv);
                logFeed.scrollTop = logFeed.scrollHeight;
            } else {
                playBeep("error");
                reactorStatus.textContent = "TRANSMISSION ERROR";
                setTimeout(() => { reactorStatus.textContent = "SYSTEM STANDBY"; }, 3000);
            }
        })
        .catch(err => {
            console.error("Error transcribing mobile audio:", err);
            playBeep("error");
            reactorStatus.textContent = "TRANSMISSION FAILED";
            setTimeout(() => { reactorStatus.textContent = "SYSTEM STANDBY"; }, 3000);
        });
    }

    function flattenArray(channelBuffer, recordingLength) {
        let result = new Float32Array(recordingLength);
        let offset = 0;
        for (let i = 0; i < channelBuffer.length; i++) {
            let buffer = channelBuffer[i];
            result.set(buffer, offset);
            offset += buffer.length;
        }
        return result;
    }

    function writeUTFBytes(view, offset, string) {
        for (let i = 0; i < string.length; i++) {
            view.setUint8(offset + i, string.charCodeAt(i));
        }
    }

    function exportWAV(audioBuffer, sampleRate) {
        let buffer = new ArrayBuffer(44 + audioBuffer.length * 2);
        let view = new DataView(buffer);

        writeUTFBytes(view, 0, 'RIFF');
        view.setUint32(4, 36 + audioBuffer.length * 2, true);
        writeUTFBytes(view, 8, 'WAVE');
        writeUTFBytes(view, 12, 'fmt ');
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, 1, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, sampleRate * 2, true);
        view.setUint16(32, 2, true);
        view.setUint16(34, 16, true);
        writeUTFBytes(view, 36, 'data');
        view.setUint32(40, audioBuffer.length * 2, true);

        let index = 44;
        for (let i = 0; i < audioBuffer.length; i++) {
            let s = Math.max(-1, Math.min(1, audioBuffer[i]));
            view.setInt16(index, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
            index += 2;
        }

        return new Blob([view], { type: 'audio/wav' });
    }

    // ── Device Switcher Helpers ──
    function applyDeviceUI(device) {
        currentActiveDevice = device;

        // Update pill active state
        devicePills.forEach(pill => {
            pill.classList.toggle("active", pill.dataset.device === device);
        });

        // Show/hide mobile banner
        if (mobileActiveBanner) {
            mobileActiveBanner.classList.toggle("visible", device === "mobile");
        }
    }

    function fetchActiveDevice() {
        fetch("/api/active_device")
            .then(res => res.json())
            .then(data => {
                applyDeviceUI(data.active_mic_device || "laptop");
            })
            .catch(() => {});
    }

    function setActiveDevice(device) {
        playBeep("click");
        fetch("/api/active_device", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device })
        })
        .then(res => res.json())
        .then(data => {
            applyDeviceUI(data.active_mic_device || device);
            const entry = document.createElement("div");
            entry.className = "log-entry system";
            entry.innerHTML = `[INPUT SWITCH] ACTIVE MIC DEVICE: ${data.active_mic_device.toUpperCase()}`;
            logFeed.appendChild(entry);
            logFeed.scrollTop = logFeed.scrollHeight;
        })
        .catch(() => { playBeep("error"); });
    }

    // ── Elements ──
    const hudContainer = document.querySelector(".hud-container");
    const clockEl = document.getElementById("hud-clock");
    const dateEl = document.getElementById("hud-date");
    const tickerTextEl = document.getElementById("ticker-text");
    
    const cpuVal = document.getElementById("cpu-value");
    const cpuBar = document.getElementById("cpu-bar");
    const ramVal = document.getElementById("ram-value");
    const ramBar = document.getElementById("ram-bar");
    const ramDetails = document.getElementById("ram-details");
    const diskVal = document.getElementById("disk-value");
    const diskBar = document.getElementById("disk-bar");
    const diskDetails = document.getElementById("disk-details");
    const batteryVal = document.getElementById("battery-value");
    const batteryBar = document.getElementById("battery-bar");
    const batterySource = document.getElementById("battery-source");

    // GPU & Cooling Elements
    const gpuVal = document.getElementById("gpu-value");
    const gpuBar = document.getElementById("gpu-bar");
    const gpuDetails = document.getElementById("gpu-details");
    const cpuTempEl = document.getElementById("cpu-temp-val");
    const cpuFanEl = document.getElementById("cpu-fan-val");
    const gpuFanEl = document.getElementById("gpu-fan-val");
    
    const reactorTrigger = document.getElementById("reactor-trigger");
    const reactorStatus = document.getElementById("reactor-status");
    const reactorContainer = document.querySelector(".reactor-container");
    const centerPanel = document.querySelector(".center-panel");
    const spectrumBars = document.getElementById("spectrum-bars");
    
    const commandForm = document.getElementById("command-form");
    const commandInput = document.getElementById("command-input");
    const stopSpeechBtn = document.getElementById("stop-speech-btn");
    
    const weatherTemp = document.getElementById("weather-temp");
    const weatherCity = document.getElementById("weather-city");
    const weatherCond = document.getElementById("weather-cond");
    const wFeels = document.getElementById("w-feels");
    const wHum = document.getElementById("w-hum");
    const wWind = document.getElementById("w-wind");
    
    const tasksList = document.getElementById("tasks-list");
    const logFeed = document.getElementById("log-feed");
    
    const btnLock = document.getElementById("btn-lock");
    const btnPower = document.getElementById("btn-power");
    const btnSyncAutomations = document.getElementById("btn-sync-automations");
    
    const playPauseBgm = document.getElementById("play-pause-bgm");
    const ambientBgm = document.getElementById("ambient-bgm");
    const mediaProgress = document.getElementById("media-progress");
    const playerTime = document.getElementById("player-time");

    // Alarms Elements
    const alarmForm = document.getElementById("alarm-form");
    const alarmTimeInput = document.getElementById("alarm-time");
    const alarmLabelInput = document.getElementById("alarm-label");
    const alarmsList = document.getElementById("alarms-list");

    // Spotify WiFi output switcher elements
    const spotifyDeviceSelector = document.getElementById("spotify-device-selector");
    const spotifyDeviceDropdown = document.getElementById("spotify-device-dropdown");
    const spotifyDeviceList = document.getElementById("spotify-device-list");

    // Device switcher elements
    const devicePills = document.querySelectorAll(".device-pill");
    const mobileActiveBanner = document.getElementById("mobile-active-banner");
    let currentActiveDevice = "laptop";

    // Security Lock Screen Elements
    const lockStatus = document.getElementById("lock-status");
    const keypadDisplay = document.getElementById("keypad-display");
    const keyButtons = document.querySelectorAll(".key-btn[data-val]");
    const keyClear = document.getElementById("key-clear");
    const keyEnter = document.getElementById("key-enter");
    const btnFaceVerify = document.getElementById("btn-face-verify");
    const faceScannerWrap = document.getElementById("face-scanner-wrap");
    const faceScannerText = document.getElementById("face-scanner-text");

    let enteredPasscode = "";
    let isMainHUDInitialized = false;
    let hasAttemptedAutoScan = false;

    // Mobile Helper Modal elements
    const mobileSetupModal = document.getElementById("mobile-setup-modal");
    const btnMobileSetup = document.getElementById("btn-mobile-setup");
    const btnMobileSetupMain = document.getElementById("btn-mobile-setup-main");
    const btnCloseSetup = document.getElementById("btn-close-setup");
    const btnTriggerPermissions = document.getElementById("btn-trigger-permissions");
    const btnTestSpeaker = document.getElementById("btn-test-speaker");

    // Unified Audio Elements
    const ttsAudioPlayer = new Audio();
    let playedSpeechId = 0;

    function unlockAudio() {
        ttsAudioPlayer.play().then(() => {
            ttsAudioPlayer.pause();
            console.log("[AUDIO] ttsAudioPlayer unlocked.");
        }).catch(e => {
            console.log("[AUDIO] Unlock attempt:", e);
        });

        const silentWakeLock = document.getElementById("silent-wakelock");
        if (silentWakeLock) {
            silentWakeLock.play().then(() => {
                console.log("[AUDIO] silent-wakelock active in background.");
            }).catch(e => {
                console.log("[AUDIO] silent-wakelock failed:", e);
            });
        }
    }

    // Attempt to unlock audio on first page clicks/touches
    document.body.addEventListener("click", unlockAudio, { once: true });
    document.body.addEventListener("touchstart", unlockAudio, { once: true });

    function showMobileSetupModal() {
        playBeep("click");
        mobileSetupModal.classList.remove("hidden");
    }

    function hideMobileSetupModal() {
        playBeep("click");
        mobileSetupModal.classList.add("hidden");
    }

    if (btnMobileSetup) btnMobileSetup.addEventListener("click", showMobileSetupModal);
    if (btnMobileSetupMain) btnMobileSetupMain.addEventListener("click", showMobileSetupModal);
    if (btnCloseSetup) btnCloseSetup.addEventListener("click", hideMobileSetupModal);

    if (btnTestSpeaker) {
        btnTestSpeaker.addEventListener("click", () => {
            playBeep("success");
            unlockAudio();
            // Trigger test voice audio playback
            ttsAudioPlayer.src = API_BASE + "/api/tts_audio?t=" + Date.now();
            ttsAudioPlayer.play().catch(err => {
                console.error("Test playback failed:", err);
                alert("Audio playback failed. Please toggle your Ring/Silent switch to RING (sound on) and try again.");
            });
        });
    }

    if (btnTriggerPermissions) {
        btnTriggerPermissions.addEventListener("click", () => {
            playBeep("click");
            const labelText = btnTriggerPermissions.textContent;
            btnTriggerPermissions.textContent = "REQUESTING ACCESS...";
            btnTriggerPermissions.disabled = true;

            navigator.mediaDevices.getUserMedia({ audio: true, video: true })
            .then(stream => {
                btnTriggerPermissions.textContent = "ACCESS GRANTED SUCCESS";
                btnTriggerPermissions.style.borderColor = "var(--success)";
                btnTriggerPermissions.style.color = "var(--success)";
                
                stream.getTracks().forEach(track => track.stop());
                
                const logEntry = document.createElement("div");
                logEntry.className = "log-entry system";
                logEntry.innerHTML = `[MOBILE SYSTEM] MIC & CAMERA ACCESS GRANTED VIA CHROME PROMPTS.`;
                logFeed.appendChild(logEntry);
                logFeed.scrollTop = logFeed.scrollHeight;
                
                setTimeout(() => {
                    btnTriggerPermissions.textContent = "INITIATE PERMISSION PROMPTS";
                    btnTriggerPermissions.style.borderColor = "";
                    btnTriggerPermissions.style.color = "";
                    btnTriggerPermissions.disabled = false;
                }, 3000);
            })
            .catch(err => {
                console.error("Failed to request permissions:", err);
                btnTriggerPermissions.textContent = "ACCESS DENIED / ERROR";
                btnTriggerPermissions.style.borderColor = "var(--danger)";
                btnTriggerPermissions.style.color = "var(--danger)";
                
                setTimeout(() => {
                    btnTriggerPermissions.textContent = "INITIATE PERMISSION PROMPTS";
                    btnTriggerPermissions.style.borderColor = "";
                    btnTriggerPermissions.style.color = "";
                    btnTriggerPermissions.disabled = false;
                }, 3000);
            });
        });
    }

    // ── Procedural Web Audio Synth ──
    function playBeep(type = "click") {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            
            if (type === "click") {
                osc.type = "sine";
                osc.frequency.setValueAtTime(900, ctx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(1400, ctx.currentTime + 0.06);
                gain.gain.setValueAtTime(0.04, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.06);
                osc.start();
                osc.stop(ctx.currentTime + 0.06);
            } else if (type === "success") {
                osc.type = "triangle";
                osc.frequency.setValueAtTime(700, ctx.currentTime);
                osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.08);
                gain.gain.setValueAtTime(0.05, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
                osc.start();
                osc.stop(ctx.currentTime + 0.18);
            } else if (type === "error") {
                osc.type = "sawtooth";
                osc.frequency.setValueAtTime(220, ctx.currentTime);
                osc.frequency.linearRampToValueAtTime(120, ctx.currentTime + 0.22);
                gain.gain.setValueAtTime(0.08, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.22);
                osc.start();
                osc.stop(ctx.currentTime + 0.22);
            }
        } catch (e) {
            // Context blocked
        }
    }

    function playTTSAudio(speechId) {
        if (currentActiveDevice === "laptop") return;
        
        if (speechId) {
            playedSpeechId = speechId;
        }
        
        try {
            ttsAudioPlayer.src = API_BASE + "/api/tts_audio?t=" + Date.now();
            ttsAudioPlayer.play().catch(err => {
                console.error("Failed to play TTS audio on mobile speaker:", err);
            });
        } catch (err) {
            console.error("Error playing TTS audio:", err);
        }
    }

    // ── Clock & Date ──
    function updateClock() {
        const now = new Date();
        const hrs = String(now.getHours()).padStart(2, "0");
        const mins = String(now.getMinutes()).padStart(2, "0");
        const secs = String(now.getSeconds()).padStart(2, "0");
        
        clockEl.textContent = `${hrs}:${mins}:${secs}`;
        
        const options = { year: "numeric", month: "long", day: "numeric" };
        dateEl.textContent = now.toLocaleDateString("en-US", options).toUpperCase();
    }
    setInterval(updateClock, 500);
    updateClock();

    // ── Ambient Audio BGM Controller ──
    let isBgmPlaying = false;
    let bgmSeconds = 0;
    let isSpotifyConnected = false;
    let isSpotifyPlaying = false;
    
    playPauseBgm.addEventListener("click", () => {
        playBeep("click");
        if (isSpotifyConnected) {
            const nextAction = isSpotifyPlaying ? "pause" : "play";
            fetch("/api/spotify/control", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: nextAction })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                    playBeep("success");
                    if (data.open_url) {
                        window.open(data.open_url, "spotify_player");
                    }
                    fetchStatus();
                } else {
                    playBeep("error");
                }
            })
            .catch(() => playBeep("error"));
            return;
        }

        if (isBgmPlaying) {
            ambientBgm.pause();
            playPauseBgm.textContent = "PLAY";
            isBgmPlaying = false;
        } else {
            ambientBgm.volume = 0.15;
            ambientBgm.play().then(() => {
                playPauseBgm.textContent = "MUTE";
                isBgmPlaying = true;
            }).catch(() => {
                alert("Interact with the page first to enable background audio loop.");
            });
        }
    });

    setInterval(() => {
        if (isSpotifyConnected) {
            return;
        }
        if (isBgmPlaying) {
            bgmSeconds = (bgmSeconds + 1) % 256;
            const min = String(Math.floor(bgmSeconds / 60)).padStart(2, "0");
            const sec = String(bgmSeconds % 60).padStart(2, "0");
            playerTime.textContent = `${min}:${sec}`;
            mediaProgress.style.width = `${(bgmSeconds / 256) * 100}%`;
        }
    }, 1000);

    // ── Security Lock Authorization Flow ──

    let authCheckTimeout = null;

    function checkAuth() {
        if (authCheckTimeout) clearTimeout(authCheckTimeout);
        
        fetch("/api/status")
            .then(res => res.json())
            .then(data => {
                if (data.is_locked) {
                    sessionStorage.removeItem("jarvis_verified");
                    lockScreen.classList.remove("hidden");
                    hudContainer.classList.add("hidden");
                    
                    // Automatically trigger video face verification once on page load
                    if (!hasAttemptedAutoScan) {
                        hasAttemptedAutoScan = true;
                        triggerAutomaticFaceScan();
                    }
                    
                    authCheckTimeout = setTimeout(checkAuth, 1000);
                } else {
                    sessionStorage.setItem("jarvis_verified", "true");
                    lockScreen.classList.add("hidden");
                    hudContainer.classList.remove("hidden");
                    if (!isMainHUDInitialized) {
                        initializeMainHUD();
                    }
                }
            })
            .catch(() => {
                if (window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1" && window.location.protocol !== "file:") {
                    if (!API_BASE) {
                        lockStatus.textContent = "OFFLINE: UPLINK NOT ESTABLISHED. CLICK 'LINK UPLINK' IN THE TOP-RIGHT TO CONFIGURE.";
                        lockStatus.style.color = "var(--danger)";
                    } else {
                        lockStatus.textContent = `OFFLINE: CANNOT REACH TUNNEL (${API_BASE}). VERIFY PORT OR TUNNEL IS ACTIVE.`;
                        lockStatus.style.color = "var(--danger)";
                    }
                } else {
                    lockStatus.textContent = "OFFLINE: CANNOT CONNECT TO LOCAL SERVER. RUN THE JARVIS BAT SHORTCUT.";
                    lockStatus.style.color = "var(--danger)";
                }
                authCheckTimeout = setTimeout(checkAuth, 2000);
            });
    }

    function triggerAutomaticFaceScan() {
        faceScannerWrap.classList.add("scanning");
        faceScannerText.textContent = "SCANNING...";
        lockStatus.textContent = "INITIATING AUTOMATIC VIDEO VERIFICATION...";

        // Try phone/browser camera first
        navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
        .then(stream => {
            const video = document.createElement("video");
            video.srcObject = stream;
            video.play();
            
            setTimeout(() => {
                const canvas = document.createElement("canvas");
                canvas.width = video.videoWidth || 640;
                canvas.height = video.videoHeight || 480;
                const ctx = canvas.getContext("2d");
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                
                stream.getTracks().forEach(track => track.stop());
                
                canvas.toBlob(blob => {
                    const formData = new FormData();
                    formData.append("image", blob, "face.jpg");
                    
                    fetch("/api/face_verify", {
                        method: "POST",
                        body: formData
                    })
                    .then(res => res.json())
                    .then(data => {
                        faceScannerWrap.classList.remove("scanning");
                        faceScannerText.textContent = "CAMERA STANDBY";
                        
                        if (data.verified) {
                            lockStatus.textContent = "BIOMETRIC VERIFIED. ACCESS GRANTED.";
                            lockStatus.style.color = "var(--success)";
                            setTimeout(unlockJarvis, 1000);
                        } else {
                            playBeep("error");
                            lockStatus.textContent = `VIDEO SHIELD FAILED: ${data.error || "NO RECOGNIZED USER"}. PLEASE ENTER PASSCODE.`;
                            lockStatus.style.color = "var(--warning)";
                        }
                    })
                    .catch(() => {
                        faceScannerWrap.classList.remove("scanning");
                        faceScannerText.textContent = "CAMERA STANDBY";
                        playBeep("error");
                        lockStatus.textContent = "COMMUNICATION EXCEPTION. PLEASE ENTER PASSCODE.";
                        lockStatus.style.color = "var(--warning)";
                    });
                }, "image/jpeg");
            }, 1000);
        })
        .catch(err => {
            console.log("Browser camera denied, falling back to backend webcam...", err);
            fetch("/api/face_verify", { method: "POST" })
            .then(res => res.json())
            .then(data => {
                faceScannerWrap.classList.remove("scanning");
                faceScannerText.textContent = "CAMERA STANDBY";
                
                if (data.verified) {
                    lockStatus.textContent = "BIOMETRIC VERIFIED. ACCESS GRANTED.";
                    lockStatus.style.color = "var(--success)";
                    setTimeout(unlockJarvis, 1000);
                } else {
                    playBeep("error");
                    lockStatus.textContent = `VIDEO SHIELD FAILED: ${data.error || "NO RECOGNIZED USER"}. PLEASE ENTER PASSCODE.`;
                    lockStatus.style.color = "var(--warning)";
                }
            })
            .catch(() => {
                faceScannerWrap.classList.remove("scanning");
                faceScannerText.textContent = "CAMERA STANDBY";
                playBeep("error");
                lockStatus.textContent = "VIDEO SOURCE OFFLINE. PLEASE ENTER PASSCODE.";
                lockStatus.style.color = "var(--warning)";
            });
        });
    }

    function unlockJarvis() {
        playBeep("success");
        sessionStorage.setItem("jarvis_verified", "true");
        lockScreen.classList.add("hidden");
        hudContainer.classList.remove("hidden");
        
        // Ensure backend state is unlocked
        fetch("/api/verify_passcode", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ passcode: "4598" })
        })
        .then(() => {
            if (!isMainHUDInitialized) {
                initializeMainHUD();
            }
            // Trigger Jarvis vocal greeting
            fetch("/api/command", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command: "hello jarvis" })
            });
        });
    }

    // Keyboard listener for manual passcode typing
    window.addEventListener("keydown", (e) => {
        // Only listen if lock screen is visible
        if (lockScreen.classList.contains("hidden")) return;
        
        // Check if numerical key
        if (e.key >= "0" && e.key <= "9") {
            if (enteredPasscode.length < 4) {
                enteredPasscode += e.key;
                keypadDisplay.textContent = "*".repeat(enteredPasscode.length);
                playBeep("click");
            }
        } else if (e.key === "Backspace") {
            enteredPasscode = enteredPasscode.slice(0, -1);
            keypadDisplay.textContent = "*".repeat(enteredPasscode.length);
            playBeep("click");
        } else if (e.key === "Escape") {
            enteredPasscode = "";
            keypadDisplay.textContent = "";
            playBeep("click");
        } else if (e.key === "Enter") {
            if (enteredPasscode.length === 4) {
                keyEnter.click();
            }
        }
    });


    // Keypad Digit inputs
    keyButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            playBeep("click");
            if (enteredPasscode.length < 4) {
                enteredPasscode += btn.getAttribute("data-val");
                keypadDisplay.textContent = "*".repeat(enteredPasscode.length);
            }
        });
    });

    keyClear.addEventListener("click", () => {
        playBeep("click");
        enteredPasscode = "";
        keypadDisplay.textContent = "";
    });

    keyEnter.addEventListener("click", () => {
        if (enteredPasscode.length === 0) return;
        fetch("/api/verify_passcode", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ passcode: enteredPasscode })
        })
        .then(res => res.json())
        .then(data => {
            if (data.verified) {
                unlockJarvis();
            } else {
                playBeep("error");
                enteredPasscode = "";
                keypadDisplay.textContent = "";
                lockStatus.textContent = "CRITICAL ERROR: PASSCODE INVALID. DENIED.";
                lockStatus.style.color = "var(--danger)";
                setTimeout(() => {
                    lockStatus.textContent = "SECURITY PROTOCOL ACTIVE. AUTHENTICATION REQUIRED.";
                    lockStatus.style.color = "var(--warning)";
                }, 3000);
            }
        })
        .catch(() => {
            playBeep("error");
        });
    });

    // Webcam Face Verification Scan
    btnFaceVerify.addEventListener("click", () => {
        playBeep("click");
        faceScannerWrap.classList.add("scanning");
        faceScannerText.textContent = "SCANNING...";
        lockStatus.textContent = "INITIATING FACIAL VECTOR SCAN PROTOCOL...";

        // Try phone/browser camera first
        navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } })
        .then(stream => {
            const video = document.createElement("video");
            video.srcObject = stream;
            video.play();
            
            setTimeout(() => {
                const canvas = document.createElement("canvas");
                canvas.width = video.videoWidth || 640;
                canvas.height = video.videoHeight || 480;
                const ctx = canvas.getContext("2d");
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                
                stream.getTracks().forEach(track => track.stop());
                
                canvas.toBlob(blob => {
                    const formData = new FormData();
                    formData.append("image", blob, "face.jpg");
                    
                    fetch("/api/face_verify", {
                        method: "POST",
                        body: formData
                    })
                    .then(res => res.json())
                    .then(data => {
                        faceScannerWrap.classList.remove("scanning");
                        faceScannerText.textContent = "CAMERA STANDBY";
                        
                        if (data.verified) {
                            lockStatus.textContent = "BIOMETRIC VERIFIED. ACCESS GRANTED.";
                            lockStatus.style.color = "var(--success)";
                            setTimeout(unlockJarvis, 1000);
                        } else {
                            playBeep("error");
                            lockStatus.textContent = `BIOMETRIC SHIELD: ${data.error || "UNKNOWN USER"}`;
                            lockStatus.style.color = "var(--danger)";
                            setTimeout(() => {
                                lockStatus.textContent = "SECURITY PROTOCOL ACTIVE. AUTHENTICATION REQUIRED.";
                                lockStatus.style.color = "var(--warning)";
                            }, 3000);
                        }
                    })
                    .catch(() => {
                        faceScannerWrap.classList.remove("scanning");
                        faceScannerText.textContent = "CAMERA STANDBY";
                        playBeep("error");
                        lockStatus.textContent = "COMMUNICATION EXCEPTION: CAMERA MODULE OFFLINE";
                        lockStatus.style.color = "var(--danger)";
                    });
                }, "image/jpeg");
            }, 1000);
        })
        .catch(err => {
            console.log("Browser camera denied, falling back to backend webcam...", err);
            fetch("/api/face_verify", { method: "POST" })
            .then(res => res.json())
            .then(data => {
                faceScannerWrap.classList.remove("scanning");
                faceScannerText.textContent = "CAMERA STANDBY";
                
                if (data.verified) {
                    lockStatus.textContent = "BIOMETRIC VERIFIED. ACCESS GRANTED.";
                    lockStatus.style.color = "var(--success)";
                    setTimeout(unlockJarvis, 1000);
                } else {
                    playBeep("error");
                    lockStatus.textContent = `BIOMETRIC SHIELD: ${data.error || "UNKNOWN USER"}`;
                    lockStatus.style.color = "var(--danger)";
                    setTimeout(() => {
                        lockStatus.textContent = "SECURITY PROTOCOL ACTIVE. AUTHENTICATION REQUIRED.";
                        lockStatus.style.color = "var(--warning)";
                    }, 3000);
                }
            })
            .catch(() => {
                faceScannerWrap.classList.remove("scanning");
                faceScannerText.textContent = "CAMERA STANDBY";
                playBeep("error");
                lockStatus.textContent = "COMMUNICATION EXCEPTION: CAMERA MODULE OFFLINE";
                lockStatus.style.color = "var(--danger)";
            });
        });
    });

    // ── API: Status Updates ──
    let lastStatus = "";
    
    function fetchStatus() {
        fetch("/api/status")
            .then(res => res.json())
            .then(data => {
                // Background speech check (for laptop speech in "both" mode)
                if (data.last_speech_id && data.last_speech_id !== playedSpeechId) {
                    const isNew = (playedSpeechId !== 0);
                    playedSpeechId = data.last_speech_id;
                    if (isNew && data.active_mic_device === "both") {
                        playTTSAudio(data.last_speech_id);
                    }
                }

                if (data.is_locked) {
                    sessionStorage.removeItem("jarvis_verified");
                    lockScreen.classList.remove("hidden");
                    checkAuth();
                    return;
                }

                // Sync active device from status payload
                if (data.active_mic_device && data.active_mic_device !== currentActiveDevice) {
                    applyDeviceUI(data.active_mic_device);
                }

                const status = data.status;
                
                // ── Dynamic Theme Engine — syncs entire UI to keyboard color ──
                if (data.keyboard_color) {
                    applyTheme(data.keyboard_color);
                }

                // Sync Spotify details
                isSpotifyConnected = data.spotify_logged_in;
                isSpotifyPlaying = data.spotify_is_playing;
                
                const trackEl = document.querySelector(".media-track");
                const artistEl = document.querySelector(".media-artist");
                
                if (isSpotifyConnected) {
                    trackEl.textContent = (data.spotify_track || "NO ACTIVE PLAYBACK").toUpperCase();
                    artistEl.textContent = (data.spotify_artist || "READY").toUpperCase();
                    artistEl.style.color = "var(--text-sec)";
                    
                    playPauseBgm.textContent = isSpotifyPlaying ? "PAUSE" : "PLAY";
                    spotifyDeviceSelector.style.display = "inline-block";
                    
                    if (data.spotify_duration > 0) {
                        const pct = (data.spotify_progress / data.spotify_duration) * 100;
                        mediaProgress.style.width = `${pct}%`;
                        
                        const totalSecs = Math.floor(data.spotify_progress / 1000);
                        const mins = String(Math.floor(totalSecs / 60)).padStart(2, "0");
                        const secs = String(totalSecs % 60).padStart(2, "0");
                        playerTime.textContent = `${mins}:${secs}`;
                    } else {
                        mediaProgress.style.width = "0%";
                        playerTime.textContent = "00:00";
                    }
                } else {
                    trackEl.textContent = "STARK INDUSTRIES SOUNDTRACK";
                    artistEl.innerHTML = (isBgmPlaying ? "BGM_LOOP_ACTIVE.WAV" : "BGM_LOOP_STANDBY.WAV") + 
                        ` | <span id="spotify-connect-btn" style="color: #ff9900; cursor: pointer; text-decoration: underline; font-weight: bold;">CONNECT SPOTIFY</span>`;
                    
                    spotifyDeviceSelector.style.display = "none";
                    spotifyDeviceDropdown.classList.add("hidden");
                    
                    const connectBtn = document.getElementById("spotify-connect-btn");
                    if (connectBtn) {
                        connectBtn.onclick = (e) => {
                            e.stopPropagation();
                            playBeep("click");
                            window.open("/api/spotify/login", "_blank");
                        };
                    }
                    
                    if (!isBgmPlaying) {
                        playPauseBgm.textContent = "PLAY";
                        mediaProgress.style.width = "0%";
                        playerTime.textContent = "00:00";
                    }
                }

                if (status === lastStatus) return;
                lastStatus = status;
                
                // Clear state classes
                reactorContainer.classList.remove("listening", "processing", "speaking");
                centerPanel.classList.remove("listening", "processing", "speaking");
                
                if (status === "listening") {
                    reactorContainer.classList.add("listening");
                    centerPanel.classList.add("listening");
                    reactorStatus.textContent = "MIC CAPTURE IN PROGRESS";
                    tickerTextEl.textContent = "SYSTEM ACTIVE - COMMAND STREAM DETECTED";
                } else if (status === "processing") {
                    reactorContainer.classList.add("processing");
                    centerPanel.classList.add("processing");
                    reactorStatus.textContent = "ANALYSIS SUB-PROCESS...";
                    tickerTextEl.textContent = "RESOLVING COGNITIVE SEMANTIC VECTOR";
                } else if (status === "speaking") {
                    reactorContainer.classList.add("speaking");
                    centerPanel.classList.add("speaking");
                    reactorStatus.textContent = "VOCAL SYNTH TRANSCRIPTION";
                    tickerTextEl.textContent = "TRANSMITTING RESPONSE MATRIX...";
                } else {
                    reactorStatus.textContent = "SYSTEM STANDBY";
                    tickerTextEl.textContent = "ALL CORES STABLE. READY FOR INTENT STREAM.";
                }
            })
            .catch(() => {});
    }

    // ── API: System Diagnostics ──
    function fetchStats() {
        fetch("/api/stats")
            .then(res => res.json())
            .then(data => {
                // CPU
                cpuVal.textContent = `${data.cpu}%`;
                cpuBar.style.width = `${data.cpu}%`;
                
                // RAM
                ramVal.textContent = `${data.ram.percent}%`;
                ramBar.style.width = `${data.ram.percent}%`;
                ramDetails.textContent = `${data.ram.used_gb} GB / ${data.ram.total_gb} GB`;
                
                // Disk
                diskVal.textContent = `${data.disk.percent}%`;
                diskBar.style.width = `${data.disk.percent}%`;
                diskDetails.textContent = `${data.disk.used_gb} GB / ${data.disk.total_gb} GB`;
                
                // Battery
                batteryVal.textContent = `${data.battery.percent}%`;
                batteryBar.style.width = `${data.battery.percent}%`;
                
                if (data.battery.charging) {
                    batterySource.textContent = "AC POWER SUPPLY - CHARGING";
                    batteryBar.classList.add("charging");
                } else {
                    batterySource.textContent = "INTERNAL LI-ON BATTERY CELL";
                    batteryBar.classList.remove("charging");
                }

                // Render GPU telemetry
                gpuVal.textContent = `${data.gpu.load}%`;
                gpuBar.style.width = `${data.gpu.load}%`;
                gpuDetails.textContent = `TEMP: ${data.gpu.temp}°C | VRAM: ${data.gpu.mem_used} GB / ${data.gpu.mem_total} GB`;

                // Render cooling system specs
                cpuTempEl.textContent = `${data.cpu_temp}°C`;
                cpuFanEl.textContent = `${data.cpu_fan_rpm} RPM`;
                gpuFanEl.textContent = `${data.gpu_fan_rpm} RPM`;
            })
            .catch(() => {});
    }

    // ── API: Environmental (Weather) ──
    function fetchWeather() {
        fetch("/api/weather")
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    weatherTemp.textContent = `${Math.round(data.temp)}°C`;
                    weatherCity.textContent = `${data.city.toUpperCase()}, IN`;
                    weatherCond.textContent = data.condition.toUpperCase();
                    wFeels.textContent = `${Math.round(data.feels_like)}°C`;
                    wHum.textContent = `${data.humidity}%`;
                    wWind.textContent = `${data.wind_speed} km/h`;
                }
            })
            .catch(() => {});
    }

    // ── API: To-Do Checklist ──
    function fetchTasks() {
        fetch("/api/tasks")
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    tasksList.innerHTML = `<li class="loading">SYNC ERROR</li>`;
                    return;
                }
                if (data.length === 0) {
                    tasksList.innerHTML = `<li>NO PENDING CORE OBJECTIVES</li>`;
                    return;
                }
                tasksList.innerHTML = "";
                data.forEach(task => {
                    const li = document.createElement("li");
                    li.innerHTML = `
                        <input type="checkbox" id="task-${task.id}" data-id="${task.id}" />
                        <span>${task.task_text.toUpperCase()}</span>
                    `;
                    
                    const cb = li.querySelector("input");
                    cb.addEventListener("change", (e) => {
                        playBeep("success");
                        const id = e.target.getAttribute("data-id");
                        completeTask(id);
                    });
                    
                    tasksList.appendChild(li);
                });
            })
            .catch(() => {
                tasksList.innerHTML = `<li class="loading">OFFLINE</li>`;
            });
    }
    
    function completeTask(id) {
        fetch("/api/tasks/complete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: id })
        })
        .then(res => res.json())
        .then(() => {
            fetchTasks();
        });
    }

    // ── API: Alarms Management ──

    function fetchAlarms() {
        fetch("/api/alarms")
            .then(res => res.json())
            .then(data => {
                if (data.length === 0) {
                    alarmsList.innerHTML = `<li>NO ACTIVE ALARMS</li>`;
                    return;
                }
                alarmsList.innerHTML = "";
                data.forEach(alarm => {
                    const li = document.createElement("li");
                    li.style.display = "flex";
                    li.style.justifyContent = "space-between";
                    li.style.alignItems = "center";
                    li.style.padding = "4px 0";
                    
                    const timeLabel = alarm.time;
                    const alarmLabel = alarm.label ? ` - ${alarm.label.toUpperCase()}` : "";
                    const activeStatus = alarm.active ? " (ACTIVE)" : " (RINGING/OFF)";
                    
                    li.innerHTML = `
                        <span>${timeLabel}${alarmLabel}${activeStatus}</span>
                        <button class="hud-btn mini-btn danger-btn" data-id="${alarm.id}">DELETE</button>
                    `;
                    
                    li.querySelector("button").addEventListener("click", (e) => {
                        playBeep("error");
                        const id = e.target.getAttribute("data-id");
                        deleteAlarm(id);
                    });
                    alarmsList.appendChild(li);
                });
            })
            .catch(() => {});
    }

    function deleteAlarm(id) {
        fetch("/api/alarms/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: parseInt(id) })
        })
        .then(res => res.json())
        .then(() => {
            fetchAlarms();
        });
    }

    alarmForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const timeVal = alarmTimeInput.value;
        const labelVal = alarmLabelInput.value.trim();
        if (!timeVal) return;

        playBeep("click");
        fetch("/api/alarms/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ time: timeVal, label: labelVal })
        })
        .then(res => res.json())
        .then(() => {
            alarmTimeInput.value = "";
            alarmLabelInput.value = "";
            fetchAlarms();
        });
    });

    // ── API: Console Activity Logs ──
    let lastLogLength = 0;
    let logIdsSeen = new Set();
    
    function fetchLogs() {
        fetch("/api/logs")
            .then(res => res.json())
            .then(data => {
                let hasNewLogs = false;
                data.forEach(log => {
                    const logKey = log.id || log.created_at;
                    if (!logIdsSeen.has(logKey)) {
                        logIdsSeen.add(logKey);
                        hasNewLogs = true;
                    }
                });
                
                if (!hasNewLogs && lastLogLength === data.length) return;
                lastLogLength = data.length;
                
                logFeed.innerHTML = "";
                data.slice().reverse().forEach(log => {
                    const timeStr = log.created_at ? log.created_at.substring(11, 19) : "00:00:00";
                    
                    // User transcript row
                    const userDiv = document.createElement("div");
                    userDiv.className = "log-entry user";
                    userDiv.innerHTML = `<span class="log-time">[${timeStr}]</span> USER: "${log.transcript.toUpperCase()}"`;
                    logFeed.appendChild(userDiv);
                    
                    // Jarvis response row
                    if (log.response) {
                        const respDiv = document.createElement("div");
                        respDiv.className = "log-entry response";
                        respDiv.innerHTML = `<span class="log-time">[${timeStr}]</span> JARVIS: "${log.response.toUpperCase()}"`;
                        logFeed.appendChild(respDiv);
                    }
                });
                logFeed.scrollTop = logFeed.scrollHeight;
            })
            .catch(() => {});
    }

    // ── Command Submission Form ──
    commandForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = commandInput.value.trim();
        if (!text) return;
        
        playBeep("click");
        commandInput.value = "";
        
        // Optimistically insert user log
        const timeStr = new Date().toUTCString().substring(17, 25);
        const userDiv = document.createElement("div");
        userDiv.className = "log-entry user";
        userDiv.innerHTML = `<span class="log-time">[${timeStr}]</span> USER: "${text.toUpperCase()}"`;
        logFeed.appendChild(userDiv);
        logFeed.scrollTop = logFeed.scrollHeight;
        
        fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: text })
        })
        .then(res => res.json())
        .then(data => {
            if (data.response) {
                playBeep("success");
                playTTSAudio(data.speech_id);
                if (data.open_url) {
                    window.open(data.open_url, "spotify_player");
                }
                fetchLogs(); // Sync logs
                fetchAlarms(); // Sync alarms in case an alarm was set via speech
            } else {
                playBeep("error");
            }
        })
        .catch(() => {
            playBeep("error");
            const errDiv = document.createElement("div");
            errDiv.className = "log-entry system";
            errDiv.innerHTML = `<span class="log-time">[${timeStr}]</span> [COM_ERROR] CRITICAL: TELEMETRY RETRANSMIT FAILED`;
            logFeed.appendChild(errDiv);
            logFeed.scrollTop = logFeed.scrollHeight;
        });
    });

    // ── Trigger Speech Interruption ──
    stopSpeechBtn.addEventListener("click", () => {
        playBeep("error");
        fetch("/api/stop", { method: "POST" })
            .then(res => res.json())
            .then(() => {
                fetchStatus();
            });
    });

    // ── Click Arc Reactor to focus input or start voice recognition ──
    reactorTrigger.addEventListener("click", () => {
        playBeep("click");

        // Block mobile mic if laptop has exclusive control
        if (currentActiveDevice === "laptop") {
            reactorStatus.textContent = "LAPTOP MIC ACTIVE";
            const w = document.createElement("div");
            w.className = "log-entry system";
            w.innerHTML = `[INPUT LOCK] LAPTOP MIC IS ACTIVE. SWITCH TO MOBILE IN THE FOOTER TO USE THIS DEVICE.`;
            logFeed.appendChild(w);
            logFeed.scrollTop = logFeed.scrollHeight;
            setTimeout(() => { reactorStatus.textContent = "SYSTEM STANDBY"; }, 3000);
            return;
        }

        if (isCustomRecording) {
            stopCustomAudioRecording();
        } else {
            if (isSpotifyConnected) {
                fetch("/api/spotify/control", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ action: "pause" })
                }).catch(() => {});
            }
            startMobileSpeechRecognition();
        }
    });

    // ── Footer Buttons ──
    btnLock.addEventListener("click", () => {
        playBeep("error");
        // Lock screen front-end simulation
        sessionStorage.removeItem("jarvis_verified");
        checkAuth();
        
        const entry = document.createElement("div");
        entry.className = "log-entry system";
        entry.innerHTML = `[SYSTEM SECURITY] LOCK COMMAND RECEIVED. INITIATING SHIELD SECURITY...`;
        logFeed.appendChild(entry);
        logFeed.scrollTop = logFeed.scrollHeight;
    });

    btnPower.addEventListener("click", () => {
        playBeep("error");
        const entry = document.createElement("div");
        entry.className = "log-entry system";
        entry.innerHTML = `[POWER SHIELD] CRITICAL: TERMINAL DEACTIVATION REQUESTED.`;
        logFeed.appendChild(entry);
        logFeed.scrollTop = logFeed.scrollHeight;
        
        const confirmShutdown = confirm("Initiate total terminal shutdown sequence, Sir?");
        if (confirmShutdown) {
            fetch("/api/command", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command: "power off" })
            });
        }
    });

    btnSyncAutomations.addEventListener("click", () => {
        playBeep("click");
        const entry = document.createElement("div");
        entry.className = "log-entry system";
        entry.innerHTML = `[CACHE PROCESS] SYNCING AUTOMATIONS TREE FROM DATABASE...`;
        logFeed.appendChild(entry);
        logFeed.scrollTop = logFeed.scrollHeight;
        
        fetch("/api/automations")
            .then(res => res.json())
            .then(data => {
                playBeep("success");
                const count = data.length || 0;
                const resultEntry = document.createElement("div");
                resultEntry.className = "log-entry system";
                resultEntry.innerHTML = `[SYNC COMPLETE] ${count} INTENT-MAPPINGS REGISTERED IN MEMORY BUFFER.`;
                logFeed.appendChild(resultEntry);
                logFeed.scrollTop = logFeed.scrollHeight;
            })
            .catch(() => {
                playBeep("error");
            });
    });

    function toggleSpotifyDeviceDropdown() {
        if (spotifyDeviceDropdown.classList.contains("hidden")) {
            fetchSpotifyDevices();
        } else {
            spotifyDeviceDropdown.classList.add("hidden");
        }
    }

    function fetchSpotifyDevices() {
        spotifyDeviceList.innerHTML = '<div class="log-entry system" style="padding: 5px;">SCANNING FOR OUTPUTS...</div>';
        spotifyDeviceDropdown.classList.remove("hidden");
        
        fetch("/api/spotify/devices")
            .then(res => res.json())
            .then(devices => {
                if (devices.error) {
                    spotifyDeviceList.innerHTML = `<div class="log-entry system" style="color: var(--danger); padding: 5px;">ERROR: ${devices.error.toUpperCase()}</div>`;
                    return;
                }
                
                if (devices.length === 0) {
                    spotifyDeviceList.innerHTML = '<div class="log-entry system" style="padding: 5px;">NO Wi-Fi SPEAKERS FOUND</div>';
                    return;
                }
                
                spotifyDeviceList.innerHTML = "";
                devices.forEach(device => {
                    const item = document.createElement("div");
                    item.className = "device-item";
                    if (device.is_active) {
                        item.classList.add("active");
                    }
                    
                    const typeLabel = device.type ? `(${device.type.toUpperCase()})` : "";
                    item.innerHTML = `
                        <span>${device.name.toUpperCase()}</span>
                        <span class="device-type font-mono">${typeLabel}</span>
                    `;
                    
                    item.addEventListener("click", (e) => {
                        e.stopPropagation();
                        playBeep("click");
                        switchSpotifyDevice(device.id, device.name);
                    });
                    
                    spotifyDeviceList.appendChild(item);
                });
            })
            .catch(() => {
                spotifyDeviceList.innerHTML = '<div class="log-entry system" style="color: var(--danger); padding: 5px;">OFFLINE</div>';
            });
    }

    function switchSpotifyDevice(deviceId, deviceName) {
        fetch("/api/spotify/devices/switch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_id: deviceId })
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === "success") {
                playBeep("success");
                spotifyDeviceDropdown.classList.add("hidden");
                
                const entry = document.createElement("div");
                entry.className = "log-entry system";
                entry.innerHTML = `[OUTPUT SWITCH] Spotify playback transferred to ${deviceName.toUpperCase()}`;
                logFeed.appendChild(entry);
                logFeed.scrollTop = logFeed.scrollHeight;
                
                fetchStatus();
            } else {
                playBeep("error");
            }
        })
        .catch(() => {
            playBeep("error");
        });
    }

    // Close dropdown when clicking outside
    document.addEventListener("click", () => {
        if (spotifyDeviceDropdown) {
            spotifyDeviceDropdown.classList.add("hidden");
        }
    });

    // ── HUD Initialization ──

    function initializeMainHUD() {
        isMainHUDInitialized = true;

        if (spotifyDeviceSelector) {
            spotifyDeviceSelector.addEventListener("click", (e) => {
                e.stopPropagation();
                playBeep("click");
                toggleSpotifyDeviceDropdown();
            });
        }

        // Wire device switcher pills
        devicePills.forEach(pill => {
            pill.addEventListener("click", () => {
                setActiveDevice(pill.dataset.device);
            });
        });

        // Start loops using an inline Web Worker to prevent background throttling
        const workerCode = `
            let timer = null;
            self.onmessage = function(e) {
                if (e.data === 'start') {
                    if (timer) clearInterval(timer);
                    timer = setInterval(() => {
                        self.postMessage('tick');
                    }, 1000);
                } else if (e.data === 'stop') {
                    if (timer) clearInterval(timer);
                }
            };
        `;
        
        try {
            const blob = new Blob([workerCode], { type: "application/javascript" });
            const worker = new Worker(URL.createObjectURL(blob));
            let tickCount = 0;
            
            worker.onmessage = function(e) {
                if (e.data === 'tick') {
                    tickCount++;
                    
                    // fetchStatus every 1s
                    fetchStatus();
                    
                    // fetchLogs every 2s
                    if (tickCount % 2 === 0) {
                        fetchLogs();
                    }
                    
                    // fetchStats, fetchAlarms, fetchActiveDevice every 5s
                    if (tickCount % 5 === 0) {
                        fetchStats();
                        fetchAlarms();
                        fetchActiveDevice();
                    }
                    
                    // fetchTasks every 10s
                    if (tickCount % 10 === 0) {
                        fetchTasks();
                    }
                    
                    // fetchWeather every 30s
                    if (tickCount % 30 === 0) {
                        fetchWeather();
                    }
                }
            };
            
            worker.postMessage('start');
        } catch (err) {
            console.warn("Background Web Worker failed to load, falling back to standard timers:", err);
            setInterval(fetchStatus, 1000);
            setInterval(fetchStats, 3000);
            setInterval(fetchWeather, 30000);
            setInterval(fetchTasks, 5000);
            setInterval(fetchAlarms, 5000);
            setInterval(fetchLogs, 2000);
            setInterval(fetchActiveDevice, 5000);
        }

        fetchStatus();
        fetchStats();
        fetchWeather();
        fetchTasks();
        fetchAlarms();
        fetchLogs();
        fetchActiveDevice();
    }

    // Run auth check immediately
    checkAuth();
});
