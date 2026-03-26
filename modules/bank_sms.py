import re
import json
import hashlib
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from models.signals import RawSignal, SignalSource

# ─────────────────────────────────────────────────────────────
# LEARN: Regex patterns for Indian bank SMS formats.
#
# re.compile() pre-compiles the pattern so it's faster when
# called many times. The (?i) flag makes it case-insensitive.
#
# Named groups (?P<name>...) let us do match.group("amount")
# instead of match.group(1) — much more readable.
# ─────────────────────────────────────────────────────────────

# Matches: Rs.500, Rs 500, INR 500, Rs.1,234.56
AMOUNT_RE = re.compile(
    r"(?:rs\.?|inr)\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE
)

# Matches: Avl Bal Rs.2,340 / Balance Rs 5,200 / Bal:Rs.100
BALANCE_RE = re.compile(
    r"(?:avl\.?\s*bal|balance|bal)\s*[:\-]?\s*(?:rs\.?|inr)?\s*(?P<balance>[\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE
)

# Debit keywords
DEBIT_RE = re.compile(
    r"\b(?:debited|debit|withdrawn|withdrawal|spent|paid|purchase|dr)\b",
    re.IGNORECASE
)

# Credit keywords
CREDIT_RE = re.compile(
    r"\b(?:credited|credit|received|deposited|cr|added)\b",
    re.IGNORECASE
)

# UPI / NEFT / IMPS / ATM
CHANNEL_RE = re.compile(
    r"\b(?P<channel>UPI|NEFT|IMPS|ATM|RTGS|NACH|EMI)\b",
    re.IGNORECASE
)

# Known Indian bank SMS sender patterns
BANK_SENDERS = {
    "HDFCBK", "SBIINB", "ICICIB", "AXISBK", "KOTAKB",
    "PAYTMB", "YESBNK", "INDBNK", "PNBSMS", "BOIIND",
    "CANBNK", "UNIONB", "IDBIBK", "FEDERAL", "RBLBNK",
}


def is_bank_sms(sender: str, body: str) -> bool:
    """
    LEARN: Two-layer check.
    First check if the sender ID looks like a bank (HDFCBK, SBIINB etc.)
    If sender is unknown, fall back to checking if the body has
    both a money amount AND a debit/credit keyword.
    """
    sender_upper = sender.upper().replace(" ", "")
    if any(b in sender_upper for b in BANK_SENDERS):
        return True
    has_amount = bool(AMOUNT_RE.search(body))
    has_txn    = bool(DEBIT_RE.search(body) or CREDIT_RE.search(body))
    return has_amount and has_txn


def parse_amount(text: str) -> float | None:
    m = AMOUNT_RE.search(text)
    if m:
        return float(m.group("amount").replace(",", ""))
    return None


def parse_balance(text: str) -> float | None:
    m = BALANCE_RE.search(text)
    if m:
        return float(m.group("balance").replace(",", ""))
    return None


def parse_channel(text: str) -> str:
    m = CHANNEL_RE.search(text)
    return m.group("channel").upper() if m else "UNKNOWN"


def classify_transaction(body: str) -> str:
    """Returns 'debit', 'credit', or 'unknown'."""
    if DEBIT_RE.search(body):
        return "debit"
    if CREDIT_RE.search(body):
        return "credit"
    return "unknown"


def compute_urgency(txn_type: str, amount: float | None, balance: float | None) -> float:
    """
    LEARN: Rule-based urgency scoring.
    We don't need ML here — simple rules work perfectly:
    - Low balance is always urgent
    - Large debits are more urgent than small ones
    - Credits are low urgency (good news)
    """
    score = 0.4  # baseline

    if balance is not None and balance < 500:
        score = 0.95   # critically low balance
    elif balance is not None and balance < 1500:
        score = 0.80   # low balance warning

    if txn_type == "debit" and amount is not None:
        if amount >= 5000:
            score = max(score, 0.85)
        elif amount >= 1000:
            score = max(score, 0.65)

    if txn_type == "credit":
        score = min(score, 0.45)   # credits are good, lower urgency

    return round(score, 2)


def parse_sms(sender: str, body: str, received_at: datetime | None = None) -> RawSignal | None:
    """
    Main entry point. Takes a raw SMS and returns a RawSignal,
    or None if it doesn't look like a bank transaction SMS.
    """
    if not is_bank_sms(sender, body):
        return None

    txn_type = classify_transaction(body)
    amount   = parse_amount(body)
    balance  = parse_balance(body)
    channel  = parse_channel(body)
    ts       = received_at or datetime.now(timezone.utc)

    # Build a human-readable subject line
    if amount and txn_type != "unknown":
        direction = "debited" if txn_type == "debit" else "credited"
        subject   = f"₹{amount:,.0f} {direction} via {channel}"
        if balance is not None:
            subject += f" — Bal ₹{balance:,.0f}"
    else:
        subject = "Bank SMS received"

    urgency = compute_urgency(txn_type, amount, balance)

    # Stable signal_id based on content hash — prevents duplicates
    signal_id = "bank_" + hashlib.md5(body.encode()).hexdigest()[:10]

    return RawSignal(
        source    = SignalSource.BANK_SMS,
        content   = body.strip(),
        metadata  = {
            "subject":          subject,
            "sender":           sender,
            "txn_type":         txn_type,
            "amount":           amount,
            "balance":          balance,
            "channel":          channel,
            "urgency_score":    urgency,
            "sender_weight":    0.95,
            "sender_category":  "bank",
        },
        received_at = ts,
        signal_id   = signal_id,
    )


# ── Test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_messages = [
        ("HDFCBK", "HDFC Bank: Rs.1,500 debited from A/c XX1234 on 26-Mar via UPI. Avl Bal Rs.420.50"),
        ("SBIINB", "Your SBI A/c XXXX5678 credited with Rs.10,000 on 26/03/26. Balance Rs.12,340."),
        ("ICICIB", "ICICI Bank: ATM withdrawal of Rs.2,000 from A/c XX9012. Bal Rs.3,100."),
        ("AD-ZOMATO", "Your order is on the way! Track here: zomato.com/track"),  # should be ignored
        ("UNKNOWN", "Rs.500 debited from your account. Balance Rs.150."),          # fallback detection
    ]

    print("\n── Bank SMS Parser Test ──\n")
    for sender, body in test_messages:
        signal = parse_sms(sender, body)
        if signal:
            m = signal.metadata
            print(f"✓ [{m['txn_type'].upper():6}] {m['subject']}")
            print(f"  urgency={m['urgency_score']}  channel={m['channel']}  sender={sender}")
            print(f"  id={signal.signal_id}\n")
        else:
            print(f"✗ Ignored: [{sender}] {body[:60]}\n")
