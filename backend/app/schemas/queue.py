"""Kolejka, limity dzienne, kalendarz, trend transit time i prognoza obłożenia."""
import datetime

from pydantic import BaseModel, Field

from .base import ORMModel
from .containers import ContainerOut

# --- queue / limits / calendar ---

class QueueDay(BaseModel):
    day: datetime.date
    is_free_day: bool
    limit: int | None
    used: int
    over_limit: bool
    containers: list[ContainerOut]


class DailyLimitIn(BaseModel):
    warehouse_id: int
    day: datetime.date
    limit: int = Field(ge=0)


class DailyLimitOut(ORMModel):
    id: int
    warehouse_id: int
    day: datetime.date
    limit: int


class CalendarDayIn(BaseModel):
    warehouse_id: int
    day: datetime.date
    is_working: bool
    note: str = ""


class CalendarDayOut(ORMModel):
    id: int
    warehouse_id: int
    day: datetime.date
    is_working: bool
    note: str


class MonthlyStat(BaseModel):
    year: int
    month: int
    company_id: int
    company_name: str
    count: int


# --- #56 trend transit time (ETD→ATD) ---

class TransitTrendPoint(BaseModel):
    month: str  # "YYYY-MM"
    avg_days: float
    count: int


class TransitTrendPort(BaseModel):
    port: str
    points: list[TransitTrendPoint]


class TransitTrendOut(BaseModel):
    overall: list[TransitTrendPoint]
    by_port: list[TransitTrendPort]


# --- #58 prognoza obłożenia (najbliższe 4 tygodnie) ---

class OccupancyWeek(BaseModel):
    week_start: datetime.date
    week_end: datetime.date
    containers: int
    pallets: int


class OccupancyForecastOut(BaseModel):
    weeks: list[OccupancyWeek]
