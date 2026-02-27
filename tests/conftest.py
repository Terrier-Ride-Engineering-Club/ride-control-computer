import os
import pytest

# Use gpiozero's mock pin factory so tests can run without real GPIO hardware.
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "mock")


@pytest.fixture(autouse=True)
def resetGpioPins():
    """Reset the gpiozero mock pin factory before each test to prevent GPIOPinInUse errors.
    No-op when gpiozero is not installed (e.g. CI without Pi GPIO support)."""
    try:
        from gpiozero import Device
        from gpiozero.pins.mock import MockFactory
        Device.pin_factory = MockFactory()
        yield
        Device.pin_factory.close()
    except ImportError:
        yield
