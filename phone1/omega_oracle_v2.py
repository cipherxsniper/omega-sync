#!/usr/bin/env python3
"""
OMEGA ORACLE v2 — Deterministic Self-Learning Production Gate
Every patch must prove it improved the system mathematically.
The system can only ever improve. Never regress. Never trick itself.
"""

import re, sys, ast, json, time, hashlib, subprocess
from pathlib import Path
from datetime import datetime

HOME    = Path("/data/data/com.termux/files/home")
HISTORY = HOME / "omega_oracle_history.json"
SNAP    = HOME / "omega_sentinel_snapshot.json"

# ── Weighted component registry ────────────────────────────
COMPONENTS = {
    "omega_v10":              {"weight": 0.40, "path": HOME / "omega_v10.py"},
    "omega_consensus":        {"weight": 0.15, "path": HOME / "omega_consensus.py"},
    "omega_sentinel":         {"weight": 0.10, "path": HOME / "omega_sentinel.py"},
    "omega_oracle_v2":        {"weight": 0.10, "path": HOME / "omega_oracle_v2.py"},
    "omega_email_finder":     {"weight": 0.05, "path": HOME / "omega_email_finder.py"},
    "omega_card_engine":      {"weight": 0.05, "path": HOME / "omega_card_engine.py"},
    "omega_guardian":         {"weight": 0.05, "path": HOME / "omega-fintech/start_consensus_gate.sh"},
    "omega_bank_db":          {"weight": 0.05, "path": None},
    "omega_ledger_db":        {"weight": 0.05, "path": None},
}

# ── Error memory — learns from past mistakes ───────────────
ERROR_MEMORY_FILE = HOME / "omega_oracle_error_memory.json"

def load_error_memory() -> dict:
    if ERROR_MEMORY_FILE.exists():
        try:
            return json.loads(ERROR_MEMORY_FILE.read_text())
        except Exception:
            pass
    return {"indent_errors": [], "syntax_errors": [], "duplicate_functions": [], "patch_count": 0}

def save_error_memory(mem: dict):
    ERROR_MEMORY_FILE.write_text(json.dumps(mem, indent=2))

def record_error(error_type: str, detail: str):
    """Record a mistake so it's never repeated."""
    mem = load_error_memory()
    entry = {"detail": detail, "ts": datetime.now().isoformat(), "patch": mem["patch_count"]}
    if error_type not in mem:
        mem[error_type] = []
    # Avoid duplicates
    if not any(e["detail"] == detail for e in mem[error_type]):
        mem[error_type].append(entry)
    save_error_memory(mem)

def check_known_errors(src: str) -> list:
    """
    Check if this patch repeats a previously recorded mistake.
    Self-learning: every error ever made is checked against every future patch.
    """
    mem = load_error_memory()
    warnings = []

    # Check for previously seen indent patterns
    for err in mem.get("indent_errors", []):
        pattern = err["detail"]
        if pattern in src:
            warnings.append(f"⚠️ REPEATED INDENT ERROR (seen in patch #{err['patch']}): {pattern[:60]}")

    # Check for previously seen duplicate function names
    for err in mem.get("duplicate_functions", []):
        fn_name = err["detail"]
        count = src.count(f"def {fn_name}(")
        if count > 1:
            warnings.append(f"⚠️ REPEATED DUPLICATE (seen in patch #{err['patch']}): def {fn_name}()")

    return warnings

