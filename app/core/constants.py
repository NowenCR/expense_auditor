from enum import Enum

class Flag(str, Enum):
    OK = "OK"
    POSSIBLE_WARN = "POSSIBLE_WARN"
    DIRECT_WARN = "DIRECT_WARN"

FLAG_PRIORITY = {
    Flag.OK: 0,
    Flag.POSSIBLE_WARN: 1,
    Flag.DIRECT_WARN: 2,
}
