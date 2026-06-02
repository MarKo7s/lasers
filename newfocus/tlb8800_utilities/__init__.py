"""TLB-8800 support modules (protocol, errors, commands, logging)."""

from newfocus.tlb8800_utilities.commands import TLBReadCommands, TLBSetCommands
from newfocus.tlb8800_utilities.errors import (
    CommandResult,
    TLB8800Error,
    TLB8800ErrorCode,
    TLB8800ExecutionError,
    TLB8800ParseError,
    TLB8800ProtocolError,
    error_description,
    interpret_protocol_response,
    parse_error_codes,
)
from newfocus.tlb8800_utilities.idn import parse_idn
from newfocus.tlb8800_utilities.logging_paths import (
    find_lab_root,
    instrument_log_path,
    laser_id_from_idn,
    log_id_from_idn,
    program_data_lab_root,
    sanitize_log_id,
)
from newfocus.tlb8800_utilities.protocol import (
    DEFAULT_BAUDRATE,
    DEFAULT_TIMEOUT,
    SerialTransport,
    parse_numeric_response,
)
from newfocus.tlb8800_utilities.session_log import LaserSessionLogger, parse_log_level
from newfocus.tlb8800_utilities.types import (
    FanSpeed,
    InterlockState,
    LaserIdentity,
    LaserSpecs,
    LoopMode,
    ModulationSource,
    OperationCompleteState,
    PowerUnit,
    ScanMode,
    TriggerPolarity,
    TuningDomain,
)

__all__ = [
    "CommandResult",
    "DEFAULT_BAUDRATE",
    "DEFAULT_TIMEOUT",
    "FanSpeed",
    "InterlockState",
    "LaserIdentity",
    "LaserSpecs",
    "LaserSessionLogger",
    "LoopMode",
    "ModulationSource",
    "OperationCompleteState",
    "PowerUnit",
    "ScanMode",
    "SerialTransport",
    "TLB8800Error",
    "TLB8800ErrorCode",
    "TLB8800ExecutionError",
    "TLB8800ParseError",
    "TLB8800ProtocolError",
    "TLBReadCommands",
    "TLBSetCommands",
    "TriggerPolarity",
    "TuningDomain",
    "error_description",
    "find_lab_root",
    "instrument_log_path",
    "interpret_protocol_response",
    "laser_id_from_idn",
    "log_id_from_idn",
    "parse_error_codes",
    "parse_idn",
    "parse_log_level",
    "parse_numeric_response",
    "program_data_lab_root",
    "sanitize_log_id",
]
