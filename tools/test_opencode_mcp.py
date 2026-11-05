import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server = StdioServerParameters(
        command="python",
        args=["tools/opencode_mcp/server.py"],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()

            print("=== MCP TOOLS ===")

            for tool in tools.tools:
                print(f"{tool.name}: {tool.description}")

            print()
            print("=== OPENCODE SEND ===")

            result = await session.call_tool(
                "opencode_send",
                {"prompt": "ตอบเพียงคำว่า MCP_OPENCODE_OK"},
            )

            for content in result.content:
                if hasattr(content, "text"):
                    print(content.text)


if __name__ == "__main__":
    asyncio.run(main())