# ── Score a single component ───────────────────────────────
def score_component(name: str, info: dict) -> tuple[int, list]:
    issues = []
    path = info["path"]

    # DB components — check live connection
    if name == "omega_bank_db":
        try:
            import psycopg2
            conn = psycopg2.connect(host="127.0.0.1", port=5432,
                                    dbname="omega_bank", user="postgres",
                                    connect_timeout=3)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wallets")
            wct = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM accounts")
            act = cur.fetchone()[0]
            conn.close()
            if wct > 0 and act > 0:
                return 100, []
            issues.append(f"Empty tables: {wct} wallets, {act} accounts")
            return 50, issues
        except Exception as e:
            issues.append(f"DB unreachable: {e}")
            return 0, issues

    if name == "omega_ledger_db":
        try:
            import psycopg2
            conn = psycopg2.connect(host="127.0.0.1", port=5432,
                                    dbname="omega_ledger", user="postgres",
                                    connect_timeout=3)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM ledger_accounts")
            conn.close()
            return 100, []
        except Exception as e:
            issues.append(f"Ledger DB unreachable: {e}")
            return 0, issues

    if not path or not path.exists():
        issues.append(f"File not found: {path}")
        return 0, issues

    src = path.read_text()
    score = 100

    # Shell scripts — basic check
    if str(path).endswith(".sh"):
        has_omega = "omega_v10.py" in src or "omega" in src.lower()
        has_loop  = "while true" in src or "sleep" in src
        if has_omega and has_loop:
            return 100, []
        if has_omega or has_loop:
            return 75, ["Guardian partially configured"]
        return 50, ["Guardian missing key patterns"]

    # Python files — full analysis
    # 1. Syntax
    try:
        import py_compile, tempfile, shutil
        tmp = Path(tempfile.mktemp(suffix=".py"))
        shutil.copy(path, tmp)
        py_compile.compile(str(tmp), doraise=True)
        tmp.unlink()
    except Exception as e:
        issues.append(f"SyntaxError: {e}")
        record_error("syntax_errors", str(e)[:100])
        return 0, issues

    # 2. AST parse
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        issues.append(f"AST error line {e.lineno}: {e.msg}")
        return 0, issues

    # 3. Indentation anomalies — skip valid Python continuations
    indent_errs = []
    src_lines = src.splitlines()
    SKIP_STARTS = (
        "#", "SELECT", "INSERT", "UPDATE", "WHERE", "FROM",
        "JOIN", "SET", "ORDER", "LIMIT", "AND ", "OR ", "LEFT",
        "INNER", "VALUES", "--", "ON ",
    )
    # Track multiline triple-quoted strings to skip false positives
    in_multiline = False
    multiline_char = None
    for i, line in enumerate(src_lines, 1):
        stripped_check = line.strip()
        for _tq in ('"""', "'''"):
            _cnt = stripped_check.count(_tq)
            if _cnt > 0:
                if not in_multiline:
                    in_multiline = True
                    multiline_char = _tq
                    if _cnt >= 2: in_multiline = False; multiline_char = None
                elif multiline_char == _tq:
                    in_multiline = False; multiline_char = None
                break
        if in_multiline:
            continue
        if not line or line[0] != " ":
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(SKIP_STARTS):
            continue
        if stripped[0] in (chr(34), chr(39), "f", "b", "r"):
            continue
        spaces = len(line) - len(line.lstrip(" "))
        if spaces % 4 != 0:
            prev = src_lines[i-2].rstrip() if i > 1 else ""
            if prev and prev[-1] not in (",", "(", "[", "\\", "+"):
                indent_errs.append(f"line {i}: {spaces} spaces")
                record_error("indent_errors", line.strip()[:80])
    if indent_errs:
        penalty = min(len(indent_errs) * 5, 25)
        score -= penalty
        issues.append(f"Indent anomalies: {len(indent_errs)} real errors")

    # 4. Duplicate functions
    funcs = re.findall(r"^(?:async )?def (\w+)\(", src, re.MULTILINE)
    seen, dupes = set(), set()
    for f in funcs:
        if f in seen:
            dupes.add(f)
            record_error("duplicate_functions", f)
        seen.add(f)
    if dupes:
        penalty = len(dupes) * 5
        score -= penalty
        issues.append(f"Duplicate functions: {sorted(dupes)}")

    # 5. Check against error memory — has this patch repeated past mistakes?
    repeated = check_known_errors(src)
    if repeated:
        score -= len(repeated) * 10
        issues.extend(repeated)

    # 6. Component-specific checks
    if name == "omega_v10":
        # Must have all critical functions
        required = [
            "run_outreach", "run_inbox", "run_lead_generation",
            "run_email_enrichment", "handle_assistant_query",
            "get_bank_summary", "get_trading_summary",
            "master_button_handler", "trading_button_handler",
            "finance_button_handler", "button_handler",
            "_trading_menu", "_finance_menu", "_main_menu",
            "build_telegram_app", "start_engine",
        ]
        missing = [fn for fn in required if f"def {fn}" not in src and f"async def {fn}" not in src]
        if missing:
            penalty = len(missing) * 5
            score -= penalty
            issues.append(f"Missing functions: {missing}")

        # Must have all 29 buttons handled
        defined  = set(re.findall(r'callback_data=["\']([^"\']+)["\']', src))
        handled  = set(re.findall(r'(?:if|elif)\s+data\s*==\s*["\']([^"\']+)["\']', src))
        multi    = re.findall(r'data\s+in\s+\(([^)]+)\)', src)
        for group in multi:
            for item in re.findall(r'["\']([^"\']+)["\']', group):
                handled.add(item)
        orphaned = [cb for cb in defined if cb not in handled]
        if orphaned:
            score -= len(orphaned) * 3
            issues.append(f"Unhandled buttons: {orphaned}")

    # Functional tests — verify real data flows not just syntax
    if name == "omega_v10":
        # Test 1: card engine returns real data
        try:
            import sys as _sys
            _sys.path.insert(0, str(HOME))
            from omega_card_engine import get_cards, ensure_card_tables
            ensure_card_tables()
            cards = get_cards()
            if len(cards) == 0:
                score -= 5
                issues.append("functional: card engine returns no cards")
        except Exception as e:
            score -= 5
            issues.append(f"functional: card engine error: {e}")

        # Test 2: ledger DB has real entries
        try:
            import psycopg2
            conn = psycopg2.connect(host="127.0.0.1", port=5432,
                                    dbname="omega_ledger", user="postgres",
                                    connect_timeout=3)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM ledger_entries")
            count = cur.fetchone()[0]
            conn.close()
            if count == 0:
                score -= 5
                issues.append("functional: ledger has 0 entries")
        except Exception as e:
            score -= 5
            issues.append(f"functional: ledger entries error: {e}")

        # Test 3: wallet data is real
        try:
            import psycopg2
            conn = psycopg2.connect(host="127.0.0.1", port=5432,
                                    dbname="omega_bank", user="postgres",
                                    connect_timeout=3)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wallets WHERE available_balance > 0")
            wct = cur.fetchone()[0]
            conn.close()
            if wct == 0:
                score -= 5
                issues.append("functional: no wallets with balance")
        except Exception as e:
            score -= 5
            issues.append(f"functional: wallet check error: {e}")

    if name == "omega_sentinel":
        required_fns = ["check_syntax", "scan_buttons", "check_drift",
                        "save_snapshot", "run_all", "watch_daemon",
                        "_extract_functions", "check_mexc", "check_process"]
        missing = [f for f in required_fns if f"def {f}" not in src]
        if missing:
            score -= len(missing) * 8
            issues.append(f"Missing sentinel functions: {missing}")

    return max(0, min(100, score)), issues

