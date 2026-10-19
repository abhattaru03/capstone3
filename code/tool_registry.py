"""
Day 3 Lab Solution: Connect SQL Agent and Retrieval Agent to a Shared Tool Registry

Standardizes both agents to a consistent interface, builds the registry,
and includes a simple routing-suggestion preview (deliberately limited -
see Part 4 notes on the combined-question test).
"""

import os
from dotenv import load_dotenv
from bedrock_client import invoke_claude
load_dotenv()

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


# ── Part 1: Standardized Agent Wrappers ─────────────────────────────────────
# These wrap the actual agent logic from Day 2 (sql_agent.py) and
# Day 3 (retrieval_agent_solution.py), reshaping their output into the
# shared {success, answer, sources, metadata} contract.

def run_sql_agent(question: str) -> dict:
    # Import here to avoid circular import issues in a real project structure.
    # Path is resolved relative to this file, not the current working
    # directory — sys.path.append("../add-validation-layer-lab") broke as
    # soon as this script was run from anywhere else. Also note the sibling
    # folder is named add-validation-layer-lab-solution here, not
    # add-validation-layer-lab — adjust if your own directory layout differs.
    import sys
    sys.path.append(os.path.join(_THIS_DIR, "..", "add-validation-layer-lab-solution"))
    from validated_agent import validated_sql_agent

    result = validated_sql_agent(question)
    return {
        "success": result["validation"] == "PASSED",
        "answer": result["answer"],
        "sources": [f"SQL: {result['sql']}"],
        "metadata": {"validation": result["validation"]}
    }


def run_retrieval_agent(question: str) -> dict:
    # Same CWD-relative bug as run_sql_agent above, fixed the same way.
    # This half needs an OpenSearch domain and its own retrieval_agent_solution.py
    # sibling file to actually run — out of scope for the Docker/local-Postgres
    # conversion this file otherwise received; not re-verified here.
    import sys
    sys.path.append(os.path.join(_THIS_DIR, "..", "build-a-retrieval-agent-lab"))
    from retrieval_agent import retrieval_agent, check_grounding

    result = retrieval_agent(question)
    # NOTE: always call check_grounding directly, rather than shortcutting to
    # False when chunks is empty. check_grounding already handles a
    # zero-citation refusal correctly ("I cannot find this information..."
    # with no chunks counts as grounded, matching the convention already
    # established in the retrieval agent lab's own test findings for its
    # unanswerable-question test case). A hardcoded False here would
    # contradict that and mark a correct refusal as "not grounded."
    grounded = check_grounding(result["answer"], result["chunks"])
    return {
        "success": len(result["chunks"]) > 0,
        "answer": result["answer"],
        "sources": result["sources"],
        "metadata": {"chunk_count": len(result["chunks"]), "grounded": grounded}
    }


# ── Part 2: Tool Registry ────────────────────────────────────────────────────

TOOL_REGISTRY = {
    "sql_agent": {
        "function": run_sql_agent,
        "schema": {
            "name": "sql_agent",
            "description": (
                "Query the relational database for structured, numeric, or categorical "
                "data about clients, projects, consultants, and invoices - counts, totals, "
                "statuses, and comparisons. Do not use for policy or procedural questions."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"]
            }
        }
    },
    "retrieval_agent": {
        "function": run_retrieval_agent,
        "schema": {
            "name": "retrieval_agent",
            "description": (
                "Search indexed documents for policy, procedure, and case study information - "
                "onboarding, expense guidelines, or project narratives. Do not use for "
                "structured numeric or database questions."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"]
            }
        }
    }
}


def get_all_schemas() -> list:
    return [tool["schema"] for tool in TOOL_REGISTRY.values()]


def call_tool(tool_name: str, question: str) -> dict:
    if tool_name not in TOOL_REGISTRY:
        return {"success": False, "answer": f"Unknown tool: {tool_name}", "sources": [], "metadata": {}}
    return TOOL_REGISTRY[tool_name]["function"](question)


# ── Part 4: Simple Routing Preview ──────────────────────────────────────────

def suggest_tool(question: str) -> str:
    schemas_description = "\n".join([f"- {s['name']}: {s['description']}" for s in get_all_schemas()])

    prompt = (
        f"Available tools:\n{schemas_description}\n\n"
        f"Question: {question}\n\n"
        "Which tool should handle this? Reply with only the tool name."
    )
    result = invoke_claude(prompt, max_tokens=20)
    return result["text"].strip()


if __name__ == "__main__":
    print("=" * 70)
    print("PART 3: Registry Direct Tests")
    print("=" * 70)
    print("Registered tools:", [s["name"] for s in get_all_schemas()])

    result1 = call_tool("sql_agent", "How many active projects do we have?")
    print("\nSQL agent test:", result1)

    result2 = call_tool("retrieval_agent", "What is our onboarding process?")
    print("\nRetrieval agent test:", result2)

    result3 = call_tool("nonexistent_tool", "test")
    print("\nUnknown tool test:", result3)

    print("\n" + "=" * 70)
    print("PART 4: Routing Suggestion Preview")
    print("=" * 70)
    for q in [
        "How many consultants do we have on active projects?",
        "What is our expense reimbursement policy?",
        "How many active projects do we have and what's our onboarding process?",
    ]:
        print(f"\nQ: {q}")
        print(f"Suggested tool: {suggest_tool(q)}")