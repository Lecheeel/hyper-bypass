#!/usr/bin/env python3

import argparse
import base64
import hmac
import json
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:
    print("Error: pycryptodome is required. Run: pip install pycryptodome")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests is required. Run: pip install requests")
    sys.exit(1)

# Constants
VERSION = "1.0"
API_CN = "https://unlock.update.miui.com/v1/"
API_GLOBAL = "https://unlock.update.intl.miui.com/v1/"
SIGN_KEY = "10f29ff413c89c8de02349cb3eb9a5f510f29ff413c89c8de02349cb3eb9a5f5"
DATA_PASS = "20nr1aobv2xi8ax4"
DATA_IV = b"0102030405060708"

# ANSI colors
COLOR_GREEN = "\033[32m"
COLOR_RED = "\033[31m"
COLOR_YELLOW = "\033[33m"
COLOR_RESET = "\033[0m"


def logf(msg: str = "", color: str = "", prefix: str = "-", level: str = "I") -> None:
    """Formatted log with optional color."""
    color_code = ""
    if color.upper() == "G":
        color_code = COLOR_GREEN
    elif color.upper() == "R":
        color_code = COLOR_RED
    elif color.upper() == "Y":
        color_code = COLOR_YELLOW

    level_map = {"W": "WARN", "E": "ERROR", "I": "INFO"}
    level_str = level_map.get(level.upper(), "INFO")

    timestamp = datetime.now().strftime("[%Y-%m-%d] [%H:%M:%S]")
    print(f"{timestamp} [{level_str}] {prefix} {color_code}{msg}{COLOR_RESET}")


def resolve_adb_path(adb_path: Optional[str], script_dir: Path) -> str:
    """Resolve ADB executable path."""
    if adb_path:
        path = Path(adb_path)
        if path.exists():
            return str(path.resolve())

    # Check libraries directory
    lib_dir = script_dir / "libraries"
    system = platform.system()
    if system == "Windows":
        adb_name = "adb.exe"
    elif system == "Darwin":
        adb_name = "adb-darwin"
    else:
        adb_name = "adb"

    lib_adb = lib_dir / adb_name
    if lib_adb.exists():
        return str(lib_adb.resolve())

    # Fallback to PATH
    return adb_name


def run_adb(adb_bin: str, command: str, raw: bool = False) -> tuple[list[str] | str, int]:
    """Execute ADB command and return output."""
    full_cmd = f"{adb_bin} {command}"
    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        if raw:
            return output.strip(), result.returncode
        lines = [l for l in output.strip().split("\n") if l]
        return lines, result.returncode
    except subprocess.TimeoutExpired:
        return [], -1
    except Exception as e:
        logf(f"ADB error: {e}", "r", "!", "E")
        return [], -1


def get_devices(adb_bin: str) -> list[tuple[str, str, bool]]:
    """Get list of connected devices. Returns [(serial, transport_id, use_transport_flag), ...]."""
    lines, ret = run_adb(adb_bin, "devices -l")
    if ret != 0 or not lines:
        return []

    devices = []
    for line in lines[1:]:  # Skip "List of devices attached"
        line = re.sub(r"[ \t]+", " ", line.strip())
        parts = line.split(" ")
        if len(parts) < 2:
            continue
        status = parts[1]
        if status != "device" and status != "recovery":
            continue

        serial = parts[0]
        transport_id = ""
        for p in parts[2:]:
            if p.startswith("transport_id:"):
                transport_id = p.replace("transport_id:", "")
                break
        # Fallback: use serial if no transport_id (older adb)
        use_transport = bool(transport_id)
        if not transport_id:
            transport_id = serial

        devices.append((serial, transport_id, use_transport))

    return devices


def get_device_id(transport_id: str, use_transport: bool = True) -> str:
    """Get ADB device selector string. Use -t for numeric transport_id, -s for serial."""
    if not transport_id:
        return ""
    return f"-t {transport_id} " if use_transport else f"-s {transport_id} "


