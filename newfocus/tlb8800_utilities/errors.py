"""TLB-8800 error codes and protocol exceptions (manual §5.5, Table 5)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class TLB8800ErrorCode(IntEnum):
    """Device-dependent and SCPI-style error codes."""

    NO_ERROR = 0

    # Command / query parsing errors
    DATA_UNEXPECTED = -104
    TOO_MANY_PARAMETERS = -108
    TOO_FEW_PARAMETERS = -109
    UNKNOWN_COMMAND = -110
    UNDEFINED_HEADER = -113
    ARGUMENT_TOO_LONG = -124
    UNKNOWN_DATA_TYPE = -140
    INVALID_CHARACTERS = -141
    CHARACTER_NOT_PERMITTED = -148
    STRING_ERROR = -151

    # Execution errors
    ILLEGAL_DEVICE_CONDITION = -200
    SETTINGS_CONFLICT = -221
    ARGUMENT_OUT_OF_RANGE = -222
    PRESET_ERROR = -310
    EEPROM_WRITE_ERROR = -320

    # Device-dependent errors
    LASER_OVER_POWER = 1
    LASER_OVER_CURRENT = 2
    TEMP_REGULATION_TIMEOUT = 20
    TEMP_REGULATION_DROPOUT = 21
    FPGA_INIT_FAILURE = 200
    POST_FAILURE = 201
    RTOS_INIT_FAILURE = 204
    POST_MODULE_TEMP_OUT_OF_LIMITS = 220
    POST_VCM_POWER_TEST_FAILURE = 222
    POST_VCM_OFFSET_CALIBRATION_FAILURE = 223
    POST_ENCODER_INIT_FAILURE = 224
    POST_VCM_POLARITY_FAULT = 225
    POST_VCM_TRAVEL_LIMITS_FAILURE = 226
    POST_TEC_DRIVER_INIT_FAILURE = 227
    POST_ANALOG_CIRCUIT_INIT_FAILURE = 228
    POST_OVER_POWER_TEST_FAILURE = 229
    POST_I2C_FAILURE = 230
    POST_FAN_TACH_OUT_OF_LIMITS = 231
    POST_VCM_NEG12V_OVERVOLTAGE = 232
    POST_VCM_NEG12V_DUTY_LIMIT = 233
    POST_VCMP_OFFSET = 234
    POST_VCMI_OFFSET = 235
    POST_VCM_BOOST_OUT_OF_RANGE = 236
    POST_HS_SINGLE_FAN = 237
    POST_VCM_ENCODER_MISALIGNMENT = 240
    POST_ENCODER_INDEX_RESET_FAILURE = 241
    POST_ENCODER_INDEX_SEARCH_FAILURE = 242
    POST_HS_ASSEMBLY_ON_STANDARD_ELECTRONICS = 245
    POST_HS_4096X_INTERPOLATION = 247
    POST_STANDARD_416X_INTERPOLATION = 248
    POST_TEC_DRIVE_POLARITY = 250
    POST_LOW_TEC_CURRENT_HEATING = 251
    POST_LOW_TEC_CURRENT_COOLING = 252
    POST_EXTERNAL_5V_DELTA_V = 253
    POST_VLASER_OUT_OF_LIMITS = 254
    POST_FPGA_OVERI_RESET_ERROR = 255
    POST_LASER_CURRENT_REGULATION = 256
    POST_LASER_DIODE_SHORT_CIRCUIT = 257
    POST_OVERI_UNEXPECTED_TRIP = 258
    POST_OVERI_NO_TRIP = 259
    VCM_TORQUE_BIAS_FIRST_MOVE_FAILURE = 260
    VCM_TORQUE_BIAS_FORWARD_MOVE_FAILURE = 261
    VCM_TORQUE_BIAS_REVERSE_MOVE_FAILURE = 262
    VCM_HOMING_FAILURE = 263
    POST_VCM_DRIVER_POSITIVE_EXCURSION = 264
    POST_VCM_DRIVER_NEGATIVE_EXCURSION = 265
    POST_VCM_DRIVER_12V_DELTA_V = 266
    POST_VCM_DRIVER_CURRENT_LOW = 267
    POST_VCM_DRIVER_NEG12V_DUTY_TIMEOUT = 268
    POST_VCM_DRIVER_NEG12V_OVERVOLTAGE = 269
    LASER_TUNING_INIT_FAILURE = 270
    LASER_SCANNING_INIT_FAILURE = 271
    LASER_POWER_INIT_FAILURE = 272
    LASER_CURRENT_INIT_FAILURE = 273
    SWEEP_MOTION_FAILURE = 300
    INTERNAL_MOTION_FAILURE = 301
    FLASH_MEMORY_FAILURE = 302
    LASER_TEMP_THERMAL_RUNAWAY = 305
    MOTOR_NOT_INITIALIZED = 306
    MOTOR_BUSY = 307
    CALIBRATION_DATA_SAVE_FAILURE = 312
    FPGA_UPDATE_FAILURE = 313
    VCM_ENCODER_MISALIGNMENT_RUNTIME = 314
    POWER_FAULT_EXTERNAL_5V_LOW = 320
    POWER_FAULT_EXTERNAL_12V_LOW = 321
    POWER_FAULT_INTERNAL_NEG12V_OVERVOLTAGE = 322
    POWER_FAULT_INTERNAL_NEG12V_DUTY_LIMIT = 323
    POWER_FAULT_INTERNAL_NEG12V_LOW = 324
    FAN1_TACH_OUT_OF_LIMITS = 325
    FAN2_TACH_OUT_OF_LIMITS = 326


ERROR_DESCRIPTIONS: dict[int, str] = {
    -104: "data received different than expected",
    -108: "more parameters were received than expected",
    -109: "fewer parameters were received than required",
    -110: "unknown command received",
    -113: "header syntactically correct, but undefined for device",
    -124: "argument length exceeds the limit",
    -140: "parser could not find any known data type",
    -141: "data contains invalid characters",
    -148: "character found in argument not permitted",
    -151: "string consists too many chars or missing 2nd double quote",
    -200: "command can not be executed due to an illegal device condition",
    -221: "command can not be executed as settings conflict",
    -222: "command can not be executed as the argument was outside the range",
    -310: "error occurred while performing system preset",
    -320: "fault detected while writing to EEPROM",
    0: "no error has occurred",
    1: "laser over power occurred",
    2: "laser over current occurred",
    20: "temperature regulation not achieved before time-out",
    21: "temperature regulation not achieved after dropping out of regulation",
    200: "FPGA initialization failure",
    201: "power on self test (POST) failure",
    204: "RTOS task initialization failure",
    220: "POST: module operating temperature outside of limits",
    222: "POST: voice coil motor (VCM) power test failure",
    223: "POST: VCM offset calibration failure",
    224: "POST: encoder initialization failure",
    225: "POST: VCM polarity fault",
    226: "POST: VCM travel limits not successfully found",
    227: "POST: thermo-electric cooler (TEC) driver initialization failure",
    228: "POST: analog circuit initialization failure",
    229: "POST: over power test failure",
    230: "POST: I2C communication failure",
    231: "POST: Fan tachometer outside limits",
    232: "POST: VCM Power, enabling -12V FPGA detects overvoltage",
    233: "POST: VCM Power, enabling -12V FPGA detects duty limit",
    234: "POST: VCM Power, VCMP greater than 50mV off ground",
    235: "POST: VCM Power, VCMI offset exceeds limits",
    236: "POST: VCM Power, VCM boost converter out-of-range",
    237: "POST: High Speed configuration with only one operating fan",
    240: "POST: VCM Encoder Misalignment Fault",
    241: "POST: encoder index reset failure",
    242: "POST: encoder index search failure",
    245: "POST: measured TEC current suggests High Speed Assembly on Standard electronics configuration",
    247: "POST: measured limits imply 4096x interpolation for High Speed Laser Assembly",
    248: "POST: measured limits imply 416x interpolation for Standard Laser Assembly",
    250: "POST: incorrect TEC drive polarity",
    251: "POST: low TEC current reading while heating",
    252: "POST: low TEC current reading while cooling",
    253: "POST: external +5V excess deltaV under load",
    254: "POST: +VLASER outside expected limits",
    255: "POST: FPGA OVERI protection reset error",
    256: "POST: laser current regulation exceeds limits",
    257: "POST: laser diode short circuit protect error",
    258: "POST: OVERI comparator tripped unexpectedly",
    259: "POST: OVERI comparator did not trip as expected",
    260: "VCM torque bias first move failure",
    261: "VCM torque bias forward move failure",
    262: "VCM torque bias reverse move failure",
    263: "VCM homing failure",
    264: "POST: VCM driver diagnostic failed during positive excursion",
    265: "POST: VCM driver diagnostic failed during negative excursion",
    266: "POST: VCM driver diagnostic, external +12V excess deltaV under load",
    267: "POST: VCM driver diagnostic, VCM current lower than expected for installed laser configuration",
    268: "POST: VCM driver diagnostic, -12V supply FPGA shutdown duty cycle limit timeout",
    269: "POST: VCM driver diagnostic, -12V supply FPGA shutdown over voltage detected",
    270: "laser tuning initialization failure",
    271: "laser scanning data structure initialization failure",
    272: "laser power initialization failure",
    273: "laser current initialization failure",
    300: "sweep motion failure",
    301: "internal motion failure",
    302: "flash memory erase or write failure",
    305: "laser temperature thermal runaway error",
    306: "move requested when motor controller is not initialized",
    307: "move requested when motor controller is already busy",
    312: "Calibration Data Save Failure",
    313: "FPGA Update Failure",
    314: "VCM Encoder Misalignment Run-Time Fault",
    320: "power fault: external +5V supply less than 20 percent low",
    321: "power fault: external +12V supply less than 20 percent low",
    322: "power fault: internal -12V supply shutdown due to output over-voltage",
    323: "power fault: internal -12V supply shutdown due to duty cycle limit",
    324: "power fault: internal -12V supply less than 20 percent low",
    325: "Fan1 tachometer reading outside expected limits",
    326: "Fan2 tachometer reading outside expected limits",
}


def error_description(code: int) -> str:
    return ERROR_DESCRIPTIONS.get(code, f"unknown error code {code}")


def parse_error_codes(raw: str) -> list[int]:
    """Parse ``err?`` buffer (comma- or semicolon-separated)."""
    if not raw.strip():
        return []
    return [int(part.strip()) for part in re.split(r"[,;]+", raw.strip()) if part.strip()]


def interpret_protocol_response(response: str) -> str:
    """Human-readable meaning of a Legacy set-command reply character."""
    labels = {
        "*": "Command accepted.",
        "&": (
            "Execution error: the command was not executed. "
            "Check err? codes, interlock (int?), and device state."
        ),
        "!": "Unknown command.",
        "#": "Illegal command argument.",
    }
    text = response.strip()
    return labels.get(text, f"Unexpected protocol response: {text!r}")


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a Legacy set command (never raises for &, !, #)."""

    command: str
    response: str
    ok: bool
    message: str
    error_codes: tuple[int, ...] = ()
    error_messages: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        if self.ok:
            return f"OK ({self.response!r}): {self.message}"
        lines = [f"FAILED ({self.response!r}): {self.message}"]
        for code, desc in zip(self.error_codes, self.error_messages):
            lines.append(f"  [{code}] {desc}")
        return "\n".join(lines)


