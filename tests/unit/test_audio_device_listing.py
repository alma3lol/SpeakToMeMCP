from __future__ import annotations

from types import SimpleNamespace

from speaktome_mcp.audio import AudioInputDevice, SoundDeviceAudioCapture


class FakeSoundDeviceModule:
    def __init__(self, devices: list[dict[str, object]], default_device: object) -> None:
        self._devices = devices
        self.default = SimpleNamespace(device=default_device)
        self.InputStream = object

    def query_devices(self) -> list[dict[str, object]]:
        return self._devices


def test_list_input_devices_filters_outputs_and_marks_default() -> None:
    sounddevice_module = FakeSoundDeviceModule(
        devices=[
            {
                "name": "Built-in Output",
                "max_input_channels": 0,
                "default_samplerate": 48000,
            },
            {
                "name": "USB Microphone",
                "max_input_channels": 1,
                "default_samplerate": 44100.4,
            },
            {
                "name": "Webcam Mic",
                "max_input_channels": 2,
                "default_samplerate": 48000,
            },
        ],
        default_device=(2, 0),
    )

    devices = SoundDeviceAudioCapture(sounddevice_module).list_input_devices()

    assert devices == [
        AudioInputDevice(
            device_id=1,
            name="USB Microphone",
            max_input_channels=1,
            default_sample_rate=44100,
            is_default=False,
        ),
        AudioInputDevice(
            device_id=2,
            name="Webcam Mic",
            max_input_channels=2,
            default_sample_rate=48000,
            is_default=True,
        ),
    ]


def test_list_input_devices_falls_back_to_first_input_when_default_missing() -> None:
    sounddevice_module = FakeSoundDeviceModule(
        devices=[
            {
                "name": "Desk Mic",
                "max_input_channels": 1,
                "default_samplerate": 16000,
            },
            {
                "name": "Headset Mic",
                "max_input_channels": 1,
                "default_samplerate": 32000,
            },
        ],
        default_device=(-1, 3),
    )

    devices = SoundDeviceAudioCapture(sounddevice_module).list_input_devices()

    assert devices[0].is_default is True
    assert devices[1].is_default is False
