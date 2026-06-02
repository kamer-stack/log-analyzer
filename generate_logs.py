#!/usr/bin/env python3
"""
generate_logs.py — Test log generator for the Log Analyzer Tool
Dev Weekend Fellowship Assessment

Usage:
    python scripts/generate_logs.py                          # default: sample_logs.log
    python scripts/generate_logs.py --output my.log          # custom output file
    python scripts/generate_logs.py --lines 5000             # more lines
    python scripts/generate_logs.py --seed 42                # reproducible output
    python scripts/generate_logs.py --edge-cases-only        # only edge case lines

Generates realistic Apache/Nginx-style log lines plus deliberately injected
edge cases covering all 38 scenarios documented in the assessment.
"""

import argparse
import json
import random
import time
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Data pools
# ---------------------------------------------------------------------------

METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
METHOD_WEIGHTS = [60, 15, 8, 6, 5, 4, 2]

PATHS = [
    "/api/users", "/api/users/123", "/api/users?page=2&limit=50",
    "/api/orders", "/api/orders/456", "/api/products",
    "/api/products/789", "/api/auth/login", "/api/auth/logout",
    "/api/search?q=hello+world", "/health", "/metrics",
    "/static/main.css", "/static/app.js",
    "/api/files/my document.pdf",        # edge case 21: path with spaces
    "/api/reports/2024/Q1",
]

STATUS_CODES = [200, 200, 200, 200, 201, 204, 301, 304, 400, 401, 403, 404, 404, 429, 500, 502, 503]

IPS = [
    "192.168.1.{}".format(i) for i in range(1, 20)
] + [
    "10.0.0.{}".format(i) for i in range(1, 10)
] + [
    "172.16.0.1", "203.0.113.42", "198.51.100.7",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "curl/7.68.0",
    "python-requests/2.28.0",
    "Go-http-client/1.1",
    "Googlebot/2.1",
]

REFERRERS = [
    '"-"',
    '"https://example.com/dashboard"',
    '"https://search.example.org/q=products"',
    '"https://partner.site/referral?id=abc&source=newsletter"',  # edge 18: spaces if unquoted
]

# ---------------------------------------------------------------------------
# Baseline log line builder
# ---------------------------------------------------------------------------

def make_baseline_line(ts: datetime, ip: str, method: str, path: str,
                        status: int, resp_ms: int) -> str:
    """Standard format: 2024-03-15T14:23:01Z IP METHOD /path STATUS 142ms"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} {path} {status} {resp_ms}ms"


# ---------------------------------------------------------------------------
# Edge case line builders (one per edge case)
# ---------------------------------------------------------------------------

def ec02_slash_date(ts, ip, method, path, status, resp_ms):
    """Edge 2: slash-separated date"""
    ts_str = ts.strftime("%Y/%m/%d %H:%M:%S")
    return f"{ts_str} {ip} {method} {path} {status} {resp_ms}ms"

def ec03_human_month(ts, ip, method, path, status, resp_ms):
    """Edge 3: human-readable month"""
    ts_str = ts.strftime("%d-%b-%Y %H:%M:%S")
    return f"{ts_str} {ip} {method} {path} {status} {resp_ms}ms"

def ec04_unix_epoch(ts, ip, method, path, status, resp_ms):
    """Edge 4: unix epoch integer timestamp"""
    epoch = int(ts.timestamp())
    return f"{epoch} {ip} {method} {path} {status} {resp_ms}ms"

def ec05_missing_timestamp(ip, method, path, status, resp_ms):
    """Edge 5: missing timestamp entirely"""
    return f"{ip} {method} {path} {status} {resp_ms}ms"

def ec06_malformed_timestamp(ip, method, path, status, resp_ms):
    """Edge 6: malformed timestamp"""
    return f"2024-99-99T25:61:00Z {ip} {method} {path} {status} {resp_ms}ms"

def ec07_response_seconds(ts, ip, method, path, status, resp_ms):
    """Edge 8: response time as decimal seconds"""
    resp_s = resp_ms / 1000.0
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} {path} {status} {resp_s:.3f}s"

def ec08_response_bare(ts, ip, method, path, status, resp_ms):
    """Edge 9: bare number, no unit"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} {path} {status} {resp_ms}"

