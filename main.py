import sys
import os
import serial
import serial.tools.list_ports
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFileDialog, QComboBox, QSlider, QMessageBox,
                             QTextEdit, QGroupBox, QGridLayout, QSpinBox, QProgressBar, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QPixmap, QFont


class HPGLParser:
    """Class to parse HPGL files and convert to commands for Arduino"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.commands = []
        self.min_x = float('inf')
        self.min_y = float('inf')
        self.max_x = float('-inf')
        self.max_y = float('-inf')

    def parse_file(self, filename):
        """Parse an HPGL file and convert to commands"""
        self.reset()

        try:
            with open(filename, 'r') as f:
                content = f.read()

            # Remove any whitespace
            content = content.replace(' ', '').replace('\n', '').replace('\r', '')

            # Split by semicolons to get commands
            raw_commands = content.split(';')

            for cmd in raw_commands:
                if not cmd:
                    continue

                # Extract command type (first two characters)
                cmd_type = cmd[:2]

                if cmd_type == 'IN':
                    # Initialize
                    self.commands.append({'type': 'HOME'})
                elif cmd_type == 'PU':
                    # Pen Up (Laser Off)
                    self.commands.append({'type': 'PU'})

                    # Check if coordinates follow
                    if len(cmd) > 2:
                        coords = cmd[2:].split(',')
                        if len(coords) >= 2:
                            x, y = int(coords[0]), int(coords[1])
                            self.update_bounds(x, y)
                            self.commands.append({'type': 'PA', 'x': x, 'y': y})

                elif cmd_type == 'PD':
                    # Pen Down (Laser On)
                    self.commands.append({'type': 'PD'})

                    # Check if coordinates follow
                    if len(cmd) > 2:
                        coords = cmd[2:].split(',')
                        if len(coords) >= 2:
                            x, y = int(coords[0]), int(coords[1])
                            self.update_bounds(x, y)
                            self.commands.append({'type': 'PA', 'x': x, 'y': y})

                elif cmd_type == 'PA':
                    # Plot Absolute
                    coords = cmd[2:].split(',')
                    if len(coords) >= 2:
                        x, y = int(coords[0]), int(coords[1])
                        self.update_bounds(x, y)
                        self.commands.append({'type': 'PA', 'x': x, 'y': y})

                elif cmd_type == 'SP':
                    # Select Pen (Laser Power)
                    if len(cmd) > 2:
                        pen = int(cmd[2:])
                        # Scale pen from HPGL (0-8) to PWM (0-255)
                        power = min(255, int((pen / 8) * 255))
                        self.commands.append({'type': 'SP', 'power': power})
            return True
        except Exception as e:
            print(f"Error parsing HPGL file: {e}")
            return False

    def update_bounds(self, x, y):
        """Update the min/max bounds of the drawing"""
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)

    def get_bounds(self):
        """Get the bounds of the drawing"""
        if self.min_x == float('inf'):
            return (0, 0, 0, 0)  # No valid commands
        return (self.min_x, self.min_y, self.max_x, self.max_y)

    def get_commands(self):
        """Get the parsed commands"""
        return self.commands


class JobThread(QThread):
    """Thread to run the engraving job"""
    progress_update = pyqtSignal(int)
    status_update = pyqtSignal(str)
    job_finished = pyqtSignal()

    def __init__(self, arduino, commands):
        super().__init__()
        self.arduino = arduino
        self.commands = commands
        self.is_running = False
        self.is_paused = False

    def run(self):
        """Run the engraving job"""
        self.is_running = True
        self.is_paused = False
        total_commands = len(self.commands)

        try:
            for i, cmd in enumerate(self.commands):
                # Check if job is paused
                while self.is_paused and self.is_running:
                    time.sleep(0.1)

                # Check if job was canceled
                if not self.is_running:
                    break

                # Send command to Arduino
                cmd_type = cmd['type']
                if cmd_type == 'HOME':
                    self.arduino.send_command('HOME:')
                    self.status_update.emit("Homing machine...")
                elif cmd_type == 'PU':
                    self.arduino.send_command('PU:')
                    self.status_update.emit("Laser OFF")
                elif cmd_type == 'PD':
                    self.arduino.send_command('PD:')
                    self.status_update.emit("Laser ON")
                elif cmd_type == 'PA':
                    x, y = cmd['x'], cmd['y']
                    self.arduino.send_command(f'PA:{x},{y}')
                    self.status_update.emit(f"Moving to ({x}, {y})")
                elif cmd_type == 'SP':
                    power = cmd['power']
                    self.arduino.send_command(f'SP:{power}')
                    self.status_update.emit(f"Setting laser power to {power}")

                # Wait for Arduino to process command
                response = self.arduino.wait_for_response()
                if response and response.startswith("ERR"):
                    self.status_update.emit(f"Error: {response}")

                # Update progress
                progress = int((i + 1) / total_commands * 100)
                self.progress_update.emit(progress)

            # Turn off laser at end of job
            self.arduino.send_command('PU:')
            self.status_update.emit("Job completed")
        except Exception as e:
            self.status_update.emit(f"Error: {str(e)}")
        finally:
            self.is_running = False
            self.job_finished.emit()

    def pause(self):
        """Pause the job"""
        self.is_paused = True

    def resume(self):
        """Resume the job"""
        self.is_paused = False

    def stop(self):
        """Stop the job"""
        self.is_running = False


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


class HPGLPreview(QWidget):
    """Widget to preview HPGL commands"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.commands = []
        self.bounds = (0, 0, 0, 0)
        self.setMinimumSize(400, 400)

    def set_commands(self, commands, bounds):
        """Set the commands to preview"""
        self.commands = commands
        self.bounds = bounds
        self.update()

    def paintEvent(self, event):
        """Paint the HPGL preview"""
        if not self.commands:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Set background
        painter.fillRect(self.rect(), QColor(240, 240, 240))

        # Get drawing bounds
        min_x, min_y, max_x, max_y = self.bounds

        # Safety check
        if min_x == max_x or min_y == max_y:
            return

        # Calculate scaling to fit widget
        width_margin = self.width() * 0.1
        height_margin = self.height() * 0.1

        available_width = self.width() - 2 * width_margin
        available_height = self.height() - 2 * height_margin

        scale_x = available_width / (max_x - min_x)
        scale_y = available_height / (max_y - min_y)

        # Use smaller scale to maintain aspect ratio
        scale = min(scale_x, scale_y)

        # Offset to center the drawing
        offset_x = width_margin + (available_width - scale * (max_x - min_x)) / 2
        offset_y = height_margin + (available_height - scale * (max_y - min_y)) / 2

        # Transform coordinates
        def transform_x(x):
            return offset_x + scale * (x - min_x)

        def transform_y(y):
            # Invert Y axis because screen coordinates go down
            return self.height() - (offset_y + scale * (y - min_y))

        # Draw commands
        pen_down = False
        current_x, current_y = 0, 0
        laser_power = 0

        for cmd in self.commands:
            cmd_type = cmd['type']

            if cmd_type == 'PU':
                pen_down = False
            elif cmd_type == 'PD':
                pen_down = True
            elif cmd_type == 'PA':
                new_x, new_y = cmd['x'], cmd['y']

                if pen_down:
                    # Draw line with intensity based on laser power
                    intensity = min(255, max(0, laser_power))
                    color = QColor(255 - intensity, 0, 0)  # Darker red for higher power
                    pen = QPen(color, 2)
                    painter.setPen(pen)

                    # Draw line
                    painter.drawLine(
                        int(transform_x(current_x)), int(transform_y(current_y)),
                        int(transform_x(new_x)), int(transform_y(new_y))
                    )
                else:
                    # Draw movement path as dashed line
                    pen = QPen(QColor(0, 0, 255, 128), 1, Qt.PenStyle.DashLine)
                    painter.setPen(pen)

                    # Draw line
                    painter.drawLine(
                        int(transform_x(current_x)), int(transform_y(current_y)),
                        int(transform_x(new_x)), int(transform_y(new_y))
                    )

                # Update current position
                current_x, current_y = new_x, new_y

            elif cmd_type == 'SP':
                laser_power = cmd['power']


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Initialize components
        self.arduino = ArduinoController()
        self.hpgl_parser = HPGLParser()
        self.job_thread = None

        # Set up UI
        self.setWindowTitle("HPGL Laser Engraver Control")
        self.setMinimumSize(800, 600)

        # Create main widget and layout
        main_widget = QWidget()
        main_layout = QHBoxLayout()

        # Left panel for controls
        left_panel = QWidget()
        left_layout = QVBoxLayout()

        # Connection group
        connection_group = QGroupBox("Connection")
        connection_layout = QGridLayout()

        self.port_combo = QComboBox()
        self.refresh_ports_button = QPushButton("Refresh")
        self.connect_button = QPushButton("Connect")

        connection_layout.addWidget(QLabel("Port:"), 0, 0)
        connection_layout.addWidget(self.port_combo, 0, 1)
        connection_layout.addWidget(self.refresh_ports_button, 0, 2)
        connection_layout.addWidget(self.connect_button, 1, 0, 1, 3)

        connection_group.setLayout(connection_layout)

        # File group
        file_group = QGroupBox("HPGL File")
        file_layout = QGridLayout()

        self.file_path_label = QLabel("No file selected")
        self.file_path_label.setWordWrap(True)
        self.open_file_button = QPushButton("Open File")

        file_layout.addWidget(self.file_path_label, 0, 0, 1, 2)
        file_layout.addWidget(self.open_file_button, 1, 0, 1, 2)

        file_group.setLayout(file_layout)

        # Laser control group
        laser_group = QGroupBox("Laser Control")
        laser_layout = QGridLayout()

        self.laser_power_slider = QSlider(Qt.Orientation.Horizontal)
        self.laser_power_slider.setRange(0, 255)
        self.laser_power_slider.setValue(0)

        self.laser_power_value = QLabel("0")
        self.laser_test_button = QPushButton("Test Fire (1s)")

        laser_layout.addWidget(QLabel("Power:"), 0, 0)
        laser_layout.addWidget(self.laser_power_slider, 0, 1)
        laser_layout.addWidget(self.laser_power_value, 0, 2)
        laser_layout.addWidget(self.laser_test_button, 1, 0, 1, 3)

        laser_group.setLayout(laser_layout)

        # Job control group
        job_group = QGroupBox("Job Control")
        job_layout = QGridLayout()

        self.start_button = QPushButton("Start Job")
        self.start_button.setEnabled(False)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        job_layout.addWidget(self.start_button, 0, 0)
        job_layout.addWidget(self.pause_button, 0, 1)
        job_layout.addWidget(self.stop_button, 0, 2)
        job_layout.addWidget(self.progress_bar, 1, 0, 1, 3)
        job_layout.addWidget(self.status_label, 2, 0, 1, 3)

        job_group.setLayout(job_layout)

        # Add groups to left panel
        left_layout.addWidget(connection_group)
        left_layout.addWidget(file_group)
        left_layout.addWidget(laser_group)
        left_layout.addWidget(job_group)
        left_layout.addStretch()

        left_panel.setLayout(left_layout)
        left_panel.setMaximumWidth(300)

        # Right panel for preview
        right_panel = QWidget()
        right_layout = QVBoxLayout()

        preview_group = QGroupBox("HPGL Preview")
        preview_layout = QVBoxLayout()

        self.preview_widget = HPGLPreview()

        preview_layout.addWidget(self.preview_widget)
        preview_group.setLayout(preview_layout)

        right_layout.addWidget(preview_group)
        right_panel.setLayout(right_layout)

        # Add panels to main layout
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Connect signals
        self.refresh_ports_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.toggle_connection)
        self.open_file_button.clicked.connect(self.open_file)
        self.laser_power_slider.valueChanged.connect(self.update_laser_power)
        self.laser_test_button.clicked.connect(self.test_laser)
        self.start_button.clicked.connect(self.start_job)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop_job)

        # Initialize UI
        self.refresh_ports()

    def refresh_ports(self):
        """Refresh list of available serial ports"""
        print("[GUI] Refreshing serial ports…")
        self.port_combo.clear()
        ports = self.arduino.get_available_ports()
        print(f"[GUI]  → found ports: {ports}")
        self.port_combo.addItems(ports)

    def toggle_connection(self):
        """Connect or disconnect from Arduino"""
        if self.arduino.is_connected():
            print("[GUI] Disconnecting from Arduino")
            self.arduino.disconnect()
            print("[GUI]  → Disconnected")
            self.connect_button.setText("Connect")
            self.status_label.setText("Disconnected")
        else:
            # Connect
            port = self.port_combo.currentText()
            print(f"[GUI] Connecting to Arduino on port {port}")
            if not port:
                print("[GUI]  → No port selected!")
                QMessageBox.warning(self, "Error", "No port selected")
                return

            success = self.arduino.connect(port)
            print(f"[GUI]  → connect() returned {success}")
            if success:
                self.connect_button.setText("Disconnect")
                self.status_label.setText("Connected")
                self.start_button.setEnabled(self.file_path_label.text() != "No file selected")
            else:
                print(f"[GUI]  → Failed to connect to {port}")
                QMessageBox.warning(self, "Error", f"Failed to connect to {port}")

    def open_file(self):
        print("[GUI] Opening HPGL file…")
        path, _ = QFileDialog.getOpenFileName(self, "Open HPGL File", "", "HPGL Files (*.hpgl *.plt);;All Files (*.*)")
        print(f"[GUI]  → user selected: {path}")
        if not path:
            print("[GUI]  → no file chosen, aborting")
            return

        ok = self.hpgl_parser.parse_file(path)
        print(f"[GUI]  → parse_file returned {ok}")
        if ok:
            commands = self.hpgl_parser.get_commands()
            bounds = self.hpgl_parser.get_bounds()
            print(f"[GUI]  → parsed {len(commands)} commands, bounds = {bounds}")
            self.preview_widget.set_commands(commands, bounds)
            self.file_path_label.setText(os.path.basename(path))
            self.start_button.setEnabled(self.arduino.is_connected())
        else:
            print("[GUI]  → parse failed")
            QMessageBox.warning(self, "Error", "Failed to parse HPGL file")

    def update_laser_power(self):
        val = self.laser_power_slider.value()
        print(f"[GUI] Laser power slider changed → {val}")
        self.laser_power_value.setText(str(val))

    def test_laser(self):
        print("[GUI] Test Laser pressed")
        try:
            power = self.laser_power_slider.value()
            print(f"[GUI]  → sending SP:{power}")
            self.arduino.send_command(f"SP:{power}")
            print("[GUI]  ← ack:", self.arduino.wait_for_response())

            print("[GUI]  → sending PD:")
            self.arduino.send_command("PD:")
            print("[GUI]  ← ack:", self.arduino.wait_for_response())

            time.sleep(1)
            print("[GUI]  → sending PU:")
            self.arduino.send_command("PU:")
            print("[GUI]  ← ack:", self.arduino.wait_for_response())
        except Exception as e:
            print("[GUI]  → Test Laser error:", e)

    def start_job(self):
        """Start the engraving job"""
        if not self.arduino.is_connected():
            QMessageBox.warning(self, "Error", "Not connected to Arduino")
            return

        print("[GUI] Start Job pressed")
        commands = self.hpgl_parser.get_commands()
        print(f"[GUI]  → {len(commands)} commands to execute")
        if not commands:
            QMessageBox.warning(self, "Error", "No valid commands to execute")
            return

        # Set initial laser power
        power = self.laser_power_slider.value()
        self.arduino.send_command(f"SP:{power}")
        self.arduino.wait_for_response()

        # Create and start job thread
        self.job_thread = JobThread(self.arduino, commands)
        self.job_thread.progress_update.connect(self.update_progress)
        self.job_thread.status_update.connect(self.update_status)
        self.job_thread.job_finished.connect(self.job_finished)
        self.job_thread.start()

        # Update UI
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.pause_button.setText("Pause")
        self.stop_button.setEnabled(True)
        self.open_file_button.setEnabled(False)

    def toggle_pause(self):
        """Pause or resume the job"""
        if not self.job_thread:
            return

        if self.job_thread.is_paused:
            # Resume
            print("[GUI] Resuming job")
            self.job_thread.resume()
            self.pause_button.setText("Pause")
            self.status_label.setText("Job resumed")
        else:
            # Pause
            print("[GUI] Pausing job")
            self.job_thread.pause()
            self.pause_button.setText("Resume")
            self.status_label.setText("Job paused")

    def stop_job(self):
        """Stop the engraving job"""
        print("[GUI] Stop Job pressed")
        if not self.job_thread:
            return

        self.job_thread.stop()
        self.status_label.setText("Job stopped")

    def update_progress(self, progress):
        """Update progress bar"""
        print(f"[GUI] Job progress: {progress}%")
        self.progress_bar.setValue(progress)

    def update_status(self, status):
        """Update status label"""
        print(f"[GUI] Job status: {status}")
        self.status_label.setText(status)

    def job_finished(self):
        """Called when job is finished"""
        print("[GUI] Job finished")
        # Reset UI
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.open_file_button.setEnabled(True)
        self.progress_bar.setValue(0)

        # Make sure laser is off
        if self.arduino.is_connected():
            try:
                self.arduino.send_command("PU")
                self.arduino.wait_for_response()
                self.arduino.send_command(f'PA:0,0')
                self.arduino.wait_for_response()

            except:
                pass

    def closeEvent(self, event):
        """Handle window close event"""
        # Stop job if running
        if self.job_thread and self.job_thread.is_running:
            self.job_thread.stop()
            self.job_thread.wait(1000)

        # Turn off laser and disconnect
        if self.arduino.is_connected():
            try:
                self.arduino.send_command("PU")
                self.arduino.wait_for_response()
                self.arduino.disconnect()
            except:
                pass

        event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()