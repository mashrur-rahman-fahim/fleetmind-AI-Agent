"""
FleetMind MCP Client
Connects to the FleetMind MCP Server via SSE transport
Track 2: MCP in Action - Enterprise Category
"""

import json
import uuid
import asyncio
from typing import Any, Optional
from dataclasses import dataclass, field

import httpx


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
    Connects via SSE and executes tools
    """

    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.session_id: Optional[str] = None
        self.tools: dict[str, MCPTool] = {}
        self._client: Optional[httpx.AsyncClient] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.session_id is not None

    async def connect(self) -> dict:
        """
        Initialize connection to MCP server and discover tools
        Returns connection status and available tools
        """
        try:
            self._client = httpx.AsyncClient(timeout=30.0)

            # Initialize SSE connection to get session ID
            sse_url = f"{self.server_url}/sse?api_key={self.api_key}"

            async with self._client.stream("GET", sse_url) as response:
                if response.status_code != 200:
                    return {
                        "success": False,
                        "error": f"Failed to connect: HTTP {response.status_code}"
                    }

                # Read the first few events to get session info
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            try:
                                event_data = json.loads(data)
                                if "endpoint" in str(event_data):
                                    # Extract session ID from endpoint
                                    endpoint = event_data.get("endpoint", "")
                                    if "session_id=" in endpoint:
                                        self.session_id = endpoint.split("session_id=")[-1]
                                        break
                            except json.JSONDecodeError:
                                continue

            # If we got a session, discover tools
            if self.session_id:
                await self._discover_tools()
                self._connected = True
                return {
                    "success": True,
                    "session_id": self.session_id,
                    "tools_count": len(self.tools),
                    "tools": list(self.tools.keys())
                }

            return {
                "success": False,
                "error": "Could not establish session"
            }

        except httpx.TimeoutException:
            return {"success": False, "error": "Connection timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _discover_tools(self):
        """Discover available tools from the MCP server"""
        # Send tools/list request
        result = await self._send_request("tools/list", {})
        if result.get("tools"):
            for tool in result["tools"]:
                self.tools[tool["name"]] = MCPTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=tool.get("inputSchema", {})
                )

    async def _send_request(self, method: str, params: dict) -> dict:
        """Send JSON-RPC request to MCP server"""
        if not self._client:
            return {"error": "Not connected"}

        message_url = f"{self.server_url}/messages/?session_id={self.session_id}&api_key={self.api_key}"

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }

        try:
            response = await self._client.post(
                message_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                return response.json().get("result", {})
            elif response.status_code == 202:
                # Accepted - need to poll for result via SSE
                return await self._poll_for_result(request_id)
            else:
                return {"error": f"HTTP {response.status_code}: {response.text}"}

        except Exception as e:
            return {"error": str(e)}

    async def _poll_for_result(self, request_id: str, timeout: float = 30.0) -> dict:
        """Poll SSE stream for the result of an async request"""
        sse_url = f"{self.server_url}/sse?api_key={self.api_key}&session_id={self.session_id}"

        try:
            async with asyncio.timeout(timeout):
                async with self._client.stream("GET", sse_url) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data:
                                try:
                                    event_data = json.loads(data)
                                    if event_data.get("id") == request_id:
                                        return event_data.get("result", {})
                                except json.JSONDecodeError:
                                    continue
        except asyncio.TimeoutError:
            return {"error": "Request timeout"}

        return {"error": "No result received"}

    async def call_tool(self, tool_name: str, arguments: dict = None) -> MCPResponse:
        """
        Execute an MCP tool

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments as a dictionary

        Returns:
            MCPResponse with success status and result/error
        """
        if not self.is_connected:
            return MCPResponse(
                success=False,
                error="Not connected to MCP server",
                tool_name=tool_name
            )

        if tool_name not in self.tools:
            return MCPResponse(
                success=False,
                error=f"Tool '{tool_name}' not found. Available: {list(self.tools.keys())}",
                tool_name=tool_name
            )

        try:
            result = await self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments or {}
            })

            if "error" in result:
                return MCPResponse(
                    success=False,
                    error=result["error"],
                    tool_name=tool_name
                )

            # Extract content from MCP response
            content = result.get("content", [])
            if content and isinstance(content, list):
                # Get the text content
                text_content = next(
                    (c.get("text") for c in content if c.get("type") == "text"),
                    None
                )
                if text_content:
                    try:
                        # Parse JSON result
                        parsed = json.loads(text_content)
                        return MCPResponse(
                            success=True,
                            result=parsed,
                            tool_name=tool_name
                        )
                    except json.JSONDecodeError:
                        return MCPResponse(
                            success=True,
                            result=text_content,
                            tool_name=tool_name
                        )

            return MCPResponse(
                success=True,
                result=result,
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
        """Close the connection"""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False
        self.session_id = None


# Synchronous wrapper for simpler usage
class SyncMCPClient:
    """Synchronous wrapper for FleetMindMCPClient"""

    def __init__(self, server_url: str, api_key: str):
        self._async_client = FleetMindMCPClient(server_url, api_key)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self):
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
            return self._loop

    def _run(self, coro):
        loop = self._get_loop()
        if loop.is_running():
            # If we're in an async context, create a task
            return asyncio.ensure_future(coro)
        return loop.run_until_complete(coro)

    def connect(self) -> dict:
        return self._run(self._async_client.connect())

    def call_tool(self, tool_name: str, arguments: dict = None) -> MCPResponse:
        return self._run(self._async_client.call_tool(tool_name, arguments))

    def list_tools(self) -> list[dict]:
        return self._async_client.list_tools()

    @property
    def is_connected(self) -> bool:
        return self._async_client.is_connected

    def disconnect(self):
        self._run(self._async_client.disconnect())


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
