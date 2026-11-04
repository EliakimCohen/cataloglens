"""Normalization rules. Money is stored as integer cents, never binary floats."""

from dataclasses import asdict, dataclass
from decimal import Decimal
import re
import unicodedata

CATEGORIES = ("headphones", "laptops", "shoes", "speakers", "other")
RULE_VERSION = "keywords-v1"
RULES = (
    ("headphones", r"\b(headphones?|earbuds?|earphones?|headsets?)\b"),
    ("laptops", r"\b(laptops?|notebooks?|chromebooks?)\b"),
    ("shoes", r"\b(shoes?|sneakers?|trainers?|boots?)\b"),
    ("speakers", r"\b(speakers?|soundbars?)\b"),
)


class ValidationError(ValueError):
    pass


def text(value, field, maximum, *, required=True):
    if not isinstance(value, str):
        raise ValidationError(f"{field}: expected text")
    value = " ".join(unicodedata.normalize("NFKC", value).split())
    if required and not value:
        raise ValidationError(f"{field}: required")
    if len(value) > maximum:
        raise ValidationError(f"{field}: exceeds {maximum} characters")
    return value


def price_cents(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValidationError("price: use a decimal string or integer")
    value = str(value).strip()
    if value.startswith("$"):
        value = value[1:].strip()
    if re.fullmatch(r"\d+(?:\.\d{2})?", value):
        normalized = value
    elif re.fullmatch(r"\d+,\d{2}", value):
        normalized = value.replace(",", ".")
    elif re.fullmatch(r"[1-9]\d{0,2}(?:,\d{3})+\.\d{2}", value):
        normalized = value.replace(",", "")
    elif re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+,\d{2}", value):
        normalized = value.replace(".", "").replace(",", ".")
    else:
        raise ValidationError("price: unsupported or ambiguous format")
    if len(normalized) > 16:
        raise ValidationError("price: out of range")
    cents = int(Decimal(normalized) * 100)
    if not 0 < cents <= 100_000_000:
        raise ValidationError("price: must be positive and at most USD 1,000,000")
    return cents


def classify_rules(title, description=""):
    content = f"{title} {description}".casefold()
    for category, pattern in RULES:
        match = re.search(pattern, content)
        if match:
            return category, match.group()
    return "other", ""


@dataclass(frozen=True)
class Product:
    merchant: str
    sku: str
    title: str
    description: str
    price_cents: int
    currency: str
    category: str
    evidence: str

    @property
    def key(self):
        return self.merchant.casefold(), self.sku.casefold()

    def as_dict(self):
        return asdict(self)


def normalize(row):
    if not isinstance(row, dict):
        raise ValidationError("record: expected an object")
    merchant = text(row.get("merchant"), "merchant", 80)
    sku = text(row.get("sku"), "sku", 80)
    title = text(row.get("title"), "title", 300)
    description = text(row.get("description", ""), "description", 2000, required=False)
    currency = text(row.get("currency"), "currency", 3).upper()
    if currency != "USD":
        raise ValidationError("currency: only USD is supported; no implicit conversion")
    category, evidence = classify_rules(title, description)
    return Product(merchant, sku, title, description, price_cents(row.get("price")),
                   currency, category, evidence)
