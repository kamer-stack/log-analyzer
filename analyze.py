#!/usr/bin/env python3
"""
analyze.py — Log Analyzer Tool
Dev Weekend Fellowship Assessment

Usage:
    python analyze.py logfile.log
    python analyze.py logfile.log --top 10
    python analyze.py logfile.log --json
    python analyze.py logfile.log --no-color
"""

import argparse
import json
import re
import sys
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional


class Colors:
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    RED = "\033[91m"; YELLOW = "\033[93m"; GREEN = "\033[92m"
    CYAN = "\033[96m"; MAGENTA = "\033[95m"; BLUE = "\033[94m"; WHITE = "\033[97m"

_USE_COLOR = True

def c(color, text):
    return f"{color}{text}{Colors.RESET}" if _USE_COLOR else text


class LogRecord:
    __slots__ = ("raw","line_number","timestamp","ip","method","path","status_code","response_ms","anomalies")
    def __init__(self, raw, line_number):
        self.raw = raw; self.line_number = line_number
        self.timestamp = None; self.ip = None; self.method = None; self.path = None
        self.status_code = None; self.response_ms = None; self.anomalies = []


_TIMESTAMP_FORMATS = [
    ("%Y-%m-%dT%H:%M:%SZ", False), ("%Y/%m/%d %H:%M:%S", False),
    ("%d-%b-%Y %H:%M:%S", False), ("%Y-%m-%d %H:%M:%S", False),
    ("%d/%b/%Y:%H:%M:%S", False),
]

def parse_timestamp(token):
    if re.fullmatch(r"\d{9,11}", token):
        try:
            return datetime.fromtimestamp(int(token), tz=timezone.utc), "unix_epoch"
        except (ValueError, OSError):
            pass
    for fmt, _ in _TIMESTAMP_FORMATS:
        try:
            dt = datetime.strptime(token, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, ""
        except ValueError:
            continue
    if re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", token) or re.match(r"\d{2}-[A-Za-z]{3}-\d{4}", token):
        return None, "malformed_timestamp"
    return None, "not_a_timestamp"


def parse_response_time(token):
    anomalies = []
    token = token.strip()
    if not token:
        return None, []
    if re.fullmatch(r"-?\d+(\.\d+)?", token):
        val = float(token)
        if val < 0: anomalies.append(f"negative_response_time:{val}ms")
        return val, anomalies
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)ms", token, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        if val < 0: anomalies.append(f"negative_response_time:{val}ms")
        return val, anomalies
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)s", token, re.IGNORECASE)
    if m:
        val = float(m.group(1)) * 1000.0
        if val < 0: anomalies.append(f"negative_response_time:{val}ms")
        return val, anomalies
    return None, []


def parse_status_code(token):
    anomalies = []
    token = token.strip()
    if token == "-":
        anomalies.append("status_dash_placeholder")
        return None, anomalies
    if re.fullmatch(r"\d{3}", token):
        code = int(token)
        if code not in range(100, 600):
            anomalies.append(f"nonstandard_status:{code}")
        return code, anomalies
    anomalies.append(f"nonstandard_status:{token!r}")
    return None, anomalies


_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$|^[0-9a-fA-F:]+:[0-9a-fA-F:]+$")
def looks_like_ip(token): return bool(_IP_RE.match(token))

_HTTP_METHODS = frozenset(["GET","POST","PUT","DELETE","PATCH","HEAD","OPTIONS","TRACE","CONNECT"])
def looks_like_method(token): return token.upper() in _HTTP_METHODS


_JSON_FIELD_MAP = {
    "timestamp":"timestamp","ts":"timestamp","time":"timestamp","@timestamp":"timestamp",
    "ip":"ip","remote_addr":"ip","client_ip":"ip","host":"ip","remote_ip":"ip",
    "method":"method","verb":"method","http_method":"method","request_method":"method",
    "path":"path","uri":"path","url":"path","request_uri":"path","request":"path",
    "status_code":"status","status":"status","code":"status","http_status":"status","response_code":"status",
    "response_time":"resp_time","duration":"resp_time","duration_ms":"resp_time",
    "latency":"resp_time","elapsed":"resp_time","took":"resp_time",
}

def parse_json_line(raw):
    brace = raw.find("{")
    if brace == -1: return None
    try:
        obj = json.loads(raw[brace:])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict): return None
    normalised = {}
    for k, v in obj.items():
        mapped = _JSON_FIELD_MAP.get(k.lower())
        if mapped and mapped not in normalised:
            normalised[mapped] = v
    return normalised if normalised else None


def _tokenize(line):
    tokens = []; current = []; in_quote = False; quote_char = None
    for ch in line:
        if in_quote:
            current.append(ch)
            if ch == quote_char: in_quote = False
        elif ch in ('"', "'"):
            in_quote = True; quote_char = ch; current.append(ch)
        elif ch in (" ", "\t"):
            if current: tokens.append("".join(current)); current = []
        else:
            current.append(ch)
    if current: tokens.append("".join(current))
    return tokens

