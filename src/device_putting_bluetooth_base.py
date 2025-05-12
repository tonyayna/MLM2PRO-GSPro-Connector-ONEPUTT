import json
import logging

from PySide6.QtBluetooth import QBluetoothDeviceInfo
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from src.ball_data import BallData
from src.bluetooth.bluetooth_device_rssi_scanner import BluetoothDeviceRssiScanner
from src.bluetooth.bluetooth_device_scanner import BluetoothDeviceScanner
from src.device_base import DeviceBase
from src.log_message import LogMessageSystems, LogMessageTypes


class DevicePuttingBluetoothBase(DeviceBase):

    RSSI_SCAN_INTERVAL = 5000

    def __init__(self, main_window, device_names: list[str]) -> None:
        DeviceBase.__init__(self, main_window)
        self.device = None
        self._device_names: list[str] = device_names
        self._scanner: BluetoothDeviceScanner = BluetoothDeviceScanner(self._device_names)
        self._rssi_scanner: BluetoothDeviceRssiScanner = BluetoothDeviceRssiScanner(self._device_names)
        self._rssi_timer: QTimer = QTimer()
        self._rssi_timer.setInterval(DevicePuttingBluetoothBase.RSSI_SCAN_INTERVAL)
        self._rssi_timer.timeout.connect(self._rssi_scanner.scan)
        self.__setup_signals()
        self.__not_connected_status()

    def setup_device_thread(self) -> None:
        super().setup_device_thread()

    def __setup_signals(self) -> None:
        self.main_window.gspro_connection.club_selected.connect(self.__club_selected)

        self._scanner.device_found.connect(self.device_found)
        self._scanner.device_not_found.connect(self.__device_not_found)

        self._scanner.status_update.connect(self.__status_update)
        self._scanner.error.connect(self.__scanner_error)

        self._rssi_scanner.rssi.connect(self.__update_rssi)

    def __club_selected(self, club_data: dict) -> None:
        if self.device is not None:
            self.device.club_selected(club_data['Player']['Club'])
        logging.debug(f"{self.__class__.__name__} Club selected: {club_data['Player']['Club']}")

        if club_data['Player']['Club'] == 'PT':
            self.resume()
        else:
            self.pause()

    def start_app(self) -> None:
        pass

    def start(self) -> None:
        if self.device is None:
            self._scanner.scan()

    def is_running(self) -> bool:
        return self.device is not None

    def is_paused(self) -> bool:
        return self._pause

    def stop(self) -> None:
        if self.device is not None:
            self.__disconnect_device()

    def pause(self) -> None:
        self._pause = True

    def resume(self) -> None:
        self._pause = False

    def device_found(self, device: QBluetoothDeviceInfo) -> None:
        self.__update_rssi(device.rssi())

    def __device_not_found(self) -> None:
        msg = f"No device found.\n\n{self.start_message}"
        self.main_window.log_message(LogMessageTypes.LOGS, LogMessageSystems.BLUETOOTH, f'{msg}')
        QMessageBox.warning(self.main_window, "No putting device found", msg)
        self.__not_connected_status()

    def __scanner_error(self, error) -> None:
        msg = f"The following error occurred while scanning for a putting device:\n\n{error}"
        self.main_window.log_message(LogMessageTypes.LOGS, LogMessageSystems.BLUETOOTH, f'{msg}')
        QMessageBox.warning(self.main_window, "Error while scanning for a putting device", msg)
        self.__not_connected_status()

    def __status_update(self, status_message) -> None:
        self.main_window.putting_server_status_label.setText('Connecting...')
        self.main_window.putting_server_status_label.setStyleSheet(f"QLabel {{ background-color : orange; color : white; }}")

        self.main_window.putting_server_button.setText('Stop')
        self.main_window.putting_server_button.setEnabled(False)

    def __not_connected_status(self) -> None:
        self.main_window.putting_server_status_label.setText('Not connected')
        self.main_window.putting_server_status_label.setStyleSheet(f"QLabel {{ background-color : red; color : white; }}")

        self.main_window.putting_rssi_level.setText('')
        self.main_window.putting_rssi_level.setStyleSheet(f"QLabel {{ background-color : white; color : white; }}")

        self.main_window.putting_battery_status.setText('')
        self.main_window.putting_battery_status.setStyleSheet(f"QLabel {{ background-color : white; color : white; }}")

        self.main_window.putting_ready_status.setText('')
        self.main_window.putting_ready_status.setStyleSheet(f"QLabel {{ background-color : white; color : white; }}")

        self.main_window.putting_server_button.setText('Connect')
        self.main_window.putting_server_button.setEnabled(True)

    def _setup_device_signals(self) -> None:
        self.device.error.connect(self.__device_error)
        self.device.status_update.connect(self.__device_status_update)

        self.device.connected.connect(self.__device_connected)
        self.device.update_battery.connect(self.__update_battery)
        self.device.shot.connect(self.__shot_sent)

    def __shot_sent(self, ball_data: BallData) -> None:
        print(f"Putting shot sent: {json.dumps(ball_data.to_json())}")
        if self.main_window.gspro_connection.connected and not self._pause:
            self.main_window.gspro_connection.send_shot_worker.run(ball_data)

    def __update_battery(self, battery: int) -> None:
        self.main_window.putting_battery_status.setText(f"Battery: {battery}")
        if battery > 50:
            color = 'green'
        elif battery > 20:
            color = 'orange'
        else:
            color = 'red'

        if battery > 100:
            color = 'red'
            battery = 'N/A'

        self.main_window.putting_battery_status.setText(f"Battery: {battery}")
        self.main_window.putting_battery_status.setStyleSheet(f"QLabel {{ background-color : {color}; color : white; }}")

    def __device_connected(self, status) -> None:
        print('__device_connected')
        self.main_window.putting_server_status_label.setText('Connected')
        self.main_window.putting_server_status_label.setStyleSheet(f"QLabel {{ background-color : green; color : white; }}")

        self.main_window.putting_server_button.setText('Stop')
        self.main_window.putting_server_button.setEnabled(True)

        self._rssi_timer.start()

    def __device_error(self, error) -> None:
        if self.device is not None:
            self.__disconnect_device()
            logging.debug(f"Putting device error: {error}")
            self.main_window.log_message(LogMessageTypes.LOGS, LogMessageSystems.BLUETOOTH, error)
            QMessageBox.warning(self.main_window, "Bluetooth Connection Error", error)
        self.__not_connected_status()

    def __device_status_update(self, status: str, message: str) -> None:
        if status == 'ready_status':
            color = 'blue'
            if message == 'Waiting':
                color = 'green'
            self.main_window.putting_ready_status.setText(message)
            self.main_window.server_status_label.setStyleSheet(f"QLabel {{ background-color : {color}; color : white; }}")

    def __update_rssi(self, rssi: int) -> None:
        logging.debug(f"inside __update_putting_rssi: {rssi}")

        self.main_window.putting_rssi_level.setText(f"RSSI: {rssi}")
        if rssi > -60:
            color = 'green'
        elif rssi <= -60 and rssi >= -80:
            color = 'orange'
        else:
            color = 'red'
        self.main_window.putting_rssi_level.setStyleSheet(f"QLabel {{ background-color : {color}; color : white; }}")

    def __disconnect_device(self) -> None:
        if self.device is not None:
            print(f'{self.__class__.__name__} Disconnecting putting device')
            self.device.disconnect_device()
            self.device.shutdown()
            self.device = None
            self._rssi_timer.stop()
            self.__not_connected_status()

    def shutdown(self) -> None:
        self.__disconnect_device()
        super().shutdown()
