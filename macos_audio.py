"""
macos_audio.py — CoreAudio helpers: list output devices, switch default output,
and observe changes in real time.

Zero external dependencies: uses ctypes against CoreAudio.framework and
CoreFoundation.framework, both always present on macOS.

Public API
----------
list_output_devices() -> list[dict]
    Returns a list of dicts:
        {
            "uid":       str,   # stable device UID (use this as identifier)
            "name":      str,   # human-readable name shown in Control Center
            "device_id": int,   # transient CoreAudio numeric ID (session-only)
            "is_active": bool,  # True if this is the current default output
        }

set_default_output(uid: str) -> bool
    Switches macOS default audio output to the device identified by *uid*.
    Returns True on success, False if UID not found or CoreAudio call failed.

AudioDeviceCache
    Thread-safe cache that holds the last-known device list and can observe
    changes with a background polling thread.

    cache = AudioDeviceCache()
    cache.refresh()                        # manual refresh
    cache.get()                            # returns cached list[dict]
    cache.start_observer(callback, interval_s=5.0)
        # callback(devices: list[dict]) is called whenever the list or
        # active device changes. Runs in a daemon thread — safe to call
        # from any thread; the callback itself runs in the observer thread.

Quick test
----------
    python3 macos_audio.py
    python3 macos_audio.py --set "BuiltInSpeakerDevice"
    python3 macos_audio.py --watch          (live observer for 30 s)
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import logging
import sys
import threading
import time
from typing import Callable, Optional

_log = logging.getLogger("deckbridge.audio")

# ── Framework handles ─────────────────────────────────────────────────────────

_ca = ctypes.CDLL(ctypes.util.find_library("CoreAudio"))
_cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))

# ── CoreAudio constants ───────────────────────────────────────────────────────

_kAudioObjectSystemObject              = 1
_kAudioHardwarePropertyDevices         = 0x64657623  # 'dev#'
_kAudioHardwarePropertyDefaultOutput   = 0x644F7574  # 'dOut'
_kAudioObjectPropertyScopeGlobal       = 0x676C6F62  # 'glob'
_kAudioObjectPropertyScopeOutput       = 0x6F757470  # 'outp'
_kAudioObjectPropertyElementMain       = 0
_kAudioDevicePropertyDeviceNameCFStr   = 0x6C6E616D  # 'lnam'
_kAudioDevicePropertyDeviceUID         = 0x75696420  # 'uid '
_kAudioDevicePropertyStreams           = 0x73746D23  # 'stm#'

_kCFStringEncodingUTF8 = 0x08000100

# ── Structs ───────────────────────────────────────────────────────────────────

class _PropertyAddress(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope",    ctypes.c_uint32),
        ("mElement",  ctypes.c_uint32),
    ]

# ── Low-level helpers ─────────────────────────────────────────────────────────

def _get_property_size(object_id: int, selector: int, scope: int) -> int:
    addr = _PropertyAddress(selector, scope, _kAudioObjectPropertyElementMain)
    size = ctypes.c_uint32(0)
    _ca.AudioObjectGetPropertyDataSize(
        object_id, ctypes.byref(addr), 0, None, ctypes.byref(size)
    )
    return size.value


def _get_property_uint32(object_id: int, selector: int, scope: int) -> Optional[int]:
    addr = _PropertyAddress(selector, scope, _kAudioObjectPropertyElementMain)
    value = ctypes.c_uint32(0)
    size  = ctypes.c_uint32(4)
    status = _ca.AudioObjectGetPropertyData(
        object_id, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(value)
    )
    return value.value if status == 0 else None


def _get_property_uint32_array(object_id: int, selector: int, scope: int) -> list[int]:
    addr = _PropertyAddress(selector, scope, _kAudioObjectPropertyElementMain)
    size = ctypes.c_uint32(0)
    _ca.AudioObjectGetPropertyDataSize(
        object_id, ctypes.byref(addr), 0, None, ctypes.byref(size)
    )
    count = size.value // 4
    if count == 0:
        return []
    buf = (ctypes.c_uint32 * count)()
    _ca.AudioObjectGetPropertyData(
        object_id, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(buf)
    )
    return list(buf)


def _get_property_cfstring(object_id: int, selector: int, scope: int) -> str:
    addr   = _PropertyAddress(selector, scope, _kAudioObjectPropertyElementMain)
    cf_ref = ctypes.c_void_p(0)
    size   = ctypes.c_uint32(ctypes.sizeof(ctypes.c_void_p))
    status = _ca.AudioObjectGetPropertyData(
        object_id, ctypes.byref(addr), 0, None, ctypes.byref(size), ctypes.byref(cf_ref)
    )
    if status != 0 or not cf_ref.value:
        return ""
    buf = ctypes.create_string_buffer(512)
    _cf.CFStringGetCString(cf_ref, buf, 512, _kCFStringEncodingUTF8)
    _cf.CFRelease(cf_ref)
    return buf.value.decode("utf-8", errors="replace")


def _set_property_uint32(object_id: int, selector: int, scope: int, value: int) -> bool:
    addr  = _PropertyAddress(selector, scope, _kAudioObjectPropertyElementMain)
    val_c = ctypes.c_uint32(value)
    status = _ca.AudioObjectSetPropertyData(
        object_id, ctypes.byref(addr), 0, None, 4, ctypes.byref(val_c)
    )
    return status == 0


def _device_has_output(device_id: int) -> bool:
    """True when the device exposes at least one output stream."""
    size = _get_property_size(device_id, _kAudioDevicePropertyStreams,
                              _kAudioObjectPropertyScopeOutput)
    return size > 0

# ── Public API ────────────────────────────────────────────────────────────────

def list_output_devices() -> list[dict]:
    """
    Return all CoreAudio devices that have at least one output stream,
    in the same order macOS enumerates them.
    """
    default_id = _get_property_uint32(
        _kAudioObjectSystemObject,
        _kAudioHardwarePropertyDefaultOutput,
        _kAudioObjectPropertyScopeGlobal,
    )
    all_ids = _get_property_uint32_array(
        _kAudioObjectSystemObject,
        _kAudioHardwarePropertyDevices,
        _kAudioObjectPropertyScopeGlobal,
    )
    devices = []
    for dev_id in all_ids:
        if not _device_has_output(dev_id):
            continue
        name = _get_property_cfstring(dev_id, _kAudioDevicePropertyDeviceNameCFStr,
                                      _kAudioObjectPropertyScopeGlobal)
        uid  = _get_property_cfstring(dev_id, _kAudioDevicePropertyDeviceUID,
                                      _kAudioObjectPropertyScopeGlobal)
        devices.append({
            "uid":       uid,
            "name":      name,
            "device_id": dev_id,
            "is_active": dev_id == default_id,
        })
    return devices


def set_default_output(uid: str) -> bool:
    """
    Switch the macOS default audio output to the device identified by *uid*.
    Returns True on success, False if the UID is not found or the call fails.
    """
    for dev in list_output_devices():
        if dev["uid"] == uid:
            ok = _set_property_uint32(
                _kAudioObjectSystemObject,
                _kAudioHardwarePropertyDefaultOutput,
                _kAudioObjectPropertyScopeGlobal,
                dev["device_id"],
            )
            return ok
    return False  # UID not found


# ── Cache + observer ──────────────────────────────────────────────────────────

def _snapshot_key(devices: list[dict]) -> tuple:
    """Stable fingerprint: sorted UIDs + active UID. Changes when list or default changes."""
    active = next((d["uid"] for d in devices if d["is_active"]), "")
    return (tuple(sorted(d["uid"] for d in devices)), active)


class AudioDeviceCache:
    """
    Thread-safe cache of the current audio output device list.

    Usage::

        cache = AudioDeviceCache()
        cache.refresh()                          # populate immediately
        devices = cache.get()                    # [{"uid":…, "name":…, …}, …]
        cache.start_observer(my_callback, 5.0)  # watch for changes every 5 s
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._devices: list[dict] = []
        self._observer_thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable[[list[dict]], None]] = []
        self._observer_interval_s: float = 5.0

    # ── Public ────────────────────────────────────────────────────────────────

    def refresh(self) -> list[dict]:
        """Fetch the current device list from CoreAudio and update the cache."""
        try:
            devices = list_output_devices()
        except Exception as exc:
            _log.warning("audio: refresh failed: %s", exc)
            return self.get()
        with self._lock:
            self._devices = devices
        return devices

    def get(self) -> list[dict]:
        """Return the cached device list (empty until first refresh())."""
        with self._lock:
            return list(self._devices)

    def start_observer(
        self,
        on_change: Callable[[list[dict]], None],
        interval_s: float = 5.0,
    ) -> None:
        """
        Register *on_change* as a callback that fires whenever the device set or
        the active (default) device changes. Starts the background polling thread
        on the first call; subsequent calls add new callbacks to the same thread.
        All registered callbacks are fired on each change event.
        """
        with self._lock:
            self._callbacks.append(on_change)
            self._observer_interval_s = interval_s

        if self._observer_thread and self._observer_thread.is_alive():
            return  # thread already running; callback registered above

        def _loop() -> None:
            last_key = _snapshot_key(self.get())
            _log.debug("audio observer started (interval=%.1fs)", self._observer_interval_s)
            while True:
                time.sleep(self._observer_interval_s)
                try:
                    devices = self.refresh()
                    key = _snapshot_key(devices)
                    if key != last_key:
                        last_key = key
                        active = next((d["name"] for d in devices if d["is_active"]), "?")
                        _log.info(
                            "audio: device list changed — %d devices, active=%r",
                            len(devices), active,
                        )
                        with self._lock:
                            cbs = list(self._callbacks)
                        for cb in cbs:
                            try:
                                cb(devices)
                            except Exception as cb_exc:
                                _log.warning("audio observer callback error: %s", cb_exc)
                except Exception as exc:
                    _log.warning("audio observer poll error: %s", exc)

        t = threading.Thread(target=_loop, name="deckbridge-audio-observer", daemon=True)
        self._observer_thread = t
        t.start()


