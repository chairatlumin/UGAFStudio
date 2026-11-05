import json

from mcp.server import MCPServer

from tools.opencode_mcp.opencode_client import send_prompt

mcp = MCPServer("UGAFStudio QA Controller")


@mcp.tool()
def qa_analyze(
    target: str = "UGAFStudio",
    unreal_versions: str = "5.7,5.8",
) -> str:
    """
    Analyze QA automation readiness without modifying files.
    """

    prompt = f"""
You are the QA analysis agent for {target}.

Target Unreal Engine versions: {unreal_versions}

Perform a READ-ONLY analysis.

Do NOT:
- modify files
- create files
- delete files
- commit changes
- push changes
- perform destructive commands

Inspect the repository and report:

# QA ANALYSIS

## 1. Repository Architecture

## 2. Existing Testing

## 3. Existing Automation

## 4. Unreal 5.7 / 5.8 Readiness

## 5. Missing Capabilities

## 6. Risks

## 7. Recommended Next Phase

## 8. Exact Files Relevant to Next Phase

## 9. Final Recommendation

Use repository evidence.
Do not invent files, systems, tests, or capabilities.
Clearly distinguish confirmed findings from recommendations.
"""

    result = send_prompt(
        prompt=prompt,
        title="UGAFStudio QA Analysis",
        new_session=True,
        timeout_sec=60,
    )

    return json.dumps(
        result,
        ensure_ascii=False,
    )


if __name__ == "__main__":
    mcp.run()