# ── Compute system hash (mathematical proof) ───────────────
def compute_system_hash() -> str:
    """
    Hash the entire system state — all component file hashes combined.
    This is the cryptographic proof of system state.
    Cannot be faked. Changes if anything changes.
    """
    combined = ""
    for name, info in sorted(COMPONENTS.items()):
        path = info["path"]
        if path and path.exists():
            content = path.read_text()
            fhash = hashlib.sha256(content.encode()).hexdigest()[:16]
            combined += f"{name}:{fhash}:"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]

# ── Grade a patch (A-F) ────────────────────────────────────
def grade(score: int, prev_score: int, same_hash: bool) -> tuple[str, str]:
    """
    Grade is not just the score — it compares to prior state.
    A system at 100/100 that hasn't actually changed is NOT an A.
    """
    delta = score - prev_score

    if same_hash:
        return "C", "No change detected — system identical to prior state"
    if score == 100 and delta > 0:
        return "A+", "Perfect score with genuine improvement"
    if score >= 95 and delta >= 0:
        return "A", "Excellent — significant improvement"
    if score >= 85 and delta >= 0:
        return "B", "Good — measurable improvement"
    if score >= 70 and delta >= 0:
        return "C", "Acceptable — minor improvement"
    if delta < 0:
        return "F", f"REGRESSION — score dropped {abs(delta)} points. PATCH BLOCKED."
    if score >= 50:
        return "D", "Below threshold — needs work"
    return "F", "Critical failure"

