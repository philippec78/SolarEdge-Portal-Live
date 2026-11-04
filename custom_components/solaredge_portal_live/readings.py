"""Convert the portal's kW and direction to fresh Home Assistant values."""

from dataclasses import dataclass
from datetime import UTC, datetime
import math

MAX_SAMPLE_AGE = 120


@dataclass(frozen=True)
class Readings:
    """One timestamped sample from the portal."""

    timestamp: datetime | None
    grid: float | None = None
    production: float | None = None
    consumption: float | None = None

    @property
    def imported(self) -> float | None:
        return max(self.grid, 0) if self.grid is not None else None

    @property
    def exported(self) -> float | None:
        return max(-self.grid, 0) if self.grid is not None else None


def _watts(component: dict) -> float | None:
    power = component.get("currentPower")
    if type(power) not in (int, float) or not math.isfinite(power) or power < 0:
        return None
    watts = power * 1000
    return round(watts, 3) if math.isfinite(watts) else None


def parse_readings(data: dict, now: datetime | None = None) -> Readings:
    """Keep the source timestamp even when the power has become stale."""
    try:
        timestamp = datetime.fromisoformat(data["lastUpdateTime"])
    except (KeyError, TypeError, ValueError):
        return Readings(None)
    if timestamp.utcoffset() is None:
        return Readings(None)
    age = ((now or datetime.now(UTC)) - timestamp).total_seconds()
    if not (
        data.get("isRealTime") is True and data.get("isCommunicating") is True
        and -30 <= age <= MAX_SAMPLE_AGE
    ):
        return Readings(timestamp)

    def component(name: str) -> dict:
        value = data.get(name)
        return value if isinstance(value, dict) and value.get("isActive") is not False else {}

    grid = component("grid")
    power = _watts(grid)
    if power is not None and power != 0:
        match grid.get("status"):
            case "export":
                power = -power
            case "import":
                pass
            case _:
                power = None
    return Readings(timestamp, power, _watts(component("solarProduction")), _watts(component("consumption")))
