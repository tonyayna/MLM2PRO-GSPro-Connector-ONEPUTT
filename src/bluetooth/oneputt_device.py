import logging
import struct
from typing import Optional

from PySide6.QtBluetooth import (
    QBluetoothDeviceInfo,
    QBluetoothUuid,
    QLowEnergyCharacteristic,
)
from PySide6.QtCore import QByteArray, QUuid

from src.ball_data import BallData, PuttType
from src.bluetooth.bluetooth_device_base import BluetoothDeviceBase
from src.bluetooth.bluetooth_device_service import BluetoothDeviceService
from src.bluetooth.bluetooth_utils import BluetoothUtils


class OnePuttDevice(BluetoothDeviceBase):

    HEARTBEAT_INTERVAL = 2000
    ONEPUTT_HEARTBEAT_INTERVAL = 20000

    BATTERY_SERVICE_UUID = QBluetoothUuid(QUuid('{5bc7050a-9607-4cf4-bbd5-e9017ba8a580}'))
    BATTERY_CHARACTERISTIC_UUID = QBluetoothUuid(QUuid('{5bc7050b-9607-4cf4-bbd5-e9017ba8a580}'))

    DEVICE_INFO_SERVICE_UUID = QBluetoothUuid(QUuid('{84d32310-fc87-44bd-a97a-fe7116f7ee7a}'))
    FIRMWARE_CHARACTERISTIC_UUID = QBluetoothUuid(QUuid('{84d32311-fc87-44bd-a97a-fe7116f7ee7a}'))
    MODEL_CHARACTERISTIC_UUID = QBluetoothUuid(QUuid('{84d32312-fc87-44bd-a97a-fe7116f7ee7a}'))
    SERIAL_NUMBER_CHARACTERISTIC_UUID = QBluetoothUuid(QUuid('{84d32313-fc87-44bd-a97a-fe7116f7ee7a}'))

    MEASUREMENT_SERVICE_UUID = QBluetoothUuid(QUuid('{99c8887f-c000-45b2-aa71-60a482a5c19a}'))
    MEASUREMENT_CHARACTERISTIC_UUID = QBluetoothUuid(QUuid('{99c88872-c000-45b2-aa71-60a482a5c19a}'))
    READY_STATUS_CHARACTERISTIC_UUID = QBluetoothUuid(QUuid('{99c88873-c000-45b2-aa71-60a482a5c19a}'))

    def __init__(self, device: QBluetoothDeviceInfo) -> None:
        self._services: Optional[list[BluetoothDeviceService]] = []

        self._device_info_service: BluetoothDeviceService = BluetoothDeviceService(
            device,
            OnePuttDevice.DEVICE_INFO_SERVICE_UUID,
            None,
            None,
            self._device_info_service_read_handler,
        )
        self._device_info_service.services_discovered.connect(self._services_discovered)
        self._services.append(self._device_info_service)

        self._battery_service: BluetoothDeviceService = BluetoothDeviceService(
            device,
            OnePuttDevice.BATTERY_SERVICE_UUID,
            [OnePuttDevice.BATTERY_CHARACTERISTIC_UUID],
            self._battery_info_handler,
            None,
        )
        self._services.append(self._battery_service)

        self._measurement_service: BluetoothDeviceService = BluetoothDeviceService(
            device,
            OnePuttDevice.MEASUREMENT_SERVICE_UUID,
            [OnePuttDevice.MEASUREMENT_CHARACTERISTIC_UUID,
             OnePuttDevice.READY_STATUS_CHARACTERISTIC_UUID],
            self._measurement_handler,
            None,
        )
        self._services.append(self._measurement_service)

        super().__init__(device,
                         self._services,
                         OnePuttDevice.HEARTBEAT_INTERVAL,
                         OnePuttDevice.ONEPUTT_HEARTBEAT_INTERVAL)

        self._counter = 0

    def _device_info_service_read_handler(self, characteristic: QLowEnergyCharacteristic, data: QByteArray) -> None:
        decoded_data = data.data().decode('utf-8')
        if characteristic.uuid() == OnePuttDevice.SERIAL_NUMBER_CHARACTERISTIC_UUID:
            self._serial_number = decoded_data
            msg = f'Serial number: {self._serial_number}'
        elif characteristic.uuid() == OnePuttDevice.FIRMWARE_CHARACTERISTIC_UUID:
            self._firmware_version = decoded_data
            msg = f'Firmware version: {self._firmware_version}'
        elif characteristic.uuid() == OnePuttDevice.MODEL_CHARACTERISTIC_UUID:
            self._model = decoded_data
            msg = f'Model: {self._model}'
        else:
            msg = f'Unknown characteristic: {characteristic.uuid().toString()}'
        print(msg)
        logging.debug(msg)

    def _services_discovered(self, service: QBluetoothUuid) -> None:
        if service == OnePuttDevice.DEVICE_INFO_SERVICE_UUID:
            msg = f'Reading device info for {self._ble_device.name()} at {self._sensor_address()}'
            print(msg)
            logging.debug(msg)
            self._device_info_service.read_characteristic(OnePuttDevice.SERIAL_NUMBER_CHARACTERISTIC_UUID)
            self._device_info_service.read_characteristic(OnePuttDevice.FIRMWARE_CHARACTERISTIC_UUID)
            self._device_info_service.read_characteristic(OnePuttDevice.MODEL_CHARACTERISTIC_UUID)
            self.connected.emit('connected')

    def _battery_info_handler(self, characteristic: QLowEnergyCharacteristic, data: QByteArray) -> None:
        msg = f'<---- (battery) Received data for characteristic {characteristic.uuid().toString()}: {BluetoothUtils.byte_array_to_hex_string(data.data())}'
        print(msg)
        logging.debug(msg)
        self.update_battery.emit(struct.unpack_from('<H', data, 0)[0])
        msg = f'Battery level: {struct.unpack_from("<H", data, 0)[0]}'
        print(msg)
        logging.debug(msg)

    def _measurement_handler(self, characteristic: QLowEnergyCharacteristic, data: QByteArray) -> None:
        msg = f'<---- (measurements handler) Received data for characteristic {characteristic.uuid().toString()}: {BluetoothUtils.byte_array_to_hex_string(data.data())}'
        logging.debug(msg)
        if characteristic.uuid() == OnePuttDevice.MEASUREMENT_CHARACTERISTIC_UUID:
            self._process_shot(data.data())
        elif characteristic.uuid() == OnePuttDevice.READY_STATUS_CHARACTERISTIC_UUID:
            ready = struct.unpack('B', data.data())[0]

            self.status_update.emit('ready_status', 'Waiting' if ready else 'Not Ready')

    def _process_shot(self, data: bytearray) -> None:
        shot_number = struct.unpack_from('<H', data, 0)[0]
        speed = struct.unpack_from('<f', data, 2)[0]
        vla = struct.unpack_from('<f', data, 6)[0]
        hla = struct.unpack_from('<f', data, 10)[0]
        max_launch_angle = struct.unpack_from('<f', data, 14)[0]
        min_launch_angle = struct.unpack_from('<f', data, 18)[0]

        if 200 <= speed <= 15000:
            if self._counter < shot_number or shot_number == 0:
                self._counter = shot_number

                ball_data = BallData()
                ball_data.speed = round(speed * 0.00223694, 2)
                ball_data.hla = round(hla, 2)
                ball_data.vla = round(vla, 2)
                ball_data.putt_type = PuttType.ONEPUTT
                ball_data.good_shot = True
                ball_data.club = self._current_club

                self.shot.emit(ball_data)

    def _heartbeat(self) -> None:
        pass