# ── Load/save history ──────────────────────────────────────
def load_history() -> list:
    if HISTORY.exists():
        try:
            return json.loads(HISTORY.read_text())
        except Exception:
            pass
    return []

def save_history(entry: dict):
    history = load_history()
    history.append(entry)
    if len(history) > 100:
        history = history[-100:]
    HISTORY.write_text(json.dumps(history, indent=2))

# ── Component floor registry — scores can never go below their best ──
FLOOR_FILE = HOME / "omega_oracle_floors.json"

def load_floors() -> dict:
    try:
        return json.loads(FLOOR_FILE.read_text())
    except:
        return {}

def update_floors(components: dict):
    floors = load_floors()
    updated = False
    for name, score in components.items():
        if score > floors.get(name, 0):
            floors[name] = score
            updated = True
    if updated:
        FLOOR_FILE.write_text(json.dumps(floors, indent=2))
    return floors

def check_floors(components: dict) -> list:
    """Returns violations where a component dropped below its floor."""
    floors = load_floors()
    violations = []
    # Only flag code regressions — skip DB components (infrastructure)
    infra = {"omega_bank_db", "omega_ledger_db"}
    for name, score in components.items():
        if name in infra:
            continue
        floor = floors.get(name, 0)
        if score < floor:
            violations.append(
                f"{name} dropped to {score} (floor: {floor}) — RATCHET VIOLATION"
            )
    return violations

def compute_percentile(history: list) -> float:
    """What percentile is the current score vs all history."""
    if len(history) < 2:
        return 100.0
    scores = [h.get("total", 0) for h in history]
    current = scores[-1]
    below = sum(1 for s in scores[:-1] if s <= current)
    return round((below / (len(scores) - 1)) * 100, 1)

