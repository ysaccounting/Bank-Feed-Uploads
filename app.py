import io
import os
import time
import uuid
import shutil
import tempfile
from datetime import datetime

import pandas as pd
from flask import Flask, request, jsonify, send_file, send_from_directory, abort
from parsers import parse_platform, PLATFORM_CONFIG

app = Flask(__name__, static_folder=None)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STORE_DIR = os.path.join(tempfile.gettempdir(), "bfu_store")
os.makedirs(STORE_DIR, exist_ok=True)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def _cleanup_old(max_age_seconds=12 * 3600):
    now = time.time()
    for name in os.listdir(STORE_DIR):
        path = os.path.join(STORE_DIR, name)
        try:
            if os.path.isdir(path) and now - os.path.getmtime(path) > max_age_seconds:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


def _log_conversion(broker, platform, account_name, start_date, end_date, row_count):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        import requests
        requests.post(
            f"{SUPABASE_URL}/rest/v1/conversion_log",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={
                "broker":       broker,
                "platform":     platform,
                "account_name": account_name,
                "start_date":   str(start_date),
                "end_date":     str(end_date),
                "row_count":    row_count,
            },
            timeout=5,
        )
    except Exception:
        pass


def _ordinal(n):
    s = ["th", "st", "nd", "rd"]
    v = n % 100
    suffix = s[(v - 20) % 10] if (v - 20) % 10 < 4 else (s[v] if v < 4 else s[0])
    return f"{n}{suffix}"


def _friendly_date_range(start, end):
    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    s = f"{months[start.month - 1]}_{_ordinal(start.day)}"
    e = f"{months[end.month - 1]}_{_ordinal(end.day)}"
    return f"{s}_thru_{e}"


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/platforms")
def platforms():
    return jsonify(sorted(PLATFORM_CONFIG.keys()))


@app.route("/process", methods=["POST"])
def process():
    broker       = request.form.get("broker", "").strip()
    platform     = request.form.get("platform", "").strip()
    account_name = request.form.get("account_name", "").strip()
    date_start   = request.form.get("date_start", "").strip() or None
    date_end     = request.form.get("date_end", "").strip()   or None

    if not broker or not platform:
        return jsonify({"error": "Broker and Platform are required."}), 400
    if not date_start or not date_end:
        return jsonify({"error": "Start date and End date are required."}), 400

    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"error": "Please upload a source file."}), 400

    try:
        ds = datetime.strptime(date_start, "%Y-%m-%d").date()
        de = datetime.strptime(date_end,   "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format."}), 400

    try:
        result = parse_platform(file, platform, date_start=ds, date_end=de)
    except Exception as e:
        return jsonify({"error": f"Could not parse file: {e}"}), 500

    if result is None or result.empty:
        return jsonify({"error": "No transactions found in that date range."}), 400

    # Build filename
    broker_clean = broker.replace(" ", "_")
    if account_name:
        platform_clean = platform.replace(" ", "_") + f"_({account_name})"
    else:
        platform_clean = platform.replace(" ", "_")
    date_range = _friendly_date_range(ds, de)
    filename = f"{broker_clean}_{platform_clean}_{date_range}.csv"

    # Save to disk
    token  = uuid.uuid4().hex
    folder = os.path.join(STORE_DIR, token)
    os.makedirs(folder, exist_ok=True)

    split         = request.form.get("split", "0").strip()
    rows_per_file = int(request.form.get("rows_per_file", 50)) if split == "1" else None

    files_out = []
    if rows_per_file:
        # Combined file
        result.to_csv(os.path.join(folder, filename), index=False)
        files_out.append({"url": f"/download/{token}/{filename}", "name": filename})
        # Split files
        chunks = [result.iloc[i:i+rows_per_file] for i in range(0, len(result), rows_per_file)]
        for idx, chunk in enumerate(chunks, 1):
            chunk_name = filename.replace(".csv", f"_{idx}.csv")
            chunk.to_csv(os.path.join(folder, chunk_name), index=False)
            files_out.append({"url": f"/download/{token}/{chunk_name}", "name": chunk_name})
    else:
        result.to_csv(os.path.join(folder, filename), index=False)
        files_out.append({"url": f"/download/{token}/{filename}", "name": filename})

    _cleanup_old()

    return jsonify({
        "row_count": len(result),
        "files":     files_out,
        "preview":   result.head(8).to_dict(orient="records"),
    })


@app.route("/download/<token>")
def download(token):
    folder = os.path.join(STORE_DIR, os.path.basename(token))
    if not os.path.isdir(folder):
        abort(404)
    csvs = [f for f in os.listdir(folder) if f.lower().endswith(".csv")]
    if not csvs:
        abort(404)
    return send_file(
        os.path.join(folder, csvs[0]),
        mimetype="text/csv",
        as_attachment=True,
        download_name=csvs[0],
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)


@app.route("/download/<token>/<fname>")
def download_named(token, fname):
    folder = os.path.join(STORE_DIR, os.path.basename(token))
    path   = os.path.join(folder, os.path.basename(fname))
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype="text/csv", as_attachment=True, download_name=fname)