def ec09_zero_response(ts, ip, method, path, status):
    """Edge 10a: zero response time"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} {path} {status} 0ms"

def ec10_negative_response(ts, ip, method, path, status):
    """Edge 10b: negative response time (anomaly)"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} {path} {status} -50ms"

def ec11_missing_response(ts, ip, method, path, status):
    """Edge 11: missing response time entirely"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} {path} {status}"

def ec13_dash_status(ts, ip, method, path, resp_ms):
    """Edge 13: dash placeholder for status"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} {path} - {resp_ms}ms"

def ec14_missing_status(ts, ip, method, path, resp_ms):
    """Edge 14: status missing (only 5 fields)"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} {path} {resp_ms}ms"

def ec15_nonstandard_status(ts, ip, method, path, resp_ms):
    """Edge 15: non-standard status code"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    bad = random.choice([999, 0, "OK", "2xx"])
    return f"{ts_str} {ip} {method} {path} {bad} {resp_ms}ms"

def ec17_user_agent(ts, ip, method, path, status, resp_ms):
    """Edge 17: user agent appended (no quotes)"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    ua = random.choice(USER_AGENTS)
    return f"{ts_str} {ip} {method} {path} {status} {resp_ms}ms {ua}"

def ec18_quoted_referrer(ts, ip, method, path, status, resp_ms):
    """Edge 18: quoted referrer with spaces — naive split breaks"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    ref = random.choice(REFERRERS)
    return f'{ts_str} {ip} {method} {path} {status} {resp_ms}ms {ref}'

def ec19_multi_extra(ts, ip, method, path, status, resp_ms):
    """Edge 19: both user agent and referrer"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    ua = random.choice(USER_AGENTS)
    ref = random.choice(REFERRERS)
    return f'{ts_str} {ip} {method} {path} {status} {resp_ms}ms {ua} {ref}'

def ec20_query_string(ts, ip, method, path, status, resp_ms):
    """Edge 20: path with query string"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method} /api/users?page=2&limit=50&sort=desc {status} {resp_ms}ms"

def ec22_blank_line():
    """Edge 22: completely blank line"""
    return ""

def ec23_truncated(ts, ip, method):
    """Edge 23: partial / truncated line"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts_str} {ip} {method}"

def ec24_stack_trace(ts):
    """Edge 24: multi-line stack trace block (returns list of lines)"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return [
        f"{ts_str} 10.0.0.1 GET /api/crash 500 1200ms",
        "Traceback (most recent call last):",
        '  File "app.py", line 42, in handler',
        "    result = db.query(sql)",
        "AttributeError: 'NoneType' object has no attribute 'query'",
    ]

