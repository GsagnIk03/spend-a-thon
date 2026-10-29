import datetime as dt
import re
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .constants import CREDIT_CARD, PAYMENT_METHODS, RECEIPT_TYPES
from .utils import is_month

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

Amount = Annotated[Decimal, Field(gt=0, le=Decimal("100000000"), decimal_places=2)]
NonNegAmount = Annotated[Decimal, Field(ge=0, le=Decimal("100000000"), decimal_places=2)]
CategoryId = Annotated[str, Field(min_length=1, max_length=40)]


def _strip(v: str | None) -> str:
    return (v or "").strip()


class _Payment(BaseModel):
    """payment_method + optional card_id (only meaningful for credit cards).

    Category ids are checked against the user's own list in the routers,
    because custom categories differ per user.
    """

    payment_method: str | None = None
    card_id: str | None = None

    @field_validator("payment_method")
    @classmethod
    def _payment(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if v not in PAYMENT_METHODS:
            raise ValueError("unknown payment method")
        return v

    @model_validator(mode="after")
    def _card(self):
        if self.payment_method != CREDIT_CARD:
            self.card_id = None
        elif self.card_id == "":
            self.card_id = None
        return self


# ---------- auth ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name is required")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("enter a valid email address")
        return v


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    id: str
    name: str
    email: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


# ---------- categories ----------
class CategoryIn(BaseModel):
    label: str = Field(min_length=1, max_length=30)
    emoji: str = Field(min_length=1, max_length=16)
    color: str | None = None

    @field_validator("label", "emoji")
    @classmethod
    def _s(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("required")
        return v

    @field_validator("color")
    @classmethod
    def _color(cls, v: str | None) -> str | None:
        if v and not COLOR_RE.match(v):
            raise ValueError("color must look like #RRGGBB")
        return v or None


# ---------- expenses ----------
class ExpenseIn(_Payment):
    amount: Amount
    date: dt.date
    category: CategoryId
    note: str = Field("", max_length=200)

    @field_validator("note")
    @classmethod
    def _note(cls, v: str) -> str:
        return v.strip()

    @field_validator("date")
    @classmethod
    def _date(cls, v: dt.date) -> dt.date:
        if v.year < 2000 or v > dt.date.today() + dt.timedelta(days=366):
            raise ValueError("date is out of range")
        return v


class ExpenseOut(BaseModel):
    id: str
    amount: float
    date: str
    category: str
    note: str
    payment_method: str | None
    card_id: str | None
    has_receipt: bool
    recurring_id: str | None
    loan_id: str | None
    created_at: str | None


class ReceiptUploadIn(BaseModel):
    content_type: str

    @field_validator("content_type")
    @classmethod
    def _ct(cls, v: str) -> str:
        if v not in RECEIPT_TYPES:
            raise ValueError("receipt must be a JPG, PNG, WEBP, HEIC image or a PDF")
        return v


class ReceiptAttachIn(BaseModel):
    key: str = Field(max_length=300)


# ---------- budgets ----------
class BudgetsIn(BaseModel):
    budgets: dict[CategoryId, Annotated[Decimal, Field(ge=0, le=Decimal("100000000"))] | None]


# ---------- recurring ----------
class RecurringIn(_Payment):
    amount: Amount
    category: CategoryId
    note: str = Field("", max_length=200)
    day_of_month: int = Field(ge=1, le=31)
    start_month: str
    end_month: str | None = None
    active: bool = True

    @field_validator("note")
    @classmethod
    def _note(cls, v: str) -> str:
        return v.strip()

    @field_validator("start_month", "end_month")
    @classmethod
    def _month(cls, v: str | None) -> str | None:
        if v in (None, ""):
            return None
        if not is_month(v):
            raise ValueError("month must look like YYYY-MM")
        return v

    @model_validator(mode="after")
    def _range(self):
        if self.start_month is None:
            raise ValueError("start_month is required")
        if self.end_month and self.end_month < self.start_month:
            raise ValueError("end month can't be before start month")
        return self


class RecurringOut(BaseModel):
    id: str
    amount: float
    category: str
    note: str
    payment_method: str | None
    card_id: str | None
    day_of_month: int
    start_month: str
    end_month: str | None
    active: bool
    last_generated_month: str | None
    next_due: str | None


# ---------- credit cards ----------
class CardIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    bank: str = Field("", max_length=40)
    last4: str = Field("", max_length=4)
    credit_limit: NonNegAmount
    available: Annotated[Decimal, Field(ge=Decimal("-100000000"), le=Decimal("100000000"), decimal_places=2)]
    statement_day: int | None = Field(None, ge=1, le=31)
    due_day: int | None = Field(None, ge=1, le=31)
    color: str | None = None

    @field_validator("name", "bank")
    @classmethod
    def _s(cls, v: str) -> str:
        return _strip(v)

    @field_validator("last4")
    @classmethod
    def _last4(cls, v: str) -> str:
        v = _strip(v)
        if v and not re.fullmatch(r"\d{4}", v):
            raise ValueError("last 4 digits must be 4 numbers")
        return v

    @field_validator("color")
    @classmethod
    def _color(cls, v: str | None) -> str | None:
        if v and not COLOR_RE.match(v):
            raise ValueError("color must look like #RRGGBB")
        return v or None


class CardPaymentIn(BaseModel):
    amount: Amount
    date: dt.date
    note: str = Field("", max_length=120)
    kind: Literal["payment", "refund"] = "payment"


class CardBalanceIn(BaseModel):
    available: Annotated[Decimal, Field(ge=Decimal("-100000000"), le=Decimal("100000000"), decimal_places=2)]


# ---------- loans & borrowings ----------
class LoanIn(_Payment):
    kind: Literal["loan", "borrowing"]
    lender: str = Field(min_length=1, max_length=60)
    taken_by: str = Field("", max_length=60)
    principal: Amount
    note: str = Field("", max_length=200)
    # EMI loans
    interest_rate: Annotated[Decimal, Field(ge=0, le=100, decimal_places=2)] | None = None
    total_interest: NonNegAmount | None = None
    installment: Amount | None = None
    emi_day: int | None = Field(None, ge=1, le=31)
    emi_count: int | None = Field(None, ge=1, le=600)
    first_emi_date: dt.date | None = None
    emi_adjustment: int = Field(0, ge=-600, le=600)  # missed (-) or extra (+) EMIs vs the schedule
    insurance: bool = False
    log_emis_as_expenses: bool = False
    # borrowings
    taken_on: dt.date | None = None

    @field_validator("lender", "taken_by", "note")
    @classmethod
    def _s(cls, v: str) -> str:
        return _strip(v)

    @model_validator(mode="after")
    def _shape(self):
        if self.kind == "loan":
            missing = [f for f in ("installment", "emi_count", "first_emi_date") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"EMI loans need {', '.join(missing)}")
            if self.emi_day is None:
                self.emi_day = self.first_emi_date.day
        else:
            for f in ("interest_rate", "total_interest", "installment", "emi_day", "emi_count",
                      "first_emi_date"):
                setattr(self, f, None)
            self.emi_adjustment = 0
            self.log_emis_as_expenses = False
            self.insurance = False
        return self


class RepaymentIn(BaseModel):
    amount: Amount
    date: dt.date
    note: str = Field("", max_length=120)