class TLB8800Error(Exception):
    """Base exception for TLB-8800 driver errors."""


class TLB8800ProtocolError(TLB8800Error):
    """Legacy protocol response error (!, #, &)."""

    RESPONSE_CMD_ERR = "!"
    RESPONSE_ARG_ERR = "#"
    RESPONSE_EXE_ERR = "&"

    def __init__(self, response_char: str, command: str = "") -> None:
        self.response_char = response_char
        self.command = command
        labels = {
            self.RESPONSE_CMD_ERR: "unknown command",
            self.RESPONSE_ARG_ERR: "illegal command argument",
            self.RESPONSE_EXE_ERR: "execution error",
        }
        label = labels.get(response_char, "protocol error")
        message = f"TLB-8800 {label} ({response_char!r})"
        if command:
            message += f" for command: {command!r}"
        super().__init__(message)


class TLB8800ExecutionError(TLB8800Error):
    """Device error code from the error buffer."""

    def __init__(self, code: int, description: Optional[str] = None) -> None:
        self.code = code
        self.description = description or error_description(code)
        super().__init__(f"TLB-8800 error {code}: {self.description}")


class TLB8800ParseError(TLB8800Error):
    """Failed to parse a device response."""

    def __init__(self, raw_response: str, message: str) -> None:
        self.raw_response = raw_response
        self.message = message
        super().__init__(f"{message} (raw={raw_response!r})")