def ec25_whitespace(ts, ip, method, path, status, resp_ms):
    """Edge 25: leading/trailing whitespace"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"   {ts_str} {ip} {method} {path} {status} {resp_ms}ms   "

def ec26_non_utf8():
    """Edge 26: non-UTF-8 / binary characters (returned as bytes -> decoded lossy)"""
    return "2024-03-15T14:23:01Z 192.168.1.99 GET /api/bad\xff\xfe 200 55ms"

def ec27_comment():
    """Edge 27: comment / header line"""
    return random.choice([
        "# Log started at 2024-03-15T00:00:00Z",
        "# Generated by nginx 1.24",
        "timestamp ip method path status response_time",
        "--- SESSION START ---",
    ])

def ec28_duplicate(line: str):
    """Edge 28: return the same line twice (caller handles)"""
    return line

def ec29_json_line(ts, ip, method, path, status, resp_ms):
    """Edge 29: fully JSON-formatted log line"""
    return json.dumps({
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ip": ip,
        "method": method,
        "path": path,
        "status_code": status,
        "response_time": f"{resp_ms}ms",
    })

def ec30_json_field_variants(ts, ip, method, path, status, resp_ms):
    """Edge 30: JSON with alternate field names"""
    return json.dumps({
        "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "remote_addr": ip,
        "verb": method,
        "uri": path,
        "status": status,         # 'status' instead of 'status_code'
        "duration_ms": resp_ms,   # numeric, no unit suffix
    })

def ec31_json_resp_number(ts, ip, method, path, status, resp_ms):
    """Edge 31: JSON with response time as plain number"""
    return json.dumps({
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ip": ip,
        "method": method,
        "path": path,
        "status_code": status,
        "response_time": resp_ms,  # number, not "142ms"
    })

def ec32_partial_json(ts):
    """Edge 32: partial / malformed JSON"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'{{"timestamp":"{ts_str}","ip":"10.0.0.5","method":"GET"'  # truncated

def ec33_mixed_format(ts, ip, method, path, status, resp_ms):
    """Edge 33: plaintext prefix + JSON suffix"""
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = json.dumps({"status_code": status, "response_time": f"{resp_ms}ms"})
    return f"ACCESS {ts_str} {ip} {method} {path} {payload}"

def ec38_no_final_newline(ts, ip, method, path, status, resp_ms):
    """Edge 38: last line has no trailing newline — handled by write logic, not line content"""
    return make_baseline_line(ts, ip, method, path, status, resp_ms)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def random_ts(base: datetime, spread_hours: int = 48) -> datetime:
    offset = random.randint(0, spread_hours * 3600)
    return base + timedelta(seconds=offset)

def random_resp() -> int:
    # mostly fast, occasional slow spikes
    if random.random() < 0.05:
        return random.randint(2000, 8000)
    return random.randint(5, 800)

def random_ip() -> str:
    return random.choice(IPS)

def random_method() -> str:
    return random.choices(METHODS, weights=METHOD_WEIGHTS)[0]

def random_path() -> str:
    return random.choice(PATHS)

def random_status() -> int:
    return random.choice(STATUS_CODES)


