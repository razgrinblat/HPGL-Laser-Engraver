import time, serial, serial.tools.list_ports
class ArduinoController:
    """Class to manage communication with Arduino"""

    def __init__(self):
        self.serial = None
        self.connected = False

    def get_available_ports(self):
        """Get list of available serial ports"""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def connect(self, port, baud=115200, timeout=2):
        """Connect to Arduino"""
        try:
            self.serial = serial.Serial(port, baud, timeout=timeout)
            time.sleep(2)  # Wait for Arduino to reset
            self.serial.reset_input_buffer()
            self.connected = True
            return True
        except Exception as e:
            print(f"Error connecting to Arduino: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from Arduino"""
        if self.serial and self.serial.is_open:
            self.serial.close()
        self.connected = False

    def is_connected(self):
        """Check if connected to Arduino"""
        return self.connected and self.serial and self.serial.is_open

    def send_command(self, command):
        """Send command to Arduino"""
        if not self.is_connected():
            raise Exception("Not connected to Arduino")

        # Add newline to command
        if not command.endswith('\n'):
            command += '\n'

        self.serial.write(command.encode())
        self.serial.flush()

    def wait_for_response(self, timeout=10):
        """Wait for response from Arduino"""
        if not self.is_connected():
            raise Exception("Not connected to Arduino")

        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if self.serial.in_waiting:
                return self.serial.readline().decode().strip()
            time.sleep(0.1)

        return None