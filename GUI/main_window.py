import os
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QComboBox, QSlider, QMessageBox, QGroupBox,
    QGridLayout, QProgressBar, QHBoxLayout
)
from GUI.arduino_controller import ArduinoController
from GUI.hpgl_parser import HPGLParser
from GUI.hpgl_preview import HPGLPreview
from GUI.job_thread import JobThread


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
            self.arduino.send_command("PU")
            self.arduino.wait_for_response()
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