def build_edge_cases(base_ts: datetime) -> list[str]:
    """
    Returns one representative line (or block) for each of the 38 edge cases.
    Lines with multiple outputs (e.g. stack traces) are flattened in.
    """
    ip = random_ip()
    m  = random_method()
    p  = random_path()
    s  = random_status()
    r  = random_resp()
    ts = random_ts(base_ts, 24)

    lines = []

    # --- Timestamp variations (1–6) ---
    lines.append(f"# --- EDGE CASES: Timestamp variations ---")
    lines.append(make_baseline_line(ts, ip, m, p, s, r))          # 1: baseline
    lines.append(ec02_slash_date(ts, ip, m, p, s, r))             # 2
    lines.append(ec03_human_month(ts, ip, m, p, s, r))            # 3
    lines.append(ec04_unix_epoch(ts, ip, m, p, s, r))             # 4
    lines.append(ec05_missing_timestamp(ip, m, p, s, r))          # 5
    lines.append(ec06_malformed_timestamp(ip, m, p, s, r))        # 6

    # --- Response time variations (7–11) ---
    lines.append(f"# --- EDGE CASES: Response time variations ---")
    lines.append(make_baseline_line(ts, ip, m, p, s, r))          # 7: baseline ms
    lines.append(ec07_response_seconds(ts, ip, m, p, s, r))       # 8
    lines.append(ec08_response_bare(ts, ip, m, p, s, r))          # 9
    lines.append(ec09_zero_response(ts, ip, m, p, s))             # 10a
    lines.append(ec10_negative_response(ts, ip, m, p, s))         # 10b
    lines.append(ec11_missing_response(ts, ip, m, p, s))          # 11

    # --- Status code variations (12–16) ---
    lines.append(f"# --- EDGE CASES: Status code variations ---")
    lines.append(make_baseline_line(ts, ip, m, p, 200, r))        # 12: standard
    lines.append(ec13_dash_status(ts, ip, m, p, r))               # 13
    lines.append(ec14_missing_status(ts, ip, m, p, r))            # 14
    lines.append(ec15_nonstandard_status(ts, ip, m, p, r))        # 15
    # 16 (field shift) — status ends up in wrong position:
    lines.append(f"2024-03-15T14:23:01Z {ip} {m} 200 /api/shifted {r}ms")  # 16

    # --- Extra/unexpected fields (17–21) ---
    lines.append(f"# --- EDGE CASES: Extra/unexpected fields ---")
    lines.append(ec17_user_agent(ts, ip, m, p, s, r))             # 17
    lines.append(ec18_quoted_referrer(ts, ip, m, p, s, r))        # 18
    lines.append(ec19_multi_extra(ts, ip, m, p, s, r))            # 19
    lines.append(ec20_query_string(ts, ip, m, p, s, r))           # 20
    # 21: path with spaces already in PATHS pool; make explicit:
    lines.append(make_baseline_line(ts, ip, "GET", "/api/files/my document.pdf", 200, r))  # 21

    # --- Malformed/broken lines (22–28) ---
    lines.append(f"# --- EDGE CASES: Malformed/broken lines ---")
    lines.append(ec22_blank_line())                                # 22
    lines.append(ec23_truncated(ts, ip, m))                       # 23
    lines.extend(ec24_stack_trace(ts))                             # 24
    lines.append(ec25_whitespace(ts, ip, m, p, s, r))             # 25
    lines.append(ec26_non_utf8())                                  # 26
    lines.append(ec27_comment())                                   # 27
    baseline = make_baseline_line(ts, ip, m, p, s, r)
    lines.append(baseline)
    lines.append(ec28_duplicate(baseline))                         # 28: duplicate

    # --- Mixed/alternate format lines (29–33) ---
    lines.append(f"# --- EDGE CASES: Mixed/alternate formats ---")
    lines.append(ec29_json_line(ts, ip, m, p, s, r))              # 29
    lines.append(ec30_json_field_variants(ts, ip, m, p, s, r))    # 30
    lines.append(ec31_json_resp_number(ts, ip, m, p, s, r))       # 31
    lines.append(ec32_partial_json(ts))                            # 32
    lines.append(ec33_mixed_format(ts, ip, m, p, s, r))           # 33

    # --- File-level edge cases 34–38 are exercised by separate mini-files ---
    # (see write_edge_case_files below)

    return lines


def write_edge_case_files(output_dir: str, base_ts: datetime, rng: random.Random):
    """
    Write separate mini-files for file-level edge cases 34–38.
    """
    import os
    os.makedirs(output_dir, exist_ok=True)

    # Edge 35: empty file
    open(os.path.join(output_dir, "edge35_empty.log"), "w").close()

    # Edge 37: file with no valid lines at all (100% malformed)
    with open(os.path.join(output_dir, "edge37_all_malformed.log"), "w") as f:
        for _ in range(10):
            f.write("THIS IS NOT A VALID LOG LINE AT ALL\n")
        f.write("!!!!!!!!!!!!!!!!!!!!!\n")
        f.write("1 2\n")

    # Edge 38: file missing final newline (last line has no \n)
    ts = random_ts(base_ts, 1)
    ip = rng.choice(IPS)
    line = make_baseline_line(ts, ip, "GET", "/api/users", 200, 123)
    with open(os.path.join(output_dir, "edge38_no_final_newline.log"), "w", newline="") as f:
        f.write(make_baseline_line(ts, ip, "GET", "/health", 200, 5) + "\n")
        f.write(line)  # deliberately NO trailing newline

    # Edge 34: large file hint — we don't actually write gigabytes but
    # sample_logs.log itself is the large-file test target; note it in a readme
    with open(os.path.join(output_dir, "README_edge_cases.txt"), "w") as f:
        f.write(
            "Edge case files for analyze.py testing\n"
            "======================================\n\n"
            "edge35_empty.log          — Edge 35: empty file\n"
            "edge37_all_malformed.log  — Edge 37: 100% malformed lines\n"
            "edge38_no_final_newline.log — Edge 38: no trailing newline\n\n"
            "Edge 34 (large file / streaming): use sample_logs.log with --lines 100000\n"
            "  python scripts/generate_logs.py --lines 100000 --output large_test.log\n"
            "  python analyze.py large_test.log\n\n"
            "Edge 36 (file not found): python analyze.py nonexistent.log\n"
        )

    print(f"  Edge-case mini-files written to: {output_dir}/")