# ── Module-level shared cache (used by server.py) ─────────────────────────────

_shared_cache = AudioDeviceCache()


def get_cache() -> AudioDeviceCache:
    """Return the module-level shared AudioDeviceCache instance."""
    return _shared_cache


# ── CLI quick test ─────────────────────────────────────────────────────────────

def _print_devices(devices: list[dict]) -> None:
    print(f"\n{'Active':<8} {'Name':<40} {'UID'}")
    print("-" * 90)
    for d in devices:
        marker = "  ✓  " if d["is_active"] else "     "
        print(f"{marker}  {d['name']:<40} {d['uid']}")
    print()


if __name__ == "__main__":
    if sys.platform != "darwin":
        print("ERROR: macos_audio.py only runs on macOS.", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]

    if "--json" in args:
        print(json.dumps(list_output_devices(), indent=2))

    elif "--set" in args:
        idx = args.index("--set")
        uid = args[idx + 1] if idx + 1 < len(args) else ""
        if not uid:
            print("Usage: python3 macos_audio.py --set <uid>", file=sys.stderr)
            sys.exit(1)
        devices = list_output_devices()
        _print_devices(devices)
        print(f"Switching to: {uid}")
        ok = set_default_output(uid)
        if ok:
            print("✓ Default output changed successfully.")
            _print_devices(list_output_devices())
        else:
            print("✗ Failed — UID not found or CoreAudio error.", file=sys.stderr)
            sys.exit(1)

    elif "--watch" in args:
        import time as _time
        print("Watching for device changes (Ctrl-C to stop)…\n")
        cache = AudioDeviceCache()
        cache.refresh()
        _print_devices(cache.get())

        def _on_change(devices: list[dict]) -> None:
            print(f"\n[{_time.strftime('%H:%M:%S')}] Device list changed:")
            _print_devices(devices)

        cache.start_observer(_on_change, interval_s=2.0)
        try:
            while True:
                _time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")

    else:
        # Default: list devices
        devices = list_output_devices()
        _print_devices(devices)
        print("Tip: python3 macos_audio.py --set <uid>    to switch device")
        print("     python3 macos_audio.py --json         for JSON output")
        print("     python3 macos_audio.py --watch        live observer")