def get_current_activity(adb_bin: str, device_id: str) -> tuple[str | None, str | None]:
    """Get current foreground activity. Returns (package, activity) or (None, None)."""
    cmd = f'{device_id}shell "dumpsys window | grep mCurrentFocus"'
    lines, ret = run_adb(adb_bin, cmd)
    if ret != 0 or not lines:
        return None, None

    line = lines[0] if lines else ""
    if "mCurrentFocus=Window" not in line:
        return None, None

    match = re.search(r"Window\{(.*)\}", line)
    if not match:
        return None, None

    window_parts = match.group(1).split(" ")
    last_part = window_parts[-1] if window_parts else ""
    components = last_part.split("/")
    package = components[0] if len(components) > 0 else None
    activity = components[1] if len(components) > 1 else None
    return package, activity


def clear_logcat(adb_bin: str, device_id: str) -> None:
    """Clear logcat buffer."""
    run_adb(adb_bin, f"{device_id}logcat -c")


def decrypt_data(data: str) -> Optional[str]:
    """Decrypt AES-128-CBC data."""
    try:
        raw = base64.b64decode(data)
        cipher = AES.new(DATA_PASS.encode(), AES.MODE_CBC, DATA_IV)
        decrypted = cipher.decrypt(raw)
        unpadded = unpad(decrypted, AES.block_size)
        return unpadded.decode("utf-8", errors="replace")
    except Exception:
        return None


def sign_data(data: str, sign_key: str) -> str:
    """Sign data using HMAC SHA-1."""
    msg = f"POST\n/v1/unlock/applyBind\ndata={data}&sid=miui_sec_android"
    sig = hmac.new(
        sign_key.encode(),
        msg.encode(),
        "sha1",
    ).digest()
    return sig.hex().lower()


