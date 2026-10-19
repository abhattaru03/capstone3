"""
Day 1 Lab Solution: RDS Setup and Schema Design

Full reference schema for a consulting-firm database, including
agent-readable schema documentation, table creation, and sample data.
This is the schema used consistently across Week 3's SQL agent labs.
"""

import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()


def get_connection():
    return psycopg2.connect(
        host=os.getenv("RDS_HOST"), port=os.getenv("RDS_PORT"),
        dbname=os.getenv("RDS_DATABASE"), user=os.getenv("RDS_USER"),
        password=os.getenv("RDS_PASSWORD")
    )


# ── Part 3: Agent-Readable Schema Documentation ─────────────────────────────
# This is the deliverable that matters most — write this BEFORE creating
# tables, and it becomes the SCHEMA_CONTEXT used by every SQL agent lab
# for the rest of the week.

SCHEMA_DOCUMENTATION = """
clients table:
- id (integer, primary key)
- name (text) — client organization name
- industry (text) — client's industry sector (e.g., 'Retail', 'Finance', 'Healthcare')
- region (text) — geographic region, one of: 'North', 'South', 'East', 'West'
- contract_value (numeric) — total contract value in USD
- created_date (date) — date the client relationship began, format YYYY-MM-DD

projects table:
- id (integer, primary key)
- client_id (integer) — foreign key referencing clients.id
- name (text) — project name
- status (text) — one of: 'active', 'completed', 'on-hold'
- start_date (date) — project start date, format YYYY-MM-DD
- end_date (date) — project end date, format YYYY-MM-DD (null if ongoing)
- budget (numeric) — total project budget in USD

consultants table:
- id (integer, primary key)
- name (text) — consultant full name
- grade (text) — one of: 'Analyst', 'Senior', 'Manager', 'Director'
- specialisation (text) — area of expertise (e.g., 'Data Engineering', 'Strategy')
- project_id (integer) — foreign key referencing projects.id
- billable_hours (numeric) — total billable hours logged on this project

invoices table:
- id (integer, primary key)
- project_id (integer) — foreign key referencing projects.id
- amount (numeric) — invoice amount in USD
- status (text) — one of: 'paid', 'pending', 'overdue'
- due_date (date) — payment due date, format YYYY-MM-DD
- paid_date (date) — date payment was received, format YYYY-MM-DD (null if unpaid)
"""


# ── Part 4: Table Creation ───────────────────────────────────────────────────

def create_tables():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            industry TEXT,
            region TEXT,
            contract_value NUMERIC,
            created_date DATE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            client_id INTEGER REFERENCES clients(id),
            name TEXT NOT NULL,
            status TEXT,
            start_date DATE,
            end_date DATE,
            budget NUMERIC
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS consultants (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            grade TEXT,
            specialisation TEXT,
            project_id INTEGER REFERENCES projects(id),
            billable_hours NUMERIC
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id),
            amount NUMERIC,
            status TEXT,
            due_date DATE,
            paid_date DATE
        )
    """)

    conn.commit()
    conn.close()
    print("Tables created successfully")


# ── Part 5: Sample Data ──────────────────────────────────────────────────────
#
# NOTE: This function is guarded against re-runs. Since this exact dataset
# is the reference SCHEMA_CONTEXT reused across Week 3's SQL agent labs,
# accidentally running this script twice (e.g., during troubleshooting)
# would otherwise silently double every row with no error — which would
# corrupt the reference dataset that later labs depend on producing
# predictable query results against.

def populate_sample_data():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM clients")
    existing_count = cur.fetchone()[0]
    if existing_count > 0:
        print(f"Sample data already present ({existing_count} clients found) — skipping insert.")
        print("If you want to reload from scratch, truncate all four tables first.")
        conn.close()
        return

    cur.execute("""
        INSERT INTO clients (name, industry, region, contract_value, created_date) VALUES
        ('Acme Corp', 'Retail', 'North', 250000, '2025-01-15'),
        ('Beta Financial', 'Finance', 'East', 480000, '2025-03-01'),
        ('Gamma Health', 'Healthcare', 'South', 320000, '2025-02-10'),
        ('Delta Manufacturing', 'Manufacturing', 'West', 190000, '2025-04-05'),
        ('Epsilon Retail', 'Retail', 'North', 275000, '2025-05-20')
    """)

    cur.execute("""
        INSERT INTO projects (client_id, name, status, start_date, end_date, budget) VALUES
        (1, 'Client Portal Redesign', 'active', '2025-02-01', NULL, 150000),
        (1, 'Data Migration', 'completed', '2025-01-20', '2025-03-15', 90000),
        (2, 'Fraud Detection System', 'active', '2025-03-10', NULL, 220000),
        (3, 'Patient Records Modernization', 'on-hold', '2025-02-15', NULL, 180000),
        (4, 'Supply Chain Analytics', 'active', '2025-04-10', NULL, 130000),
        (5, 'Inventory Management Overhaul', 'active', '2025-05-25', NULL, 160000)
    """)

    cur.execute("""
        INSERT INTO consultants (name, grade, specialisation, project_id, billable_hours) VALUES
        ('Alice Chen', 'Senior', 'Frontend Engineering', 1, 320),
        ('Bob Martinez', 'Manager', 'Data Engineering', 2, 210),
        ('Carol White', 'Analyst', 'Data Science', 3, 180),
        ('Dana Okafor', 'Senior', 'Healthcare Systems', 4, 95),
        ('Evan Park', 'Manager', 'Analytics', 5, 240),
        ('Fiona Reyes', 'Director', 'Strategy', 6, 150)
    """)

    # NOTE: originally missing an invoice for project_id=6 (Inventory
    # Management Overhaul). With INNER JOINs throughout
    # verify_relationships(), that gap silently dropped Epsilon Retail —
    # its only project, and Fiona Reyes as its only consultant — from the
    # verification query entirely, with no error and no visible sign
    # anything was wrong. Added the missing invoice below so all 5
    # clients genuinely appear in the join, which is what the check is
    # actually supposed to confirm.
    cur.execute("""
        INSERT INTO invoices (project_id, amount, status, due_date, paid_date) VALUES
        (1, 45000, 'paid', '2025-03-01', '2025-02-28'),
        (1, 45000, 'pending', '2025-05-01', NULL),
        (2, 90000, 'paid', '2025-03-20', '2025-03-18'),
        (3, 55000, 'overdue', '2025-04-01', NULL),
        (4, 45000, 'pending', '2025-05-15', NULL),
        (5, 32500, 'paid', '2025-05-01', '2025-04-29'),
        (6, 58000, 'pending', '2025-06-01', NULL)
    """)

    conn.commit()
    conn.close()
    print("Sample data inserted successfully")


# ── Part 5 Check: Join Query Across All Four Tables ─────────────────────────

def verify_relationships():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.name AS client, p.name AS project, con.name AS consultant, i.amount
        FROM clients c
        JOIN projects p ON p.client_id = c.id
        JOIN consultants con ON con.project_id = p.id
        JOIN invoices i ON i.project_id = p.id
        ORDER BY c.name;
    """)
    rows = cur.fetchall()
    conn.close()

    distinct_clients = sorted(set(row[0] for row in rows))
    print(f"Rows returned: {len(rows)}")
    print(f"Distinct clients represented: {len(distinct_clients)} — {distinct_clients}")
    for row in rows:
        print(row)
    return rows


if __name__ == "__main__":
    create_tables()
    populate_sample_data()
    print("\n--- Verifying relationships ---")
    verify_relationships()