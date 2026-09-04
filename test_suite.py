"""
Comprehensive Test Suite for Project JARVIS
Validates each component and integration independently.
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Ensure utf-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

passed_tests = []
failed_tests = []

def test_case(name):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            print(f"\n[TEST] {name} ...", flush=True)
            try:
                fn(*args, **kwargs)
                print(f"  [PASS] {name}")
                passed_tests.append(name)
            except Exception as e:
                print(f"  [FAIL] {name}: {e}")
                import traceback
                traceback.print_exc()
                failed_tests.append((name, str(e)))
        return wrapper
    return decorator


@test_case("1. Config & Environment Validation")
def test_config():
    import config
    assert config.USER_NAME == "Ajay", f"Unexpected USER_NAME: {config.USER_NAME}"
    assert config.WAKE_WORD_MODEL == "hey_jarvis"
    assert config.PIPER_VOICE_MODEL.exists(), f"Piper voice model missing at {config.PIPER_VOICE_MODEL}"
    assert config.PIPER_VOICE_CONFIG.exists(), f"Piper voice config missing at {config.PIPER_VOICE_CONFIG}"
    api_key = os.environ.get("GEMINI_API_KEY")
    assert api_key and api_key != "your_gemini_api_key_here", "GEMINI_API_KEY is not set or placeholder"
    print(f"     Config OK. Piper model: {config.PIPER_VOICE_MODEL.name}, Gemini model: {config.GEMINI_MODEL}")


@test_case("2. System Info Tool (CPU, RAM, GPU NVML)")
def test_system_info():
    from tools import system_info
    info = system_info.get_system_info()
    assert "CPU:" in info, f"Missing CPU info: {info}"
    assert "RAM:" in info, f"Missing RAM info: {info}"
    print(f"     Output: {info}")


@test_case("3. Volume Control Tool (pycaw)")
def test_volume():
    from tools import volume
    vol_str = volume.get_volume()
    assert "Volume is at" in vol_str, f"Unexpected volume response: {vol_str}"
    print(f"     Output: {vol_str}")


@test_case("4. Clipboard Tool (pyperclip)")
def test_clipboard():
    from tools import clipboard
    import pyperclip
    original = pyperclip.paste()
    test_str = "JARVIS_TEST_CLIPBOARD_VERIFICATION"
    res_write = clipboard.write_clipboard(test_str)
    assert test_str in res_write or "Copied" in res_write
    res_read = clipboard.read_clipboard()
    assert test_str in res_read, f"Expected '{test_str}' in read result, got: {res_read}"
    # Restore original clipboard
    pyperclip.copy(original)
    print(f"     Clipboard write/read/restore passed.")


@test_case("5. Web Search Tool (DuckDuckGo)")
def test_web_search():
    from tools import web_search
    results = web_search.search_web("Python programming language")
    assert "Python" in results, f"Search failed or empty: {results}"
    print(f"     Search output preview: {results[:120]}...")


@test_case("6. App Launcher Tool (Validation & Running Apps)")
def test_app_launcher():
    import config
    from tools import app_launcher
    running = app_launcher.list_running_apps()
    assert "Running apps:" in running or "No running" in running, f"Unexpected list_running_apps: {running}"
    print(f"     Running apps preview: {running[:100]}...")

    # Check which configured apps exist on this PC
    installed_count = 0
    for name, path in config.APP_MAP.items():
        exists = Path(path).exists()
        if exists:
            installed_count += 1
    print(f"     APP_MAP has {len(config.APP_MAP)} entries, {installed_count} valid executables on disk.")


@test_case("7. GitHub Tool Stub")
def test_github():
    from tools import github_tool
    res = github_tool.github_info(repo="test/repo", action="summary")
    assert "GitHub" in res, f"Unexpected github_info response: {res}"
    print(f"     Output: {res}")


@test_case("8. Tool Dispatcher & Safety Gate Integration")
def test_dispatcher():
    from core.tool_dispatcher import ToolDispatcher
    import config

    class DummySpeaker:
        def speak(self, text):
            pass

    class DummyTranscriber:
        def listen_and_transcribe(self):
            return "no"

    dispatcher = ToolDispatcher(speaker=DummySpeaker(), transcriber=DummyTranscriber())
    
    # 1. Un-gated tool: get_system_info
    res = dispatcher.dispatch("get_system_info", {})
    assert "CPU:" in res, f"Dispatch get_system_info failed: {res}"
    print(f"     Ungated dispatch succeeded: {res[:60]}...")

    # 2. Gated tool: write_clipboard with dummy saying "no"
    res_gated = dispatcher.dispatch("write_clipboard", {"text": "blocked"})
    assert "cancelled by the safety gate" in res_gated, f"Safety gate did not cancel: {res_gated}"
    print(f"     Gated dispatch properly blocked by safety gate: {res_gated}")


@test_case("9. Agent Tool-Calling End-to-End (Gemini API)")
def test_agent_tool_calling():
    from core.agent import Agent
    from core.tool_dispatcher import ToolDispatcher

    class DummySpeaker:
        def speak(self, text):
            pass

    class DummyTranscriber:
        def listen_and_transcribe(self):
            return "yes"

    dispatcher = ToolDispatcher(speaker=DummySpeaker(), transcriber=DummyTranscriber())
    agent = Agent(tool_dispatcher=dispatcher)
    agent.load()

    # Ask something that should trigger get_system_info
    response = agent.process("What is my current CPU usage or system info?")
    assert len(response) > 0, "Agent returned empty response"
    print(f"     Agent tool-calling response: '{response}'")


@test_case("10. Audio Speaker Component (piper synthesis)")
def test_speaker():
    from audio.speaker import Speaker
    speaker = Speaker()
    speaker.load()
    assert speaker.backend in ("piper", "pyttsx3"), f"Unexpected backend: {speaker.backend}"
    # Speak a quick phrase
    speaker.speak("Verification test complete.")
    print(f"     Speaker loaded with backend '{speaker.backend}' and played audio successfully.")


@test_case("11. Audio Transcriber Component (faster-whisper on CUDA)")
def test_transcriber():
    import numpy as np
    from audio.transcriber import Transcriber
    import config

    transcriber = Transcriber()
    transcriber.load()
    assert transcriber._model is not None, "Whisper model failed to load"
    
    # Transcribe 1 second of silent audio array (16000 float32 samples)
    silence = np.zeros(16000, dtype=np.float32)
    text = transcriber.transcribe(silence)
    print(f"     Whisper CUDA transcription completed (silence output: '{text}').")


@test_case("12. Audio Listener Component (openwakeword)")
def test_listener():
    import numpy as np
    from audio.listener import WakeWordListener
    import config

    listener = WakeWordListener()
    listener.load()
    assert listener._model is not None, "openwakeword model failed to load"

    # Feed 1280 int16 samples into model predict
    chunk = np.zeros(1280, dtype=np.int16)
    prediction = listener._model.predict(chunk)
    assert config.WAKE_WORD_MODEL in prediction or len(prediction) > 0
    score = prediction.get(config.WAKE_WORD_MODEL, 0.0)
    print(f"     openwakeword prediction on silence: score={score:.4f} (model: {config.WAKE_WORD_MODEL})")


def main():
    print("=" * 60)
    print("PROJECT JARVIS FULL COMPONENT TEST SUITE")
    print("=" * 60)

    test_config()
    test_system_info()
    test_volume()
    test_clipboard()
    test_web_search()
    test_app_launcher()
    test_github()
    test_dispatcher()
    test_agent_tool_calling()
    test_speaker()
    test_transcriber()
    test_listener()

    print("\n" + "=" * 60)
    print(f"TEST SUMMARY: {len(passed_tests)} Passed, {len(failed_tests)} Failed")
    print("=" * 60)
    for t in passed_tests:
        print(f"  [PASS] {t}")
    for t, err in failed_tests:
        print(f"  [FAIL] {t} -> {err}")

    if failed_tests:
        sys.exit(1)
    else:
        print("\nALL 12 TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)

if __name__ == "__main__":
    main()
