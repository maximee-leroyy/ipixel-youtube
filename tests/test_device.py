"""BLE connection: retries, host-wide lock. No real Bluetooth needed."""

import sys
import threading
import time

import pytest
from bleak.exc import BleakDeviceNotFoundError
from pypixelcolor.lib.device_info import DeviceInfo

from ipixel.display import device


class FakePanel(device.Panel):
    """A Panel without Bluetooth: fails `failures` times, then connects."""

    def __init__(self, failures: int) -> None:  # no super(): no event loop thread needed
        self.address = "AA:BB:CC:DD:EE:FF"
        self.failures = failures
        self.connects = 0
        self.disconnects = 0

    @property
    def info(self) -> DeviceInfo:
        return DeviceInfo(
            device_type=0, mcu_version="0.0", wifi_version="0.0", width=32, height=32, has_wifi=False, password_flag=255
        )

    def connect(self) -> None:
        self.connects += 1
        if self.connects <= self.failures:
            raise BleakDeviceNotFoundError(self.address, "not found")

    def disconnect(self) -> None:
        self.disconnects += 1

    def set_brightness(self, level: int) -> None:
        pass

    def delete(self, slot: int) -> None:
        pass


@pytest.fixture(autouse=True)
def no_wait(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr(device.time, "sleep", sleeps.append)
    monkeypatch.setattr(device, "release_stale_connection", lambda address: None)
    return sleeps


def test_retries_until_connected(no_wait: list[float]) -> None:
    panel = FakePanel(failures=2)
    device.connect_device(panel, attempts=None)
    assert panel.connects == 3
    assert panel.disconnects == 2  # each failed attempt is cleaned up
    assert len(no_wait) == 2


def test_gives_up_after_attempts() -> None:
    panel = FakePanel(failures=5)
    with pytest.raises(BleakDeviceNotFoundError):
        device.connect_device(panel, attempts=3)
    assert panel.connects == 3


def test_retry_delay_grows_then_caps() -> None:
    assert 3 <= device.retry_delay(1) <= 5
    assert 6 <= device.retry_delay(2) <= 8
    assert device.retry_delay(50) <= device.RETRY_MAX_S + 2


@pytest.mark.skipif(sys.platform != "linux", reason="abstract UNIX sockets are Linux-only (BlueZ hosts)")
def test_ble_lock_is_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device.time, "sleep", time.sleep)
    holding = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with device.ble_lock():
            holding.set()
            release.wait(5)

    thread = threading.Thread(target=holder)
    thread.start()
    holding.wait(5)
    with pytest.raises(TimeoutError):
        with device.ble_lock(timeout=0.1):
            pass
    release.set()
    thread.join()
    with device.ble_lock(timeout=0.1):
        pass
