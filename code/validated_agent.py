"""
Lab Solution: Add a Validation Layer Between Query Generation and Execution
"""

import psycopg2
import os
from dotenv import load_dotenv
from bedrock_client import invoke_claude
load_dotenv()

SCHEMA_CONTEXT = """
Tables available:
- clients(id, name, industry, region, contract_value, created_date)
- projects(id, client_id, name, status, start_date, end_date, budget)
- consultants(id, name, grade, specialisation, project_id, billable_hours)
- invoices(id, project_id, amount, status, due_date, paid_date)

status in projects is one of: 'active', 'completed', 'on-hold'.
status in invoices is one of: 'paid', 'pending', 'overdue'.
All monetary values are in USD.
"""


# ── Part 1: Validator ────────────────────────────────────────────────────────

BLOCKED_KEYWORDS = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
                    "EXEC", "EXECUTE", "GRANT", "REVOKE"]


def validate_sql(query: str) -> dict:
    """
    Validates a Claude-generated SQL query before execution.
    Blocks any query that is not a SELECT or contains destructive keywords.
    Uses word-boundary matching to avoid false positives on column names
    like 'deleted_at'.
    """
    query_upper = query.upper().strip()
    padded = f" {query_upper} "

    for keyword in BLOCKED_KEYWORDS:
        if f" {keyword} " in padded or query_upper.startswith(keyword + " ") or query_upper == keyword:
            return {
                "valid": False,
                "reason": f"Blocked: '{keyword}' is not permitted. Only SELECT queries are allowed."
            }

    if not query_upper.startswith("SELECT"):
        return {
            "valid": False,
            "reason": "Only SELECT queries are permitted. Query must begin with SELECT."
        }

    # Block stacked queries (multiple statements separated by semicolons)
    # A single trailing semicolon is fine; anything after it is not.
    stripped = query.strip().rstrip(";")
    if ";" in stripped:
        return {
            "valid": False,
            "reason": "Blocked: multiple statements detected (possible stacked query attempt)."
        }

    return {"valid": True, "reason": "OK"}


# ── Part 2: Test Suite ───────────────────────────────────────────────────────
#
# NOTE: the original stacked-query test case
# ("SELECT * FROM projects; DROP TABLE clients;") is blocked by the
# BLOCKED_KEYWORDS check (it contains "DROP") before the code ever reaches
# the dedicated semicolon/stacking check — verified directly by running
# validate_sql() on it in isolation. That means the semicolon-detection
# logic itself was never actually exercised by this test suite; a bug in
# just that logic could have shipped undetected. Added a stacked query
# using only harmless keywords, which does hit the semicolon check
# specifically, plus a single-trailing-semicolon case to confirm that
# documented "one trailing semicolon is fine" behavior actually holds.

TEST_CASES = [
    ("SELECT * FROM clients WHERE region = 'North'", True),
    ("select count(*) from projects", True),
    ("SELECT name, contract_value FROM clients ORDER BY contract_value DESC LIMIT 5", True),
    ("DROP TABLE clients", False),
    ("DELETE FROM projects WHERE status = 'active'", False),
    ("UPDATE consultants SET grade = 'Senior'", False),
    ("INSERT INTO invoices VALUES (1, 100, 'paid')", False),
    ("SELECT * FROM projects; DROP TABLE clients;", False),
    ("SeLeCt * FrOm clients", True),          # mixed case, still valid SELECT
    ("SELECT deleted_at FROM projects", True), # column name contains 'delete' but isn't the keyword
    ("SELECT * FROM projects; SELECT * FROM clients", False),  # stacked query, no blocked keyword —
                                                                # this is the one that actually proves
                                                                # the semicolon check works on its own
    ("SELECT * FROM clients;", True),          # single trailing semicolon should still be valid
]


def run_test_suite():
    print("=" * 70)
    print("VALIDATOR TEST SUITE")
    print("=" * 70)
    all_passed = True
    for query, expected in TEST_CASES:
        result = validate_sql(query)
        passed = result["valid"] == expected
        all_passed = all_passed and passed
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] valid={result['valid']} (expected {expected}) | {query[:60]}")
    print(f"\nAll tests passed: {all_passed}")
    return all_passed


# ── Part 3: Wired-In Validated Agent ─────────────────────────────────────────

