from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtCore import Qt
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
