import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def main():
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "tools.opencode_mcp.qa_controller",
        ],
        cwd=PROJECT_ROOT,
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()

            print("=== QA CONTROLLER TOOLS ===")

            for tool in tools.tools:
                print(f"{tool.name}: {tool.description}")

            print()
            print("=== QA ANALYSIS ===")

            result = await session.call_tool(
                "qa_analyze",
                {
                    "target": "UGAFStudio",
                    "unreal_versions": "5.7,5.8",
                },
            )

            for content in result.content:
                if hasattr(content, "text"):
                    print(content.text)


if __name__ == "__main__":
    asyncio.run(main())
