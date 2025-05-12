from typing import Optional

from PySide6.QtBluetooth import QBluetoothDeviceInfo

from src.bluetooth.oneputt_device import OnePuttDevice
from src.device_putting_bluetooth_base import DevicePuttingBluetoothBase


class DevicePuttingBluetoothOnePutt(DevicePuttingBluetoothBase):
    def __init__(self, main_window) -> None:
        DevicePuttingBluetoothBase.__init__(self, main_window=main_window, device_names=['OnePutt-'])
        self.device: Optional[OnePuttDevice] = None

    def device_found(self, device: QBluetoothDeviceInfo) -> None:
        super().device_found(device)
        if self.device is not None:
            self.device.disconnect_device()
            self.device.shutdown()
            self.device = None
        self.device = OnePuttDevice(device)
        self._setup_device_signals()
        self.device.connect_device()

    @property
    def start_message(self) -> str:
        return 'Before starting Bluetooth connection ensure your OnePutt is turned on.'
