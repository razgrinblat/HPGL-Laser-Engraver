import time
from PyQt6.QtCore import QThread,pyqtSignal
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