def post_api(
    api_base: str,
    endpoint: str,
    data: dict,
    headers: list[str],
    use_form: bool = True,
) -> Optional[dict]:
    """POST to API and return JSON response or None."""
    url = api_base.rstrip("/") + "/" + endpoint.lstrip("/")
    req_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    for h in headers:
        if ":" in h:
            k, v = h.split(":", 1)
            req_headers[k.strip()] = v.strip()

    try:
        if use_form:
            resp = requests.post(
                url,
                data=data,
                headers=req_headers,
                timeout=10,
                verify=False,
            )
        else:
            resp = requests.post(
                url,
                json=data,
                headers=req_headers,
                timeout=10,
                verify=False,
            )

        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def capture_bind_request(
    adb_bin: str, device_id: str
) -> tuple[Optional[str], Optional[str]]:
    """Capture args and headers from logcat. Returns (args, headers)."""
    args_val: Optional[str] = None
    headers_val: Optional[str] = None

    args_re = re.compile(r"args:(.*)")
    headers_re = re.compile(r"headers:(.*)")

    cmd = f"{adb_bin} {device_id}logcat *:S CloudDeviceStatus:V"
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            line = line.strip()
            if "CloudDeviceStatus: args:" in line:
                m = args_re.search(line)
                if m:
                    args_val = m.group(1).strip()
                run_adb(adb_bin, f"{device_id}shell svc data disable")

            if "CloudDeviceStatus: headers:" in line:
                m = headers_re.search(line)
                if m:
                    headers_val = m.group(1).strip()
                logf("Account bind request found! Let's block it.")
                break

        proc.terminate()
        proc.wait(timeout=2)
    except Exception as e:
        logf(f"Logcat capture error: {e}", "r", "!", "E")

    return args_val, headers_val


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Xiaomi HyperOS BootLoader Bypass - Python Edition"
    )
    parser.add_argument(
        "-g",
        "--global",
        dest="use_global",
        action="store_true",
        help="Use international API (for non-China ROM)",
    )
    parser.add_argument(
        "-p",
        "--adb-path",
        dest="adb_path",
        type=str,
        default=None,
        help="Path to adb executable",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    adb_bin = resolve_adb_path(args.adb_path, script_dir)

    api_base = API_GLOBAL if args.use_global else API_CN
    sign_key = SIGN_KEY

    # Banner
    logf("************************************", "g")
    logf("* Xiaomi HyperOS BootLoader Bypass *", "g")
    logf(f"* Python Edition      Version {VERSION} *", "g")
    logf("************************************", "g")

    logf("Starting ADB server...")
    run_adb(adb_bin, "root")

    devices = get_devices(adb_bin)
    while len(devices) != 1:
        if len(devices) == 0:
            logf("Waiting for device connection...")
        else:
            logf(
                f"Only one device is allowed to connect, disconnect others to continue. Current number of devices: {len(devices)}"
            )
        time.sleep(1)
        devices = get_devices(adb_bin)

    device = devices[0]
    serial, transport_id, use_transport = device
    device_id = get_device_id(transport_id, use_transport=use_transport)

    logf(f"Processing device {serial}({transport_id})...")

    clear_logcat(adb_bin, device_id)
    run_adb(adb_bin, f"{device_id}shell svc data enable")

    logf("Finding BootLoader unlock bind request...")

    package, activity = get_current_activity(adb_bin, device_id)
    if package != "com.android.settings":
        if package != "NotificationShade":
            run_adb(
                adb_bin,
                f'{device_id}shell am start -a android.settings.APPLICATION_DEVELOPMENT_SETTINGS',
            )
    else:
        if activity != "com.android.settings.bootloader.BootloaderStatusActivity":
            run_adb(
                adb_bin,
                f'{device_id}shell am start -a android.settings.APPLICATION_DEVELOPMENT_SETTINGS',
            )

    logf("Now you can bind account in the developer options.", "y", "*")

    args_val, headers_val = capture_bind_request(adb_bin, device_id)

    if not args_val or not headers_val:
        logf("Failed to capture bind request. Please try again.", "r", "!")
        sys.exit(1)

    logf("Refactoring parameters...")

    decrypted_args = decrypt_data(args_val)
    if not decrypted_args:
        logf("Failed to decrypt args.", "r", "!")
        sys.exit(1)

    data_obj = json.loads(decrypted_args)
    data_obj["rom_version"] = data_obj["rom_version"].replace("V816", "V14")
    data_str = json.dumps(data_obj, separators=(",", ":"))
    sign = sign_data(data_str, sign_key)

    decrypted_headers = decrypt_data(headers_val)
    if not decrypted_headers:
        logf("Failed to decrypt headers.", "r", "!")
        sys.exit(1)

    cookie_match = re.search(r"Cookie=\[(.*)\]", decrypted_headers)
    cookies = cookie_match.group(1).strip() if cookie_match else ""

    logf("Sending POST request...")
    res = post_api(
        api_base,
        "unlock/applyBind",
        {"data": data_str, "sid": "miui_sec_android", "sign": sign},
        [f"Cookie: {cookies}"],
        use_form=True,
    )

    run_adb(adb_bin, f"{device_id}shell svc data enable")

    if not res:
        logf("Fail to send request, check your internet connection.", "r", "!")
        sys.exit(1)

    code = res.get("code", -1)
    if code == 0:
        logf(f"Target account: {res.get('data', {}).get('userId', '')}", "g")
        logf("Account bound successfully, wait time can be viewed in the unlock tool.", "g")
    elif code == 401:
        logf("Account credentials have expired, re-login to your account in your phone. (401)", "y")
    elif code == 20086:
        logf("Device credentials expired. (20086)", "y")
    elif code == 30001:
        logf(
            "Binding failed, this device has been forced to verify the account qualification by Xiaomi. (30001)",
            "y",
        )
    elif code == 86015:
        logf("Fail to bind account, invalid device signature. (86015)", "y")
    else:
        logf(f"{res.get('descEN', 'Unknown error')} ({code})", "y")


if __name__ == "__main__":
    main()