def _looks_like_resp_time(token):
    return bool(re.fullmatch(r"-?\d+(\.\d+)?(ms|s)?", token, re.IGNORECASE))


def parse_line(raw, line_number):
    line = raw.strip()
    if not line: return None, "blank"
    if line.startswith("#") or re.match(r"^[-=*]{3,}", line): return None, "comment"
    low = line.lower()
    if low.startswith("timestamp") and "method" in low and "status" in low: return None, "comment"

    # Edge 24: stack trace / exception lines — common patterns that are not log records
    if re.match(r"^\s*(at |Caused by:|Exception in thread|[\w\.$]+Exception:)", line):
        return None, "malformed"
    if re.match(r"^[A-Za-z][\w.]+Exception", line):
        return None, "malformed"

    rec = LogRecord(raw=raw, line_number=line_number)

    if "{" in line:
        obj = parse_json_line(line)
        if obj is not None:
            ts_raw = obj.get("timestamp")
            if ts_raw:
                dt, note = parse_timestamp(str(ts_raw))
                rec.timestamp = dt
                if note == "malformed_timestamp": rec.anomalies.append("malformed_timestamp")
            else:
                rec.anomalies.append("missing_timestamp")
            rec.ip = str(obj.get("ip", "")) or None
            rec.method = str(obj.get("method", "")).upper() or None
            rec.path = str(obj.get("path", "")) or None
            status_raw = obj.get("status")
            if status_raw is not None:
                code, anoms = parse_status_code(str(status_raw))
                rec.status_code = code; rec.anomalies.extend(anoms)
            else:
                rec.anomalies.append("missing_status")
            resp_raw = obj.get("resp_time")
            if resp_raw is not None:
                ms, anoms = parse_response_time(str(resp_raw))
                rec.response_ms = ms; rec.anomalies.extend(anoms)
            else:
                rec.anomalies.append("missing_response_time")
            if rec.method is None and rec.path is None and rec.ip is None:
                return None, "malformed"
            return rec, "valid"

    try:
        tokens = _tokenize(line)
    except Exception:
        return None, "malformed"

    if len(tokens) < 3: return None, "malformed"

    idx = 0; n = len(tokens)

    # Edge 2 & 3: space-separated timestamps like "2024/03/15 14:23:01" or "15-Mar-2024 14:23:01"
    # Try merging first two tokens before single-token parse
    _dt_found = False
    if n >= 2:
        combined = tokens[0] + " " + tokens[1]
        dt_try, note_try = parse_timestamp(combined)
        if dt_try is not None:
            rec.timestamp = dt_try; idx += 2; _dt_found = True

    if not _dt_found:
        dt, note = parse_timestamp(tokens[idx])
        if dt is not None:
            rec.timestamp = dt; idx += 1
        elif note == "malformed_timestamp":
            rec.anomalies.append("malformed_timestamp"); idx += 1
        else:
            rec.anomalies.append("missing_timestamp")

    if idx >= n: return None, "malformed"

    if looks_like_ip(tokens[idx]):
        rec.ip = tokens[idx]; idx += 1
    else:
        rec.anomalies.append("missing_ip")

    if idx >= n: return None, "malformed"

    if looks_like_method(tokens[idx]):
        rec.method = tokens[idx].upper(); idx += 1
    else:
        rec.anomalies.append("missing_method")

    if idx >= n: return None, "malformed"

    path_start = idx; path_end = idx
    for scan in range(idx, min(idx + 4, n)):
        tok = tokens[scan]
        if re.fullmatch(r"\d{3}", tok) or tok == "-" or re.fullmatch(r"\d{3,}", tok):
            path_end = scan; break
        if scan == idx + 3: path_end = idx + 1
    if path_end == idx: path_end = idx + 1

    rec.path = " ".join(tokens[path_start:path_end]) if path_end > path_start else None
    idx = path_end

    if idx >= n:
        rec.anomalies.append("missing_status"); rec.anomalies.append("missing_response_time")
        return rec, "valid"

    code, anoms = parse_status_code(tokens[idx])
    rec.status_code = code; rec.anomalies.extend(anoms); idx += 1

    if idx >= n:
        rec.anomalies.append("missing_response_time"); return rec, "valid"

    ms, anoms = parse_response_time(tokens[idx])
    if ms is not None or _looks_like_resp_time(tokens[idx]):
        rec.response_ms = ms; rec.anomalies.extend(anoms)
    else:
        rec.anomalies.append("missing_response_time")

    if rec.ip is None and rec.method is None and rec.path is None:
        return None, "malformed"
    return rec, "valid"