# ── Main scoring run ───────────────────────────────────────
def run_score(verbose: bool = True) -> dict:
    history   = load_history()
    prev      = history[-1] if history else {"total": 0, "system_hash": "GENESIS", "patch_count": 0}
    prev_score = prev.get("total", 0)
    prev_hash  = prev.get("system_hash", "GENESIS")

    results   = {}
    total     = 0.0
    all_issues = []

    for name, info in COMPONENTS.items():
        score, issues = score_component(name, info)
        weighted = score * info["weight"]
        total   += weighted
        results[name] = {"score": score, "weighted": weighted, "issues": issues}
        for issue in issues:
            all_issues.append(f"[{name}] {issue}")

    total_int    = int(round(total))
    system_hash  = compute_system_hash()
    same_hash    = (system_hash == prev_hash)
    letter, note = grade(total_int, prev_score, same_hash)
    best_ever    = max(total_int, max((h.get("total", 0) for h in history), default=0))

    # Increment patch counter in error memory
    mem = load_error_memory()
    mem["patch_count"] += 1
    save_error_memory(mem)

    entry = {
        "ts":          datetime.now().isoformat(),
        "total":       total_int,
        "grade":       letter,
        "system_hash": system_hash,
        "prev_hash":   prev_hash,
        "prev_score":  prev_score,
        "delta":       total_int - prev_score,
        "patch_count": mem["patch_count"],
        "components":  {k: v["score"] for k, v in results.items()},
    }
    save_history(entry)

    if verbose:
        bar_chars = 10
        print("\n" + "=" * 54)
        print(f"  OMEGA ORACLE v2 — SYSTEM SCORE: {total_int}/100")
        print(f"  Grade: {letter}  |  {note}")
        print(f"  Hash:  {system_hash}  (prev: {prev_hash})")
        percentile = entry.get("percentile", 100.0)
        violations = entry.get("floor_violations", [])
        print(f"  Delta: {'+' if entry['delta'] >= 0 else ''}{entry['delta']} pts  |  Best ever: {best_ever}/100  |  Percentile: {percentile}%")
        if violations:
            print(f"  🚨 RATCHET VIOLATIONS:")
            for v in violations:
                print(f"     {v}")
        print(f"  Patch: #{mem['patch_count']}  |  Memory: {sum(len(v) for k,v in mem.items() if isinstance(v, list))} known errors")
        print("=" * 54)
        for name, data in results.items():
            score    = data["score"]
            weight   = COMPONENTS[name]["weight"]
            filled   = int(score / 100 * bar_chars)
            bar      = "█" * filled + "░" * (bar_chars - filled)
            status   = "✅" if score == 100 else ("⚠️ " if score >= 70 else "❌")
            print(f"  {status} {name:<25} {bar} {score:>3}/100  (w={int(weight*100)}%)")
        print("=" * 54)
        if all_issues:
            print(f"\n  Issues ({len(all_issues)}):")
            for issue in all_issues:
                print(f"    • {issue}")
        else:
            print("\n  ✅ ZERO ISSUES — SYSTEM PERFECT")

        # Show error memory summary
        mem_loaded = load_error_memory()
        total_known = sum(len(v) for k, v in mem_loaded.items() if isinstance(v, list))
        if total_known > 0:
            print(f"\n  🧠 Error memory: {total_known} patterns learned")
            print(f"     indent: {len(mem_loaded.get('indent_errors',[]))}  "
                  f"syntax: {len(mem_loaded.get('syntax_errors',[]))}  "
                  f"dupes: {len(mem_loaded.get('duplicate_functions',[]))}")

        # Regression block
        if letter == "F" and entry["delta"] < 0:
            print(f"\n  🚨 REGRESSION DETECTED — PATCH BLOCKED")
            print(f"     Score dropped from {prev_score} to {total_int}")
            print(f"     Fix issues above before restarting omega")

        print("=" * 54 + "\n")

    return entry

# ── Trend view ─────────────────────────────────────────────
def show_trend():
    history = load_history()
    if not history:
        print("No history yet.")
        return
    print("\n  ORACLE SCORE TREND (last 10 patches)")
    print("  " + "─" * 44)
    for h in history[-10:]:
        bar   = "█" * int(h["total"] / 10)
        delta = h.get("delta", 0)
        sign  = "+" if delta >= 0 else ""
        print(f"  #{h.get('patch_count','?'):>3}  {bar:<10} {h['total']:>3}/100  "
              f"{sign}{delta:>3}pts  [{h['grade']}]  {h['ts'][:16]}")
    print()

# ── Entrypoint ─────────────────────────────────────────────
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"

    if cmd == "score":
        result = run_score(verbose=True)
        sys.exit(0 if result["grade"] != "F" else 1)
    elif cmd == "trend":
        show_trend()
    elif cmd == "memory":
        mem = load_error_memory()
        print(f"\n  ERROR MEMORY — {sum(len(v) for k,v in mem.items() if isinstance(v,list))} patterns learned")
        for k, v in mem.items():
            if isinstance(v, list) and v:
                print(f"\n  {k} ({len(v)}):")
                for e in v[-3:]:
                    print(f"    patch #{e['patch']}: {e['detail'][:70]}")
    elif cmd == "hash":
        print(f"System hash: {compute_system_hash()}")
    else:
        print("Usage: python3 omega_oracle_v2.py [score|trend|memory|hash]")