def generate_sql(question: str) -> str:
    prompt = (
        f"{SCHEMA_CONTEXT}\n\n"
        f"Generate a SQL query to answer: {question}\n\n"
        "Return ONLY the SQL query. No explanation, no markdown, no backticks."
    )
    result = invoke_claude(prompt, max_tokens=512)
    sql = result["text"].strip()
    return sql.removeprefix("```sql").removeprefix("```").removesuffix("```").strip()


def execute_query_safely(sql: str) -> dict:
    validation = validate_sql(sql)

    if not validation["valid"]:
        return {
            "success": False,
            "error": validation["reason"],
            "validation": "BLOCKED",
            "sql": sql
        }

    try:
        conn = psycopg2.connect(
            host=os.getenv("RDS_HOST"), port=int(os.getenv("RDS_PORT")),
            dbname=os.getenv("RDS_DATABASE"), user=os.getenv("RDS_USER"),
            password=os.getenv("RDS_PASSWORD")
        )
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        conn.close()
        return {
            "success": True, "columns": cols, "rows": rows,
            "validation": "PASSED", "sql": sql
        }
    except Exception as e:
        return {"success": False, "error": str(e), "validation": "EXECUTION_ERROR", "sql": sql}


def validated_sql_agent(question: str) -> dict:
    sql = generate_sql(question)
    result = execute_query_safely(sql)

    if not result["success"]:
        return {
            "answer": f"Query blocked or failed: {result['error']}",
            "sql": sql,
            "validation": result["validation"]
        }

    prompt = (
        f"Question: {question}\nColumns: {result['columns']}\n"
        f"Data: {result['rows'][:20]}\n\nAnswer concisely."
    )
    interpretation = invoke_claude(prompt, max_tokens=500)

    return {"answer": interpretation["text"], "sql": sql, "validation": result["validation"]}


if __name__ == "__main__":
    run_test_suite()

    print("\n" + "=" * 70)
    print("RE-TESTING LAB 2 FAILURE MODES AGAINST THE VALIDATED AGENT")
    print("=" * 70)

    # NOTE: the two "direct attempt" rows below (DROP and the stacked query)
    # were originally re-tested by passing the malicious string as the
    # natural-language *question* to validated_sql_agent(), e.g.
    # validated_sql_agent("DROP TABLE clients"). That doesn't actually test
    # the validator: Claude refuses to generate destructive SQL from that
    # prompt and instead returns a harmless SELECT of its own, so
    # validate_sql() never sees a DROP or a stacked query at all — verified
    # directly (generate_sql("DROP TABLE clients") produced
    # "SELECT 'This request is not allowed...' AS error_message;", which
    # validate_sql() correctly marked valid, because it *is* valid). The
    # findings table's claim that these were "blocked by the validator" was
    # therefore wrong — the real blocker was Claude's own alignment at the
    # generation step, not this lab's validation layer, and the two were
    # never actually distinguished.
    #
    # To genuinely test whether the validator blocks a destructive query
    # reaching the database, the malicious SQL needs to go straight to
    # execute_query_safely() — simulating the real threat model (Claude
    # eventually *does* generate something destructive) rather than asking
    # Claude in English to do something it already refuses to do.
    ambiguous_questions = [
        "Which client is our best client?",              # #1 — ambiguous, not a validation problem
        "Which projects started recently?",               # #2 — ambiguous, not a validation problem
        "What's the status of things?",                   # #3 — ambiguous, not a validation problem
        "Show me everything",                             # #6 — unbounded, not caught by SQL validation alone
    ]
    for q in ambiguous_questions:
        result = validated_sql_agent(q)
        print(f"\nQ: {q}")
        print(f"Validation: {result['validation']}")
        print(f"Answer: {result['answer']}")

    direct_attacks = [
        "DROP TABLE clients",                             # direct attempt — should be blocked
        "SELECT * FROM projects; DROP TABLE clients;",    # stacked query attempt — should be blocked
    ]
    for sql in direct_attacks:
        result = execute_query_safely(sql)
        print(f"\nSQL fed directly to execute_query_safely(): {sql!r}")
        print(f"Validation: {result['validation']}")
        print(f"Error/result: {result.get('error', result.get('rows'))}")

    print("\n" + "=" * 70)
    print("CONFIRMING LEGITIMATE QUESTIONS STILL WORK")
    print("=" * 70)
    legit_questions = [
        "How many active projects do we have?",
        "What is the total contract value across all clients?",
    ]
    for q in legit_questions:
        result = validated_sql_agent(q)
        print(f"\nQ: {q}")
        print(f"Validation: {result['validation']}")
        print(f"Answer: {result['answer']}")

        