class Stats:
    def __init__(self):
        self.total_lines = 0; self.blank_lines = 0; self.comment_lines = 0
        self.valid_lines = 0; self.malformed_lines = 0
        self.endpoint_times = defaultdict(list)
        self.status_counts = defaultdict(int)
        self.ip_counts = defaultdict(int)
        self.hour_counts = defaultdict(int)
        self.anomaly_counts = defaultdict(int)
        self.seen_lines = set(); self.duplicate_count = 0

    def ingest(self, rec):
        key = rec.raw.strip()
        if key in self.seen_lines:
            self.duplicate_count += 1; self.anomaly_counts["duplicate_line"] += 1
        else:
            self.seen_lines.add(key)
        if rec.method and rec.path and rec.response_ms is not None:
            self.endpoint_times[f"{rec.method} {rec.path}"].append(rec.response_ms)
        if rec.status_code is not None:
            self.status_counts[str(rec.status_code)] += 1
        else:
            self.status_counts["unknown"] += 1
        if rec.ip: self.ip_counts[rec.ip] += 1
        if rec.timestamp: self.hour_counts[rec.timestamp.hour] += 1
        for a in rec.anomalies:
            self.anomaly_counts[re.sub(r":[^\s]+$", "", a)] += 1


def _row(label, value, color=""):
    val_str = f"{value:,}" if isinstance(value, int) else str(value)
    if color: val_str = c(color, val_str)
    print(f"  {label:<35} {val_str}")

def _bar(value, max_value, width=16):
    filled = round(value / max_value * width) if max_value else 0
    return "█" * filled + c(Colors.DIM, "░" * (width - filled))

def _spark_bar(value, max_value, width=10):
    filled = round(value / max_value * width) if max_value else 0
    col = Colors.RED if filled >= width * 0.8 else (Colors.YELLOW if filled >= width * 0.5 else Colors.GREEN)
    return c(col, "█" * filled) + c(Colors.DIM, "░" * (width - filled))

def _status_color(code):
    if code.startswith("2"): return Colors.GREEN
    if code.startswith("3"): return Colors.CYAN
    if code.startswith("4"): return Colors.YELLOW
    if code.startswith("5"): return Colors.RED
    return Colors.DIM


def print_report(stats, filepath, top_n):
    sep = c(Colors.DIM, "─" * 60); sep2 = c(Colors.DIM, "━" * 60)
    total_counted = stats.valid_lines + stats.malformed_lines
    mal_pct = (stats.malformed_lines / total_counted * 100) if total_counted else 0.0

    print(f"\n{sep2}")
    print(c(Colors.BOLD + Colors.WHITE, "  LOG ANALYSIS REPORT"))
    print(c(Colors.DIM, f"  {filepath}"))
    print(sep2)

    print(f"\n{c(Colors.BOLD, '  SUMMARY')}\n{sep}")
    _row("Total lines read", stats.total_lines)
    _row("Valid lines", stats.valid_lines, Colors.GREEN)
    _row("Malformed lines", stats.malformed_lines, Colors.RED if stats.malformed_lines else Colors.DIM)
    _row("Blank lines (skipped)", stats.blank_lines, Colors.DIM)
    _row("Comment lines (skipped)", stats.comment_lines, Colors.DIM)
    _row("Duplicate lines detected", stats.duplicate_count, Colors.YELLOW if stats.duplicate_count else Colors.DIM)
    _row("Malformed rate", f"{mal_pct:.1f}%", Colors.RED if mal_pct > 5 else Colors.GREEN)

    print(f"\n{c(Colors.BOLD, f'  TOP {top_n} SLOWEST ENDPOINTS (avg response time)')}\n{sep}")
    if stats.endpoint_times:
        avgs = {ep: sum(t)/len(t) for ep, t in stats.endpoint_times.items()}
        ranked = sorted(avgs.items(), key=lambda x: -x[1])[:top_n]
        for i, (ep, avg) in enumerate(ranked, 1):
            cnt = len(stats.endpoint_times[ep])
            bar = _spark_bar(avg, ranked[0][1])
            print(f"  {c(Colors.DIM, str(i).rjust(2))}  {bar} {c(Colors.CYAN, f'{avg:7.1f}ms')}  {ep}  {c(Colors.DIM, f'({cnt} req)')}")
    else:
        print(c(Colors.DIM, "  (no response time data)"))

    print(f"\n{c(Colors.BOLD, '  STATUS CODE DISTRIBUTION')}\n{sep}")
    if stats.status_counts:
        total_req = sum(stats.status_counts.values())
        for code, count in sorted(stats.status_counts.items(), key=lambda x: -x[1]):
            pct = count / total_req * 100
            print(f"  {c(_status_color(code), code.rjust(7))}  {_bar(count, max(stats.status_counts.values()))} {c(Colors.DIM, f'{pct:5.1f}%')}  {count:,}")
    else:
        print(c(Colors.DIM, "  (no status code data)"))

    print(f"\n{c(Colors.BOLD, f'  TOP {top_n} IPs BY REQUEST COUNT')}\n{sep}")
    if stats.ip_counts:
        top_ips = sorted(stats.ip_counts.items(), key=lambda x: -x[1])[:top_n]
        mx = top_ips[0][1]
        for ip, cnt in top_ips:
            print(f"  {c(Colors.MAGENTA, ip.ljust(18))}  {_bar(cnt, mx)}  {cnt:,}")
    else:
        print(c(Colors.DIM, "  (no IP data)"))

    print(f"\n{c(Colors.BOLD, '  TRAFFIC BY HOUR (UTC)')}\n{sep}")
    if stats.hour_counts:
        mx = max(stats.hour_counts.values())
        for hour in range(24):
            cnt = stats.hour_counts.get(hour, 0)
            marker = c(Colors.YELLOW, "◀ peak") if cnt == mx and cnt > 0 else ""
            print(f"  {c(Colors.DIM, f'{hour:02d}:00')}  {_bar(cnt, mx, 20)}  {cnt:,}  {marker}")
    else:
        print(c(Colors.DIM, "  (no timestamp data)"))

    if stats.anomaly_counts:
        print(f"\n{c(Colors.BOLD, '  ANOMALY FLAGS')}\n{sep}")
        for anomaly, count in sorted(stats.anomaly_counts.items(), key=lambda x: -x[1]):
            icon = c(Colors.RED, "⚠") if count > 5 else c(Colors.YELLOW, "⚑")
            print(f"  {icon}  {anomaly.ljust(35)}  {count:,}")

    print(f"\n{sep2}\n")


