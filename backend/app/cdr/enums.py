"""CDR-specific enums stored as text with CHECK constraints."""
from enum import StrEnum


class ImportStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class RecordFormat(StrEnum):
    CSV = "csv"
    XLS = "xls"
    XLSX = "xlsx"


class MsisdnRule(StrEnum):
    NEPAL = "np-msisdn.v1"
    INDIA = "in-msisdn.v1"


class CallDirection(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class ServiceType(StrEnum):
    VOICE = "voice"
    SMS = "sms"
    DATA = "data"


class NetworkGeneration(StrEnum):
    G2 = "2G"
    G3 = "3G"
    G4 = "4G"
    G5 = "5G"


class CustodyEventType(StrEnum):
    RECEIVED = "received"
    HASHED = "hashed"
    STORED = "stored"
    PROCESSING_STARTED = "processing_started"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"
    INTEGRITY_VERIFIED = "integrity_verified"
    INTEGRITY_FAILED = "integrity_failed"
