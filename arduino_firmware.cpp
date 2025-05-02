// HPGL Laser Engraver Firmware for Arduino Uno
//version without limit switches

// Pin definitions
const int stepY = 3;     // Y-STEP (D3)
const int dirY = 6;      // Y-DIR  (D6)
const int stepX = 2;     // X-STEP (D2)
const int dirX = 5;      // X-DIR  (D5)
const int enPin = 8;     // ENABLE (D8)
const int laserPin = 11; // Laser PWM control

// Constants
#define HPGL_TO_STEPS 10.5788  // Conversion factor from HPGL units to motor steps
#define STEP_DELAY 1200         // Microseconds between steps (adjust for speed)
#define FORWARD_DIR 0          // Direction constant
#define BACKWARD_DIR 1         // Direction constant
#define MAX_STEPS_X 19050      // Maximum X travel in steps
#define MAX_STEPS_Y 19050      // Maximum Y travel in steps

// Variables
long currentX = 0;       // Current X position in steps
long currentY = 0;       // Current Y position in steps
bool laserState = false; // Laser on/off state
int laserPower = 0;      // Laser power (0-255)
String commandBuffer = ""; // Buffer for incoming serial data

void setup() {
  // Initialize pins
  pinMode(stepX, OUTPUT);
  pinMode(dirX, OUTPUT);
  pinMode(stepY, OUTPUT);
  pinMode(dirY, OUTPUT);
  pinMode(enPin, OUTPUT);
  pinMode(laserPin, OUTPUT);

  // Set initial states
  digitalWrite(enPin, LOW);  // Enable stepper drivers (LOW = enabled)
  digitalWrite(stepX, LOW);
  digitalWrite(stepY, LOW);
  analogWrite(laserPin, 0);  // Turn laser off

  // Initialize serial communication
  Serial.begin(115200);
  Serial.println("HPGL Laser Engraver Ready");
  Serial.println("INFO: System assumes current position is (0,0)");
}

void loop() {
  // Check for incoming commands
  if (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n') {
      // Process complete command when newline is received
      processCommand(commandBuffer);
      commandBuffer = "";  // Clear buffer for next command
    } else {
      // Add character to buffer
      commandBuffer += c;
    }
  }
}

void processCommand(String command) {
  // Command format: COMMAND:PARAM1,PARAM2,...
  int colonPos = command.indexOf(':');
  if (colonPos == -1) {
    Serial.println("ERR:Invalid command format");
    return;
  }

  String cmd = command.substring(0, colonPos);
  String params = command.substring(colonPos + 1);

  if (cmd == "PU") {
    // Pen Up - Laser Off
    laserState = false;
    analogWrite(laserPin, 0);
    Serial.println("ACK:PU");
  }
  else if (cmd == "PD") {
    // Pen Down - Laser On
    laserState = true;
    analogWrite(laserPin, laserPower);
    Serial.println("ACK:PD");
  }
  else if (cmd == "PA") {
    // Plot Absolute - Move to absolute position
    int commaPos = params.indexOf(',');
    if (commaPos == -1) {
      Serial.println("ERR:Invalid PA params");
      return;
    }

    int hpglX = params.substring(0, commaPos).toInt();
    int hpglY = params.substring(commaPos + 1).toInt();

    moveToolAbsolute(hpglX, hpglY);
    Serial.println("ACK:PA");
  }
  else if (cmd == "SP") {
    // Set Pen - Set laser power (0-255)
    laserPower = params.toInt();
    if (laserPower < 0) laserPower = 0;
    if (laserPower > 255) laserPower = 255;

    if (laserState) {
      analogWrite(laserPin, laserPower);
    }
    Serial.println("ACK:SP");
  }
  else if (cmd == "HOME") {
    // Set position as home without moving (since we have no limit switches)
    currentX = 0;
    currentY = 0;
    Serial.println("ACK:HOME");
    Serial.println("INFO:Current position set as (0,0)");
  }
  else if (cmd == "STATUS") {
    // Return current status
    Serial.print("STATUS:");
    Serial.print(currentX);
    Serial.print(",");
    Serial.print(currentY);
    Serial.print(",");
    Serial.print(laserState);
    Serial.print(",");
    Serial.println(laserPower);
  }
  else if (cmd == "RESET") {
    // Emergency stop - turn off laser and disable motors
    analogWrite(laserPin, 0);
    digitalWrite(enPin, HIGH);  // Disable motor drivers
    Serial.println("ACK:RESET");
    Serial.println("INFO:Emergency stop - motors disabled, laser off");
  }
  else if (cmd == "ENABLE") {
    // Enable motor drivers
    digitalWrite(enPin, LOW);
    Serial.println("ACK:ENABLE");
    Serial.println("INFO:Motors enabled");
  }
  else if (cmd == "SET_POS") {
    // Set current position
    int commaPos = params.indexOf(',');
    if (commaPos == -1) {
      Serial.println("ERR:Invalid SET_POS params");
      return;
    }

    currentX = params.substring(0, commaPos).toInt();
    currentY = params.substring(commaPos + 1).toInt();
    Serial.println("ACK:SET_POS");
    Serial.print("INFO:Position set to (");
    Serial.print(currentX);
    Serial.print(",");
    Serial.print(currentY);
    Serial.println(")");
  }
  else {
    Serial.println("ERR:Unknown command");
  }
}

void moveToolAbsolute(int hpglX, int hpglY) {
  // Convert HPGL coordinates to steps
  long targetStepsX = round(HPGL_TO_STEPS * hpglX);
  long targetStepsY = round(HPGL_TO_STEPS * hpglY);

  // Check machine limits
  if (targetStepsX < 0 || targetStepsX > MAX_STEPS_X ||
      targetStepsY < 0 || targetStepsY > MAX_STEPS_Y) {
    Serial.println("ERR:Target position out of bounds");
    return;
  }

  // Calculate steps to move
  long dx = targetStepsX - currentX;
  long dy = targetStepsY - currentY;

  // Set directions
  digitalWrite(dirX, dx >= 0 ? FORWARD_DIR : BACKWARD_DIR);
  digitalWrite(dirY, dy >= 0 ? FORWARD_DIR : BACKWARD_DIR);

  // Get absolute values for calculations
  long absDx = abs(dx);
  long absDy = abs(dy);

  // Bresenham's line algorithm for smooth diagonal movement
  if (absDx > absDy) {
    // X is the driving axis
    long err = absDx / 2;
    for (long i = 0; i < absDx; i++) {
      stepMotorX();
      err -= absDy;
      if (err < 0) {
        stepMotorY();
        err += absDx;
      }
      delayMicroseconds(STEP_DELAY);
    }
  } else {
    // Y is the driving axis
    long err = absDy / 2;
    for (long i = 0; i < absDy; i++) {
      stepMotorY();
      err -= absDx;
      if (err < 0) {
        stepMotorX();
        err += absDy;
      }
      delayMicroseconds(STEP_DELAY);
    }
  }

  // Update current position
  currentX = targetStepsX;
  currentY = targetStepsY;
}

void stepMotorX() {
  // Generate a single pulse on X stepper pin
  digitalWrite(stepX, HIGH);
  delayMicroseconds(10); // Ensure pulse is recognized by driver
  digitalWrite(stepX, LOW);
}

void stepMotorY() {
  // Generate a single pulse on Y stepper pin
  digitalWrite(stepY, HIGH);
  delayMicroseconds(10); // Ensure pulse is recognized by driver
  digitalWrite(stepY, LOW);
}