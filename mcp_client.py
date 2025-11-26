"""
FleetMind MCP Client
Connects to the FleetMind MCP Server via SSE transport using official MCP SDK
Track 2: MCP in Action - Enterprise Category

Fixed for Gradio threading compatibility - uses fresh connections per request
"""

import json
import asyncio
import httpx
from typing import Any, Optional
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from mcp.client.sse import sse_client
from mcp import ClientSession


@dataclass
class MCPTool:
    """Represents an MCP tool"""
    name: str
    description: str
    parameters: dict = field(default_factory=dict)


@dataclass
class MCPResponse:
    """Response from MCP tool execution"""
    success: bool
    result: Any = None
    error: Optional[str] = None
    tool_name: Optional[str] = None


class FleetMindMCPClient:
    """
    MCP Client for FleetMind Server
    Uses official MCP SDK for fast, reliable SSE connections

    Thread-safe implementation that creates fresh connections for each operation
    to avoid anyio task group issues with Gradio's threading model.
    """

    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.tools: dict[str, MCPTool] = {}
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def _wake_up_space(self) -> bool:
        """Wake up HF space before connecting (free tier spaces sleep when inactive)"""
        print("Waking up HuggingFace space...")
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                # Try up to 5 times with increasing delays
                for attempt in range(5):
                    try:
                        print(f"  Wake-up attempt {attempt + 1}/5...")
                        # First hit the root endpoint
                        response = await client.get(f"{self.server_url}/")
                        if response.status_code == 200:
                            print(f"  Root endpoint responded OK")
                            # Also try the health/status endpoint if available
                            try:
                                health = await client.get(f"{self.server_url}/health", timeout=30.0)
                                print(f"  Health check: {health.status_code}")
                            except:
                                pass
                            # Wait a bit for full initialization
                            await asyncio.sleep(2)
                            return True
                    except httpx.TimeoutException:
                        print(f"  Attempt {attempt + 1} timed out, waiting...")
                        # Increasing delay between retries
                        await asyncio.sleep(3 + attempt * 2)
                        continue
                    except Exception as e:
                        print(f"  Attempt {attempt + 1} error: {e}")
                        await asyncio.sleep(3 + attempt * 2)
                        continue
            print("  Wake-up failed after all attempts")
            return False
        except Exception as e:
            print(f"  Wake-up exception: {e}")
            return False

    @asynccontextmanager
    async def _get_session(self):
        """Create a fresh MCP session for each operation (thread-safe)"""
        sse_url = f"{self.server_url}/sse?api_key={self.api_key}"

        # Increased timeouts for cold-start scenarios
        async with sse_client(sse_url, timeout=120.0, sse_read_timeout=300.0) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def connect(self) -> dict:
        """
        Initialize connection to MCP server and discover tools
        Uses official MCP SDK SSE client for fast connection

        Includes retry logic for cold-start scenarios on HuggingFace
        """
        try:
            # First wake up HF space (free tier spaces sleep when inactive)
            wake_up_success = await self._wake_up_space()
            if not wake_up_success:
                print("Warning: Space wake-up may have failed, trying to connect anyway...")

            # Retry connection up to 3 times
            last_error = None
            for attempt in range(3):
                try:
                    print(f"Connecting to MCP server (attempt {attempt + 1}/3)...")

                    # Create a temporary session just to discover tools
                    async with self._get_session() as session:
                        # Discover tools
                        tools_result = await session.list_tools()
                        for tool in tools_result.tools:
                            self.tools[tool.name] = MCPTool(
                                name=tool.name,
                                description=tool.description or "",
                                parameters=tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                            )

                    self._connected = True
                    print(f"Connected successfully! Found {len(self.tools)} tools.")

                    return {
                        "success": True,
                        "session_id": "mcp-sdk-session",
                        "tools_count": len(self.tools),
                        "tools": list(self.tools.keys())
                    }

                except Exception as e:
                    last_error = str(e)
                    print(f"Connection attempt {attempt + 1} failed: {e}")
                    if attempt < 2:
                        # Wait before retry with increasing delay
                        wait_time = 3 + attempt * 2
                        print(f"Retrying in {wait_time} seconds...")
                        await asyncio.sleep(wait_time)

            return {"success": False, "error": f"Failed after 3 attempts: {last_error}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def call_tool(self, tool_name: str, arguments: dict = None) -> MCPResponse:
        """
        Execute an MCP tool

        Creates a fresh connection for each tool call to avoid threading issues.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments as a dictionary

        Returns:
            MCPResponse with success status and result/error
        """
        if not self._connected:
            return MCPResponse(
                success=False,
                error="Not connected to MCP server. Call connect() first.",
                tool_name=tool_name
            )

        if tool_name not in self.tools:
            return MCPResponse(
                success=False,
                error=f"Tool '{tool_name}' not found. Available: {list(self.tools.keys())}",
                tool_name=tool_name
            )

        try:
            # Create a fresh session for this tool call (thread-safe)
            async with self._get_session() as session:
                result = await session.call_tool(tool_name, arguments or {})

                # Extract content from MCP response
                if result.content:
                    for content_item in result.content:
                        if hasattr(content_item, 'text'):
                            try:
                                parsed = json.loads(content_item.text)
                                return MCPResponse(
                                    success=True,
                                    result=parsed,
                                    tool_name=tool_name
                                )
                            except json.JSONDecodeError:
                                return MCPResponse(
                                    success=True,
                                    result=content_item.text,
                                    tool_name=tool_name
                                )

                return MCPResponse(
                    success=True,
                    result=str(result),
                    tool_name=tool_name
                )

        except Exception as e:
            return MCPResponse(
                success=False,
                error=str(e),
                tool_name=tool_name
            )

    def get_tool_info(self, tool_name: str) -> Optional[MCPTool]:
        """Get information about a specific tool"""
        return self.tools.get(tool_name)

    def list_tools(self) -> list[dict]:
        """List all available tools with their descriptions"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for tool in self.tools.values()
        ]

    async def disconnect(self):
        """Mark as disconnected (no persistent connection to close)"""
        self._connected = False
        self.tools = {}


# Direct tool execution without persistent connection
async def execute_tool_direct(
    server_url: str,
    api_key: str,
    tool_name: str,
    arguments: dict = None
) -> MCPResponse:
    """
    Execute a single tool call directly without maintaining a persistent connection.
    Useful for one-off tool executions.
    """
    client = FleetMindMCPClient(server_url, api_key)
    try:
        connect_result = await client.connect()
        if not connect_result.get("success"):
            return MCPResponse(
                success=False,
                error=connect_result.get("error", "Connection failed"),
                tool_name=tool_name
            )
        return await client.call_tool(tool_name, arguments)
    finally:
        await client.disconnect()
