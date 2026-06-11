import re
import io
import pandas as pd
from datetime import datetime


def _read(file) -> bytes:
    if hasattr(file, 'seek'):
        file.seek(0)
    return file.read()


def _clean_amount(val) -> float:
    if pd.isna(val):
        return 0.0
    s = str(val).replace("$", "").replace(",", "").strip()
    if re.match(r'^\(.*\)$', s):
        return -float(s.replace("(", "").replace(")", ""))
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_slash_date(s: str):
    s = s.strip()
    m = re.match(r'^(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2}):(\d{2})(AM|PM)$', s, re.IGNORECASE)
    if not m:
        return None
    hours = int(m.group(2))
    ampm = m.group(5).upper()
    if ampm == "PM" and hours != 12:
        hours += 12
    if ampm == "AM" and hours == 12:
        hours = 0
    try:
        return datetime.strptime(f"{m.group(1)} {hours:02d}:{m.group(3)}:{m.group(4)}", "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _parse_evopay_date(val: str):
    s = str(val).strip()
    m = re.match(r"^(\d{2}-\d{2}-\d{4})\s+(\d{1,2}:\d{2})\s*(am|pm)$", s, re.IGNORECASE)
    if m:
        try:
            return datetime.strptime(m.group(1) + " " + m.group(2) + " " + m.group(3).upper(), "%m-%d-%Y %I:%M %p")
        except ValueError:
            pass
    return None


def _parse_date_flexible(val: str):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y",
                "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(val).strip(), fmt)
        except ValueError:
            continue
    return None


def _load_df(file) -> pd.DataFrame:
    data = _read(file)
    name = getattr(file, 'filename', getattr(file, 'name', '')).lower()
    if name.endswith('.xlsx') or name.endswith('.xls'):
        return pd.read_excel(io.BytesIO(data), dtype=str).fillna("")
    return pd.read_csv(io.BytesIO(data), dtype=str).fillna("")


PLATFORM_CONFIG = {
    "Divvy CR": {
        "date_col": "Cleared Time in Statement (MT)",
        "desc_cols": ["Clean Merchant Name", "Card Name", "Card Last 4"],
        "amount_col": "Amount",
    },
    "Divvy PF": {
        "date_col": "Cleared Time in Statement (MT)",
        "desc_cols": ["Clean Merchant Name", "Card Name", "Card Last 4"],
        "amount_col": "Amount",
    },
    "EvoPay": {
        "date_col": "Date",
        "desc_cols": ["Customer", "ID"],
        "amount_col": "Total",
        "negate_amount": True,
        "evopay": True,
    },
    "Global Rewards": {
        "date_col": "Posted Date",
        "desc_cols": ["Description", "Cardholder Name", "Last 4 Digits"],
        "amount_col": "Transaction Amount",
        "negate_amount": True,
        "exclude_statuses": ["DECLINED", "PENDING", "REVERSAL", "FUNDS TRANSFER", "DEPOSIT"],
    },
    "Slash": {
        "date_col": "Date (UTC)",
        "desc_cols": ["Description", "Card Name", "Last 4"],
        "amount_col": "Amount",
        "slash_date": True,
        "exclude_types": ["temporary_credit_loan", "card_decline", "between_slash_accounts",
                          "loan_transaction", "card_authorization"],
    },
    "Taekus": {
        "date_col": "posted date",
        "desc_cols": ["description", "card nickname", "card last 4"],
        "amount_col": "transaction amount",
        "exclude_if_empty_col": "card nickname",
    },
    "Wex CR": {
        "date_col": "Transaction.Posting Dt",
        "desc_cols": ["Transaction.Merchant Name", "Purchase Card Log.Name", "Card Number.Card No"],
        "amount_col": "Transaction.Transaction Amount",
        "negate_amount": True,
        "wex_last4": True,
        "exclude_wex_na": True,
    },
    "Wex PF": {
        "date_col": "Transaction.Posting Dt",
        "desc_cols": ["Transaction.Merchant Name", "Purchase Card Log.Name", "Card Number.Card No"],
        "amount_col": "Transaction.Transaction Amount",
        "negate_amount": True,
        "wex_last4": True,
        "exclude_wex_na": True,
    },
}

WEX_ALT_COLS = {
    "Transaction.Posting Dt": "Posting Date",
    "Transaction.Merchant Name": "Merchant Name",
    "Purchase Card Log.Name": "Name on Card",
    "Card Number.Card No": "Card Number",
    "Transaction.Transaction Amount": "Transaction Amount ",
}


def parse_platform(file, platform: str, date_start=None, date_end=None) -> pd.DataFrame:
    config = PLATFORM_CONFIG.get(platform)
    if not config:
        return None

    df = _load_df(file)
    output = []

    from datetime import datetime as dt
    start_dt = dt.combine(date_start, dt.min.time()) if date_start else None
    end_dt   = dt.combine(date_end,   dt.max.time()) if date_end   else None

    for _, row in df.iterrows():
        # Exclude by type (Slash)
        if "exclude_types" in config:
            if row.get("Type", "").strip() in config["exclude_types"]:
                continue

        # Exclude Wex N/A cardholders
        if config.get("exclude_wex_na"):
            if row.get(config["desc_cols"][1], "").strip() == "N/A":
                continue

        # Exclude if empty col (Taekus)
        if "exclude_if_empty_col" in config:
            if not row.get(config["exclude_if_empty_col"], "").strip():
                continue

        # Exclude by status (Global Rewards)
        if "exclude_statuses" in config:
            if row.get("Status", "").strip().upper() in config["exclude_statuses"]:
                continue

        # EvoPay: keep only Accepted or Completed for both states
        if config.get("evopay"):
            buyer  = row.get("Buyer State",  "").strip()
            seller = row.get("Seller State", "").strip()
            if buyer not in {"Accepted", "Completed"} or seller not in {"Accepted", "Completed"}:
                continue

        # Exclude wire deposits (global)
        if row.get(config["desc_cols"][0], "").strip().lower() == "wire deposit":
            continue

        # Auto-detect alternate Wex column names
        if config.get("wex_last4"):
            row = dict(row)
            for std_col, alt_col in WEX_ALT_COLS.items():
                if std_col not in row and alt_col in row:
                    row[std_col] = row[alt_col]

        # Parse date
        raw_date = row.get(config["date_col"], "").strip()
        if not raw_date:
            continue

        if config.get("slash_date"):
            tx_date = _parse_slash_date(raw_date)
        elif config.get("evopay"):
            tx_date = _parse_evopay_date(raw_date)
        else:
            tx_date = _parse_date_flexible(raw_date)

        if tx_date is None:
            continue
        if start_dt and tx_date < start_dt:
            continue
        if end_dt and tx_date > end_dt:
            continue

        # Format date
        formatted_date = tx_date.strftime("%-m/%-d/%Y")

        # Build description
        merchant = row.get(config["desc_cols"][0], "").strip()
        if config.get("evopay"):
            tx_id = row.get(config["desc_cols"][1], "").strip()
            description = " - ".join(filter(bool, [merchant, tx_id]))
        else:
            card_name    = row.get(config["desc_cols"][1], "").strip()
            card_last_raw = str(row.get(config["desc_cols"][2], "")).strip()
            if config.get("wex_last4"):
                card_last = card_last_raw[-4:]
            else:
                card_last = card_last_raw.lstrip("'")
                if card_last.endswith(".0"):
                    card_last = card_last[:-2]
            description = " - ".join(filter(bool, [merchant, card_name, card_last]))

        # Amount
        amount_str = str(row.get(config["amount_col"], "")).replace("$", "").replace(",", "").strip()
        if re.match(r'^\(.*\)$', amount_str):
            amount = -float(amount_str.replace("(", "").replace(")", ""))
        else:
            try:
                amount = float(amount_str)
            except ValueError:
                continue
        if config.get("negate_amount"):
            amount = -amount

        output.append({"Date": formatted_date, "Description": description, "Amount": f"{amount:.2f}"})

    result = pd.DataFrame(output, columns=["Date", "Description", "Amount"])
    if not result.empty:
        result["_sort"] = pd.to_datetime(result["Date"], errors="coerce")
        result = result.sort_values("_sort", ascending=False).drop(columns=["_sort"])
    return result
