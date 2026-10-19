"""
Lab Solution: Build a SQL Query Agent Against Your Day 1 RDS Schema

Uses the sample consulting-firm schema from the Day 1 RDS Setup lab:
clients, projects, consultants, invoices.

Calls Claude via Bedrock (see bedrock_client.py) rather than the direct
Anthropic SDK — students in this environment don't have direct Anthropic
API keys.
"""

import psycopg2
import os
from dotenv import load_dotenv
from bedrock_client import invoke_claude
load_dotenv()

# ── Part 1: Schema Context ──────────────────────────────────────────────────

SCHEMA_CONTEXT = """
Tables available:
- clients(id, name, industry, region, contract_value, created_date)
  - region is one of: 'North', 'South', 'East', 'West'
  - contract_value is in USD
- projects(id, client_id, name, status, start_date, end_date, budget)
  - status is one of: 'active', 'completed', 'on-hold'
  - budget is in USD
  - client_id references clients.id
- consultants(id, name, grade, specialisation, project_id, billable_hours)
  - grade is one of: 'Analyst', 'Senior', 'Manager', 'Director'
  - project_id references projects.id
- invoices(id, project_id, amount, status, due_date, paid_date)
  - status is one of: 'paid', 'pending', 'overdue'
  - amount is in USD
  - project_id references projects.id

All dates are in ISO 8601 format (YYYY-MM-DD).
"""


# ── Part 2: Query Generation ────────────────────────────────────────────────

def generate_sql(question: str) -> str:
    prompt = (
        f"{SCHEMA_CONTEXT}\n\n"
        f"Generate a SQL query to answer: {question}\n\n"
        "Return ONLY the SQL query. No explanation, no markdown, no backticks."
    )
    result = invoke_claude(prompt, max_tokens=512)
    sql = result["text"].strip()
    # Strip markdown code fences if Claude adds them despite instructions
    sql = sql.removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
    return sql


# ── Part 3: Query Execution (unsafe version — validation added in Lab 3) ──

def execute_query(sql: str) -> dict:
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
        return {"success": True, "columns": cols, "rows": rows}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Part 4: Full Agent ──────────────────────────────────────────────────────

def sql_agent(question: str) -> str:
    sql = generate_sql(question)
    result = execute_query(sql)

    if not result["success"]:
        return f"Query failed: {result['error']}\nGenerated SQL was: {sql}"

    prompt = (
        f"The user asked: {question}\n"
        f"SQL used: {sql}\n"
        f"Columns: {result['columns']}\n"
        f"Data: {result['rows'][:20]}\n\n"
        "Provide a clear, concise natural-language answer based on this data."
    )
    interpretation = invoke_claude(prompt, max_tokens=500)
    return interpretation["text"]


# ── Part 5: Agent with Memory ───────────────────────────────────────────────

def sql_agent_with_memory(question: str, history: list) -> tuple[str, list]:
    context_summary = "\n".join([f"Q: {h['question']}\nA: {h['answer']}" for h in history])

    sql_prompt = (
        f"{SCHEMA_CONTEXT}\n\n"
        f"Conversation so far:\n{context_summary}\n\n"
        f"New question (may refer back to the conversation above): {question}\n\n"
        "Generate ONLY a SQL query to answer the new question."
    )
    sql_result = invoke_claude(sql_prompt, max_tokens=512)
    sql = sql_result["text"].strip()
    sql = sql.removeprefix("```sql").removeprefix("```").removesuffix("```").strip()

    result = execute_query(sql)
    if not result["success"]:
        answer = f"Query failed: {result['error']}"
    else:
        answer_prompt = f"Question: {question}\nData: {result['rows'][:20]}\n\nAnswer concisely."
        answer_result = invoke_claude(answer_prompt, max_tokens=500)
        answer = answer_result["text"]

    history.append({"question": question, "answer": answer})
    return answer, history


# ── Test Suite: 8 Questions of Increasing Complexity ────────────────────────

if __name__ == "__main__":
    test_questions = [
        "How many clients do we have?",                                          # 1. simple count
        "What is Acme Corp's contract value?",                                   # 2. simple lookup
        "Which consultants are working on active projects?",                     # 3. requires join
        "What is the total budget across all active projects?",                  # 4. aggregation
        "Show me all invoices with status overdue",                              # 5. WHERE clause
        "What is the average billable hours per project, by project name?",      # 6. join + aggregation
        "Show me our best clients",                                              # 7. ambiguous on purpose
        "What is our current stock price?",                                      # 8. cannot be answered
    ]

    print("=" * 70)
    print("PART 4: Full Agent Test — 8 Questions")
    print("=" * 70)
    for q in test_questions:
        print(f"\nQ: {q}")
        print(f"A: {sql_agent(q)}")

    print("\n" + "=" * 70)
    print("PART 5: Memory Test — Follow-Up Question")
    print("=" * 70)
    history = []
    a1, history = sql_agent_with_memory("How many active projects does Acme Corp have?", history)
    print(f"\nQ1: How many active projects does Acme Corp have?\nA1: {a1}")

    a2, history = sql_agent_with_memory("What about their total contract value?", history)
    print(f"\nQ2: What about their total contract value?\nA2: {a2}")