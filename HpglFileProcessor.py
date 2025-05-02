"""
HPGL File Processor - Standalone utility for processing HPGL files
"""

import sys
import os
import argparse
import re
import math


class HPGLProcessor:
    """
    Standalone utility for parsing and processing HPGL files
    """

    def __init__(self):
        self.commands = []
        self.min_x = float('inf')
        self.min_y = float('inf')
        self.max_x = float('-inf')
        self.max_y = float('-inf')

    def parse_file(self, filename):
        """Parse an HPGL file into commands"""
        print(f"Parsing HPGL file: {filename}")

        try:
            with open(filename, 'r') as f:
                content = f.read()

            # Remove any whitespace
            content = content.replace(' ', '').replace('\n', '').replace('\r', '')

            # Split by semicolons to get commands
            raw_commands = content.split(';')
            command_count = 0

            for cmd in raw_commands:
                if not cmd:
                    continue

                # Extract command type (first two characters)
                cmd_type = cmd[:2]
                command_count += 1

                if cmd_type == 'IN':
                    # Initialize
                    self.commands.append({'type': 'HOME'})
                    print("  Found: Initialize (IN)")
                elif cmd_type == 'PU':
                    # Pen Up (Laser Off)
                    self.commands.append({'type': 'PU'})
                    print("  Found: Pen Up (PU)")

                    # Check if coordinates follow
                    if len(cmd) > 2:
                        nums = list(map(int, cmd[2:].split(',')))
                        # consume pairs (x,y) in order
                        for i in range(0, len(nums) - 1, 2):
                            x, y = nums[i], nums[i + 1]
                            self.update_bounds(x, y)
                            self.commands.append({'type': 'PA', 'x': x, 'y': y})
                            print(f"  Found: Move to ({x}, {y})")

                elif cmd_type == 'PD':
                    # Pen Down (Laser On)
                    self.commands.append({'type': 'PD'})
                    print("  Found: Pen Down (PD)")

                    # Check if coordinates follow
                    if len(cmd) > 2:
                        nums = list(map(int, cmd[2:].split(',')))
                        # consume pairs (x,y) in order
                        for i in range(0, len(nums) - 1, 2):
                            x, y = nums[i], nums[i + 1]
                            self.update_bounds(x, y)
                            self.commands.append({'type': 'PA', 'x': x, 'y': y})
                            print(f"  Found: Move to ({x}, {y})")

                elif cmd_type == 'PA':
                    # Plot Absolute — may have multiple x,y pairs in one statement
                    nums = [int(n) for n in cmd[2:].split(',') if n]
                    for i in range(0, len(nums) - 1, 2):
                        x, y = nums[i], nums[i + 1]
                        self.update_bounds(x, y)
                        self.commands.append({'type': 'PA', 'x': x, 'y': y})
                        print(f"  Found: Plot Absolute to ({x}, {y})")

                elif cmd_type == 'SP':
                    # Select Pen (Laser Power)
                    if len(cmd) > 2:
                        pen = int(cmd[2:])
                        # Scale pen from HPGL (0-8) to PWM (0-255)
                        power = min(255, int((pen / 8) * 255))
                        self.commands.append({'type': 'SP', 'power': power})
                        print(f"  Found: Select Pen {pen} (Power: {power})")
                elif cmd_type == 'CI':
                    # Circle
                    radius = int(cmd[2:])
                    print(f"  Found: Circle with radius {radius}")
                    # Convert circle to line segments
                    self.convert_circle_to_lines(radius)

            print(f"Parsed {command_count} HPGL commands")
            print(f"Drawing bounds: ({self.min_x}, {self.min_y}) to ({self.max_x}, {self.max_y})")

            return True
        except Exception as e:
            print(f"Error parsing HPGL file: {e}")
            return False

    def update_bounds(self, x, y):
        """Update the bounds of the drawing"""
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)

    def convert_circle_to_lines(self, radius, segments=36):
        """Convert a circle to line segments"""
        # Get the last point as the center
        if self.commands and self.commands[-1]['type'] == 'PA':
            center_x = self.commands[-1]['x']
            center_y = self.commands[-1]['y']

            # Remove the center point
            self.commands.pop()

            # Add pen up to move to first point
            self.commands.append({'type': 'PU'})

            # Calculate first point
            first_x = center_x + radius
            first_y = center_y

            # Move to first point
            self.commands.append({'type': 'PA', 'x': first_x, 'y': first_y})
            self.update_bounds(first_x, first_y)

            # Put pen down to draw
            self.commands.append({'type': 'PD'})

            # Create points around the circle
            for i in range(1, segments + 1):
                angle = 2 * math.pi * i / segments  # convert to radian
                x = center_x + int(radius * math.cos(angle))
                y = center_y + int(radius * math.sin(angle))

                self.commands.append({'type': 'PA', 'x': x, 'y': y})
                self.update_bounds(x, y)

            # Add pen up at the end
            self.commands.append({'type': 'PU'})

    def scale_commands(self, scale_factor):
        """Scale all coordinates by a factor"""
        print(f"Scaling by factor {scale_factor}")

        scaled_commands = []

        for cmd in self.commands:
            if cmd['type'] == 'PA':
                scaled_cmd = cmd.copy()
                scaled_cmd['x'] = int(cmd['x'] * scale_factor)
                scaled_cmd['y'] = int(cmd['y'] * scale_factor)
                scaled_commands.append(scaled_cmd)
            else:
                scaled_commands.append(cmd)

        # Update bounds
        self.min_x = self.min_x * scale_factor
        self.min_y = self.min_y * scale_factor
        self.max_x = self.max_x * scale_factor
        self.max_y = self.max_y * scale_factor

        self.commands = scaled_commands
        print(f"New bounds: ({self.min_x}, {self.min_y}) to ({self.max_x}, {self.max_y})")

    def center_commands(self, width, height):
        """Center the drawing in the specified dimensions"""
        print(f"Centering drawing in {width}x{height} area")

        if self.min_x == float('inf'):
            print("No valid commands to center")
            return

        # Calculate offsets
        drawing_width = self.max_x - self.min_x
        drawing_height = self.max_y - self.min_y

        offset_x = int((width - drawing_width) / 2 - self.min_x)
        offset_y = int((height - drawing_height) / 2 - self.min_y)

        print(f"Applying offsets: X={offset_x}, Y={offset_y}")

        # Apply offsets
        centered_commands = []
        for cmd in self.commands:
            if cmd['type'] == 'PA':
                centered_cmd = cmd.copy()
                centered_cmd['x'] = cmd['x'] + offset_x
                centered_cmd['y'] = cmd['y'] + offset_y
                centered_commands.append(centered_cmd)
            else:
                centered_commands.append(cmd)

        # Update bounds
        self.min_x += offset_x
        self.min_y += offset_y
        self.max_x += offset_x
        self.max_y += offset_y

        self.commands = centered_commands
        print(f"New bounds: ({self.min_x}, {self.min_y}) to ({self.max_x}, {self.max_y})")

    def save_to_file(self, filename):
        """Save processed commands to an HPGL file"""
        print(f"Saving to file: {filename}")

        try:
            with open(filename, 'w') as f:
                pen_down = False
                for cmd in self.commands:
                    if cmd['type'] == 'HOME':
                        f.write("IN;")
                    elif cmd['type'] == 'PU':
                        f.write("PU;")
                        pen_down = False
                    elif cmd['type'] == 'PD':
                        f.write("PD;")
                        pen_down = True
                    elif cmd['type'] == 'PA':
                        if pen_down:
                            f.write(f"PD{cmd['x']},{cmd['y']};")
                        else:
                            f.write(f"PU{cmd['x']},{cmd['y']};")
                    elif cmd['type'] == 'SP':
                        # Convert back to HPGL pen format (0-8)
                        pen = max(0, min(8, int((cmd['power'] / 255) * 8)))
                        f.write(f"SP{pen};")

            print(f"File saved successfully with {len(self.commands)} commands")
            return True
        except Exception as e:
            print(f"Error saving file: {e}")
            return False

    def export_to_arduino_commands(self, filename):
        """Export to a plain text file with Arduino commands"""
        print(f"Exporting to Arduino command file: {filename}")

        try:
            with open(filename, 'w') as f:
                f.write("# Arduino HPGL Commands\n")
                f.write("# Format: COMMAND:PARAMS\n")
                f.write("# Use with Serial connection\n\n")

                for cmd in self.commands:
                    if cmd['type'] == 'HOME':
                        f.write("HOME:\n")
                    elif cmd['type'] == 'PU':
                        f.write("PU:\n")
                    elif cmd['type'] == 'PD':
                        f.write("PD:\n")
                    elif cmd['type'] == 'PA':
                        f.write(f"PA:{cmd['x']},{cmd['y']}\n")
                    elif cmd['type'] == 'SP':
                        f.write(f"SP:{cmd['power']}\n")

            print(f"Arduino command file saved successfully")
            return True
        except Exception as e:
            print(f"Error saving Arduino command file: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description='Process HPGL files for laser engraving')
    parser.add_argument('input', help='Input HPGL file')
    parser.add_argument('-o', '--output', help='Output HPGL file')
    parser.add_argument('-a', '--arduino', help='Export as Arduino commands')
    parser.add_argument('-s', '--scale', type=float, help='Scale factor')
    parser.add_argument('-c', '--center', action='store_true', help='Center drawing')
    parser.add_argument('-w', '--width', type=int, default=1800, help='Work area width')
    parser.add_argument('-t', '--height', type=int, default=1800, help='Work area height')

    args = parser.parse_args()

    processor = HPGLProcessor()

    # Parse input file
    if not processor.parse_file(args.input):
        sys.exit(1)

    # Apply transformations
    if args.scale:
        processor.scale_commands(args.scale)

    if args.center:
        processor.center_commands(args.width, args.height)

    # Save output
    if args.output:
        processor.save_to_file(args.output)

    # Export Arduino commands
    if args.arduino:
        processor.export_to_arduino_commands(args.arduino)


if __name__ == "__main__":
    main()