def print_json_report(stats, filepath, top_n):
    total_counted = stats.valid_lines + stats.malformed_lines
    mal_pct = (stats.malformed_lines / total_counted * 100) if total_counted else 0.0
    avgs = {ep: {"avg_ms": round(sum(t)/len(t), 2), "requests": len(t)} for ep, t in stats.endpoint_times.items()}
    top_endpoints = sorted(avgs.items(), key=lambda x: -x[1]["avg_ms"])[:top_n]
    report = {
        "file": filepath,
        "summary": {"total_lines": stats.total_lines, "valid_lines": stats.valid_lines,
                    "malformed_lines": stats.malformed_lines, "blank_lines": stats.blank_lines,
                    "comment_lines": stats.comment_lines, "duplicate_lines": stats.duplicate_count,
                    "malformed_rate_pct": round(mal_pct, 2)},
        "slowest_endpoints": [{"endpoint": ep, **v} for ep, v in top_endpoints],
        "status_codes": dict(sorted(stats.status_counts.items())),
        "top_ips": dict(sorted(stats.ip_counts.items(), key=lambda x: -x[1])[:top_n]),
        "traffic_by_hour": {str(h): stats.hour_counts.get(h, 0) for h in range(24)},
        "anomalies": dict(sorted(stats.anomaly_counts.items(), key=lambda x: -x[1])),
    }
    print(json.dumps(report, indent=2))


def analyze(filepath, top_n, output_json):
    if not os.path.exists(filepath):
        print(c(Colors.RED, f"Error: file not found: {filepath}"), file=sys.stderr)
        sys.exit(1)

    stats = Stats()
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                stats.total_lines += 1
                raw = raw_line.rstrip("\n\r")
                try:
                    rec, disposition = parse_line(raw, stats.total_lines)
                except Exception:
                    stats.malformed_lines += 1; continue
                if disposition == "blank": stats.blank_lines += 1
                elif disposition == "comment": stats.comment_lines += 1
                elif disposition == "malformed": stats.malformed_lines += 1
                elif disposition == "valid" and rec is not None:
                    stats.valid_lines += 1; stats.ingest(rec)
    except PermissionError:
        print(c(Colors.RED, f"Error: permission denied: {filepath}"), file=sys.stderr); sys.exit(1)
    except OSError as e:
        print(c(Colors.RED, f"Error reading file: {e}"), file=sys.stderr); sys.exit(1)

    if stats.total_lines == 0:
        print(c(Colors.YELLOW, f"No data: {filepath} is empty.")); sys.exit(0)

    if output_json: print_json_report(stats, filepath, top_n)
    else: print_report(stats, filepath, top_n)


def main():
    global _USE_COLOR
    parser = argparse.ArgumentParser(description="Analyze Apache/Nginx-style log files.")
    parser.add_argument("logfile")
    parser.add_argument("--top", "-t", type=int, default=5, metavar="N")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()
    if args.no_color or not sys.stdout.isatty(): _USE_COLOR = False
    analyze(args.logfile, args.top, args.json)

if __name__ == "__main__":
    main()
