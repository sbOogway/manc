"""Response shapes with no query behind them; every other route answers with a queries dataclass."""

from datetime import date

from pydantic import BaseModel


class AssetOut(BaseModel):
    symbol: str
    kind: str
    economies: list[str]
    tradingview: str | None  # EXCHANGE:TICKER for the embedded price chart


class ReportOut(BaseModel):
    symbol: str
    date: date
    formula: str
    report_md: str


class FormulasOut(BaseModel):
    default: str
    known: list[str]


class HealthOut(BaseModel):
    status: str
    last_run: date | None
