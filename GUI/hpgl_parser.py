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