def generate(
    n_lines: int,
    output_path: str,
    seed: int | None,
    edge_cases_only: bool,
    include_edge_cases: bool = True,
):
    rng = random.Random(seed)
    random.seed(seed)

    base_ts = datetime(2024, 3, 15, 0, 0, 0, tzinfo=timezone.utc)

    lines: list[str] = []

    if include_edge_cases:
        lines += build_edge_cases(base_ts)

    if not edge_cases_only:
        for _ in range(n_lines):
            ts = random_ts(base_ts, 48)
            ip = rng.choice(IPS)
            m  = rng.choices(METHODS, weights=METHOD_WEIGHTS)[0]
            p  = rng.choice(PATHS)
            s  = rng.choice(STATUS_CODES)
            r  = random_resp()
            lines.append(make_baseline_line(ts, ip, m, p, s, r))

    # Shuffle only the non-edge-case portion so edge cases stay readable at top
    if not edge_cases_only and include_edge_cases:
        ec_end = len(build_edge_cases(base_ts))  # approx boundary
        tail = lines[ec_end:]
        rng.shuffle(tail)
        lines = lines[:ec_end] + tail

    # Write — last line WITHOUT trailing newline to exercise edge 38 in main file too
    with open(output_path, "w", encoding="utf-8", errors="replace") as fh:
        for line in lines[:-1]:
            fh.write(line + "\n")
        if lines:
            fh.write(lines[-1])  # no trailing newline on last line (edge 38)

    return len(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate test log files for the Log Analyzer Tool."
    )
    parser.add_argument(
        "--output", "-o",
        default="sample_logs.log",
        help="Output log file path (default: sample_logs.log)",
    )
    parser.add_argument(
        "--lines", "-n",
        type=int,
        default=500,
        help="Number of normal log lines to generate (default: 500)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible output",
    )
    parser.add_argument(
        "--edge-cases-only",
        action="store_true",
        help="Write only the edge case lines (useful for focused testing)",
    )
    parser.add_argument(
        "--no-edge-cases",
        action="store_true",
        help="Skip edge case injection (clean log only)",
    )
    parser.add_argument(
        "--edge-case-files-dir",
        default="test_logs",
        help="Directory to write edge-case mini-files into (default: test_logs/)",
    )
    parser.add_argument(
        "--skip-mini-files",
        action="store_true",
        help="Skip writing the edge-case mini-files",
    )
    args = parser.parse_args()

    start = time.perf_counter()
    print(f"Generating logs → {args.output}")

    count = generate(
        n_lines=args.lines,
        output_path=args.output,
        seed=args.seed,
        edge_cases_only=args.edge_cases_only,
        include_edge_cases=not args.no_edge_cases,
    )

    if not args.skip_mini_files:
        base_ts = datetime(2024, 3, 15, 0, 0, 0, tzinfo=timezone.utc)
        write_edge_case_files(
            args.edge_case_files_dir,
            base_ts,
            random.Random(args.seed),
        )

    elapsed = time.perf_counter() - start
    print(f"  {count} lines written in {elapsed:.2f}s")
    print(f"  Run: python analyze.py {args.output}")


if __name__ == "__main__":
    main()
