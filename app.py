"""
FleetMind AI Agent - Gradio Application
Track 2: MCP in Action - Enterprise Category

An autonomous AI agent for enterprise fleet management that connects to
the FleetMind MCP server and executes operations through natural language.

Tags: mcp-in-action-track-enterprise
"""

import asyncio
import json
from typing import Generator
import threading
from concurrent.futures import Future

import gradio as gr

from config import Config
from mcp_client import FleetMindMCPClient
from agent import FleetMindAgent, AgentResponse


# Global state
mcp_client: FleetMindMCPClient | None = None
agent: FleetMindAgent | None = None

# Global event loop for async operations
_event_loop = None
_event_loop_thread = None


def get_event_loop():
    """Get or create a persistent event loop running in a background thread"""
    global _event_loop, _event_loop_thread

    if _event_loop is None or not _event_loop.is_running():
        def run_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()

        _event_loop = asyncio.new_event_loop()
        _event_loop_thread = threading.Thread(target=run_loop, args=(_event_loop,), daemon=True)
        _event_loop_thread.start()

    return _event_loop


def run_async(coro):
    """Run an async coroutine in the background event loop"""
    loop = get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


async def connect_to_mcp(server_url: str, api_key: str) -> tuple[str, str, str]:
    """Connect to the MCP server"""
    global mcp_client, agent

    if not server_url or not api_key:
        return "❌ Please provide both server URL and API key", "", "disconnected"

    try:
        # Disconnect old client if exists
        if mcp_client is not None:
            try:
                await mcp_client.disconnect()
            except Exception as e:
                print(f"Warning: Error disconnecting old client: {e}")

        mcp_client = FleetMindMCPClient(server_url, api_key)

        # Connect using official MCP SDK (fast connection)
        print("Connecting to MCP server...")
        result = await mcp_client.connect()

        if result.get("success"):
            # Initialize agent with Gemini API key
            gemini_key = Config.GEMINI_API_KEY
            if not gemini_key:
                return "⚠️ Connected but GEMINI_API_KEY not set", "", "warning"

            agent = FleetMindAgent(mcp_client, gemini_key)

            tools_count = result.get('tools_count', 0)
            tools_list = result.get("tools", [])

            # Group tools by category
            geocoding_tools = [t for t in tools_list if 'geocode' in t or 'route' in t]
            order_tools = [t for t in tools_list if 'order' in t]
            driver_tools = [t for t in tools_list if 'driver' in t]
            assignment_tools = [t for t in tools_list if 'assign' in t or 'delivery' in t]
            other_tools = [t for t in tools_list if t not in geocoding_tools + order_tools + driver_tools + assignment_tools]

            tools_md = f"""### Connected Successfully!

**{tools_count} Tools Available:**

🗺️ **Routing** ({len(geocoding_tools)}): {', '.join(geocoding_tools[:3])}{'...' if len(geocoding_tools) > 3 else ''}

📦 **Orders** ({len(order_tools)}): {', '.join(order_tools[:3])}{'...' if len(order_tools) > 3 else ''}

🚗 **Drivers** ({len(driver_tools)}): {', '.join(driver_tools[:3])}{'...' if len(driver_tools) > 3 else ''}

📋 **Assignments** ({len(assignment_tools)}): {', '.join(assignment_tools[:3])}{'...' if len(assignment_tools) > 3 else ''}
"""

            return (
                f"✅ Connected! {tools_count} tools ready",
                tools_md,
                "connected"
            )
        else:
            return f"❌ {result.get('error', 'Connection failed')}", "", "error"

    except Exception as e:
        return f"❌ Error: {str(e)}", "", "error"


def sync_connect(server_url: str, api_key: str) -> tuple[str, str, str]:
    """Synchronous wrapper for connect - uses persistent event loop"""
    return run_async(connect_to_mcp(server_url, api_key))


async def process_chat_message(
    message: str,
    history: list
) -> tuple[list, str, str]:
    """Process a chat message through the agent"""
    global agent, mcp_client

    if not mcp_client or not mcp_client.is_connected:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": "⚠️ **Not connected to MCP server**\n\nPlease click 'Connect' in the settings panel first."})
        return history, "", ""

    if not agent:
        # Try to initialize agent with env key
        gemini_key = Config.GEMINI_API_KEY
        if gemini_key:
            agent = FleetMindAgent(mcp_client, gemini_key)
        else:
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": "⚠️ **Gemini API key required**\n\nPlease set GEMINI_API_KEY in environment variables."})
            return history, "", ""

    try:
        # Process the message
        response: AgentResponse = await agent.process_message(message)

        # Build thinking block (Claude-style collapsible)
        thinking_html = ""
        if response.reasoning or response.steps:
            thinking_content = ""

            if response.reasoning:
                thinking_content += f"<div class='thinking-section'><strong>💭 Reasoning</strong><p>{response.reasoning}</p></div>"

            if response.steps:
                steps_html = ""
                for step in response.steps:
                    status_icon = "✅" if step.result else "🔄"
                    step_html = f"<div class='thinking-step'><strong>{status_icon} Step {step.step_number}:</strong> {step.action}"
                    if step.tool_name:
                        step_html += f"<br><span class='tool-badge'>🔧 {step.tool_name}</span>"
                        if step.result:
                            if isinstance(step.result, dict):
                                if 'success' in step.result:
                                    result_text = '✅ Success' if step.result.get('success') else '❌ Failed'
                                elif 'order_id' in step.result:
                                    result_text = f"Created: {step.result.get('order_id')}"
                                elif 'driver_id' in step.result:
                                    result_text = f"Driver: {step.result.get('driver_id')}"
                                else:
                                    result_text = "Done"
                            else:
                                result_text = str(step.result)[:50] + "..." if len(str(step.result)) > 50 else str(step.result)
                            step_html += f" → <span class='result-text'>{result_text}</span>"
                    step_html += "</div>"
                    steps_html += step_html
                thinking_content += f"<div class='thinking-section'><strong>📋 Execution</strong>{steps_html}</div>"

            # Build collapsible thinking block
            tools_count = len(response.tools_called) if response.tools_called else 0
            thinking_html = f"""<details class="thinking-block">
<summary class="thinking-header">
<span class="thinking-icon">💭</span>
<span class="thinking-title">Thinking</span>
<span class="thinking-meta">{tools_count} tool{'s' if tools_count != 1 else ''} used</span>
</summary>
<div class="thinking-content">
{thinking_content}
</div>
</details>"""

        # Build reasoning display for sidebar (simplified)
        reasoning_text = ""
        if response.reasoning:
            reasoning_text = f"**Reasoning:** {response.reasoning[:200]}..." if len(response.reasoning) > 200 else f"**Reasoning:** {response.reasoning}"

        # Build tools called display for sidebar
        tools_text = ""
        if response.tools_called:
            tools_text = " • ".join([f"`{t}`" for t in response.tools_called])
            tools_text = f"**Tools:** {tools_text}"

        # Add messages - include thinking block in assistant message
        history.append({"role": "user", "content": message})

        # Combine thinking block with response
        full_response = thinking_html + "\n\n" + response.message if thinking_html else response.message
        history.append({"role": "assistant", "content": full_response})

        return history, reasoning_text, tools_text

    except Exception as e:
        error_msg = f"❌ **Error:** {str(e)}\n\nPlease try again or check your connection."
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": error_msg})
        return history, f"### ❌ Error\n{str(e)}", ""


def sync_process_chat(
    message: str,
    history: list
) -> tuple[list, str, str]:
    """Synchronous wrapper for chat processing - uses persistent event loop"""
    return run_async(process_chat_message(message, history))


def clear_chat() -> tuple[list, str, str]:
    """Clear chat history"""
    global agent
    if agent:
        agent.clear_history()
    return [], "*Start a conversation to see AI reasoning here...*", "*Tools used will appear here...*"


# Example prompts - more diverse and useful
EXAMPLE_PROMPTS = [
    ("📋 List drivers", "Show me all available drivers"),
    ("➕ Create driver", "Create a new driver named Alex with a motorcycle, phone 555-0123"),
    ("📦 List orders", "Show me all pending orders"),
    ("🚀 Create order", "Create an urgent delivery for Sarah at 456 Oak Street, due in 2 hours"),
    ("🤖 AI assign", "Use intelligent assignment to find the best driver for my latest order"),
    ("📊 Fleet status", "What's the current status of my entire fleet?"),
    ("🗺️ Geocode", "Geocode: 1600 Amphitheatre Parkway, Mountain View, CA"),
    ("🔍 Search", "Find all orders for customer John"),
]


# Build the Gradio interface
def create_app() -> gr.Blocks:
    """Create the Gradio application with professional UI"""

    # Modern dark theme CSS
    custom_css = """
    /* FleetMind Professional Dark Theme */
    :root {
        --bg-primary: #0a0f1a;
        --bg-secondary: #111827;
        --bg-card: #1a2332;
        --bg-hover: #243044;
        --text-primary: #f1f5f9;
        --text-secondary: #94a3b8;
        --text-muted: #64748b;
        --accent: #3b82f6;
        --accent-hover: #2563eb;
        --accent-glow: rgba(59, 130, 246, 0.3);
        --success: #10b981;
        --warning: #f59e0b;
        --error: #ef4444;
        --border: #1e293b;
        --border-light: #334155;
    }

    /* Global container */
    .gradio-container {
        background: linear-gradient(180deg, var(--bg-primary) 0%, #0d1420 100%) !important;
        min-height: 100vh;
    }

    /* Header styling */
    .header-container {
        background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-secondary) 100%);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }

    /* Chat container */
    .chat-container {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 16px;
        overflow: hidden;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    }

    /* ========== DOUBLE SCROLLBAR FIX FOR GRADIO 6.x ========== */

    /* Target by elem_id for precise control */
    #fleetmind-chatbot {
        overflow: hidden !important;
        height: 480px !important;
        max-height: 480px !important;
    }

    /* The ONLY scrollable container - first child of chatbot */
    #fleetmind-chatbot > div:first-child {
        overflow-y: auto !important;
        overflow-x: hidden !important;
        height: 100% !important;
        max-height: 480px !important;
        scrollbar-width: thin !important;
        scrollbar-color: var(--border-light) var(--bg-secondary) !important;
    }

    #fleetmind-chatbot > div:first-child::-webkit-scrollbar {
        width: 8px !important;
        display: block !important;
    }

    #fleetmind-chatbot > div:first-child::-webkit-scrollbar-track {
        background: var(--bg-secondary) !important;
    }

    #fleetmind-chatbot > div:first-child::-webkit-scrollbar-thumb {
        background: var(--border-light) !important;
        border-radius: 4px !important;
    }

    /* EVERYTHING else inside - NO SCROLL */
    #fleetmind-chatbot > div:first-child > *,
    #fleetmind-chatbot > div:first-child > * > *,
    #fleetmind-chatbot > div:first-child > * > * > *,
    #fleetmind-chatbot > div:first-child > * > * > * > *,
    #fleetmind-chatbot > div:first-child > * > * > * > * > * {
        overflow: visible !important;
        max-height: none !important;
        height: auto !important;
        scrollbar-width: none !important;
        -ms-overflow-style: none !important;
    }

    #fleetmind-chatbot > div:first-child > *::-webkit-scrollbar,
    #fleetmind-chatbot > div:first-child > * > *::-webkit-scrollbar,
    #fleetmind-chatbot > div:first-child > * > * > *::-webkit-scrollbar,
    #fleetmind-chatbot > div:first-child > * > * > * > *::-webkit-scrollbar {
        display: none !important;
        width: 0 !important;
        height: 0 !important;
    }

    /* Also target by class as fallback */
    .gradio-chatbot {
        overflow: hidden !important;
    }

    /* Thinking block styling - NO scroll on container */
    .thinking-block {
        max-height: none !important;
        overflow: visible !important;
    }

    /* Only thinking-content can scroll internally */
    .thinking-content {
        max-height: 250px !important;
        overflow-y: auto !important;
        scrollbar-width: thin !important;
    }

    .thinking-content::-webkit-scrollbar {
        width: 6px !important;
        display: block !important;
    }

    .thinking-content::-webkit-scrollbar-thumb {
        background: #4a5568 !important;
        border-radius: 3px !important;
    }

    .user-message {
        background: linear-gradient(135deg, var(--accent) 0%, #1d4ed8 100%) !important;
        color: white !important;
        margin-left: 20% !important;
    }

    .bot-message {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        color: var(--text-primary) !important;
        margin-right: 20% !important;
    }

    /* Input area */
    .input-container {
        background: var(--bg-card);
        border-top: 1px solid var(--border);
        padding: 16px;
    }

    textarea, input[type="text"], input[type="password"] {
        background: var(--bg-secondary) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
        padding: 12px 16px !important;
        font-size: 14px !important;
        transition: all 0.2s ease !important;
    }

    textarea:focus, input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--accent-glow) !important;
        outline: none !important;
    }

    /* Buttons */
    button.primary {
        background: linear-gradient(135deg, var(--accent) 0%, #1d4ed8 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 12px 24px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 12px var(--accent-glow) !important;
    }

    button.primary:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px var(--accent-glow) !important;
    }

    button.secondary {
        background: var(--bg-hover) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        padding: 10px 16px !important;
        font-size: 13px !important;
        transition: all 0.2s ease !important;
    }

    button.secondary:hover {
        background: var(--border-light) !important;
        border-color: var(--accent) !important;
    }

    /* Example buttons */
    .example-btn {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border) !important;
        color: var(--text-secondary) !important;
        border-radius: 20px !important;
        padding: 8px 16px !important;
        font-size: 12px !important;
        transition: all 0.2s ease !important;
        white-space: nowrap !important;
    }

    .example-btn:hover {
        background: var(--bg-hover) !important;
        border-color: var(--accent) !important;
        color: var(--text-primary) !important;
    }

    /* Settings panel */
    .settings-panel {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }

    /* Accordion */
    .accordion {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
        margin-bottom: 12px !important;
        overflow: hidden;
    }

    .accordion-header {
        background: var(--bg-card) !important;
        padding: 14px 16px !important;
        font-weight: 600 !important;
        color: var(--text-primary) !important;
    }

    /* Status indicators */
    .status-connected {
        color: var(--success);
        font-weight: 600;
    }

    .status-disconnected {
        color: var(--error);
    }

    .status-warning {
        color: var(--warning);
    }

    /* Reasoning panel */
    .reasoning-panel {
        background: var(--bg-secondary);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 16px;
        max-height: 400px;
        overflow-y: auto;
    }

    .reasoning-panel pre {
        background: var(--bg-primary) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
        padding: 12px !important;
        overflow-x: auto;
    }

    .reasoning-panel code {
        background: var(--bg-hover) !important;
        color: var(--accent) !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
        font-size: 12px !important;
    }

    /* Markdown styling */
    .prose {
        color: var(--text-primary) !important;
    }

    .prose h1, .prose h2, .prose h3 {
        color: var(--text-primary) !important;
        font-weight: 600 !important;
    }

    .prose h3 {
        font-size: 14px !important;
        margin-top: 16px !important;
        margin-bottom: 8px !important;
        color: var(--text-secondary) !important;
    }

    .prose p {
        color: var(--text-secondary) !important;
        line-height: 1.6 !important;
    }

    .prose ul, .prose ol {
        color: var(--text-secondary) !important;
    }

    /* Labels */
    label {
        color: var(--text-secondary) !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        margin-bottom: 6px !important;
    }

    /* Footer */
    .footer {
        text-align: center;
        padding: 24px;
        color: var(--text-muted);
        font-size: 13px;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: var(--bg-secondary);
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb {
        background: var(--border-light);
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: var(--text-muted);
    }

    /* Badge */
    .badge {
        display: inline-block;
        background: var(--accent);
        color: white;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Connection status card */
    .connection-card {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(16, 185, 129, 0.05) 100%);
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 12px;
        padding: 12px 16px;
    }

    .connection-card.error {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(239, 68, 68, 0.05) 100%);
        border-color: rgba(239, 68, 68, 0.3);
    }

    /* Hide default gradio footer */
    footer {
        display: none !important;
    }

    /* Connect button with custom teal color */
    #connect-btn {
        background: linear-gradient(135deg, #047857 0%, #065f46 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 12px rgba(4, 120, 87, 0.3) !important;
        transition: all 0.2s ease !important;
    }

    #connect-btn:hover {
        background: linear-gradient(135deg, #059669 0%, #047857 100%) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px rgba(4, 120, 87, 0.4) !important;
    }

    /* Fix button and group spacing */
    .gradio-group {
        gap: 8px !important;
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
    }

    .gradio-row {
        gap: 8px !important;
        align-items: center !important;
    }

    /* Remove extra padding from button containers */
    .gradio-button {
        margin: 0 !important;
    }

    /* Send button vertical alignment */
    #send-btn {
        align-self: center !important;
        height: auto !important;
    }

    /* Compact chat input area */
    #component-0 > div {
        gap: 12px !important;
    }

    /* Quick actions section - compact */
    .quick-actions-row {
        margin-top: 8px !important;
        margin-bottom: 4px !important;
    }

    /* Settings accordion spacing */
    .gradio-accordion {
        margin-bottom: 8px !important;
    }

    .gradio-accordion > div {
        padding: 12px !important;
    }

    /* API key help text styling */
    .api-help-text {
        font-size: 11px !important;
        color: #64748b !important;
        margin-top: 4px !important;
        line-height: 1.4 !important;
    }

    .api-help-text a {
        color: #3b82f6 !important;
        text-decoration: none !important;
    }

    .api-help-text a:hover {
        text-decoration: underline !important;
    }

    /* Claude-style Thinking Block */
    .thinking-block {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #2d3748;
        border-left: 3px solid #f59e0b;
        border-radius: 12px;
        margin-bottom: 16px;
        overflow: hidden;
        transition: all 0.2s ease;
    }

    .thinking-block[open] {
        border-color: #f59e0b;
    }

    .thinking-header {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 12px 16px;
        cursor: pointer;
        user-select: none;
        background: rgba(245, 158, 11, 0.05);
        transition: background 0.2s ease;
    }

    .thinking-header:hover {
        background: rgba(245, 158, 11, 0.1);
    }

    .thinking-icon {
        font-size: 16px;
        animation: pulse 2s infinite;
    }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }

    .thinking-block[open] .thinking-icon {
        animation: none;
    }

    .thinking-title {
        font-weight: 600;
        color: #f59e0b;
        font-size: 13px;
        letter-spacing: 0.3px;
    }

    .thinking-meta {
        margin-left: auto;
        font-size: 11px;
        color: #64748b;
        background: #1e293b;
        padding: 3px 8px;
        border-radius: 10px;
    }

    .thinking-content {
        padding: 16px;
        border-top: 1px solid #2d3748;
        background: rgba(0, 0, 0, 0.2);
        /* Scroll properties defined in the main scrollbar fix section above */
    }

    .thinking-section {
        margin-bottom: 12px;
    }

    .thinking-section:last-child {
        margin-bottom: 0;
    }

    .thinking-section strong {
        display: block;
        color: #94a3b8;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }

    .thinking-section p {
        color: #cbd5e1;
        font-size: 13px;
        line-height: 1.6;
        margin: 0;
    }

    .thinking-step {
        padding: 8px 12px;
        background: #0f172a;
        border-radius: 8px;
        margin-bottom: 6px;
        font-size: 12px;
        color: #e2e8f0;
        border-left: 2px solid #3b82f6;
    }

    .thinking-step:last-child {
        margin-bottom: 0;
    }

    .tool-badge {
        display: inline-block;
        background: #1e3a5f;
        color: #60a5fa;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-family: monospace;
        margin-top: 4px;
    }

    .result-text {
        color: #10b981;
        font-size: 11px;
    }

    /* Hide marker for details */
    .thinking-block summary::-webkit-details-marker,
    .thinking-block summary::marker {
        display: none;
        content: "";
    }

    .thinking-header::before {
        content: "▶";
        font-size: 10px;
        color: #64748b;
        transition: transform 0.2s ease;
    }

    .thinking-block[open] .thinking-header::before {
        transform: rotate(90deg);
    }
    """

    with gr.Blocks() as app:
        # Apply custom CSS via HTML style tag
        gr.HTML(f"<style>{custom_css}</style>")

        # Header
        gr.HTML("""
        <div style="background: linear-gradient(135deg, #1a2332 0%, #111827 100%);
                    border: 1px solid #1e293b; border-radius: 16px; padding: 28px;
                    margin-bottom: 24px; box-shadow: 0 8px 32px rgba(0,0,0,0.4);">
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px;">
                <div>
                    <h1 style="margin: 0; font-size: 28px; font-weight: 700; color: #f1f5f9;
                               display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 32px;">🚛</span>
                        FleetMind AI Agent
                    </h1>
                    <p style="margin: 8px 0 0 0; color: #94a3b8; font-size: 15px;">
                        Autonomous fleet management powered by AI
                    </p>
                </div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <span style="background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
                                 color: white; padding: 6px 14px; border-radius: 20px;
                                 font-size: 12px; font-weight: 600;">
                        🏆 Track 2: MCP in Action
                    </span>
                    <span style="background: #1e293b; color: #94a3b8; padding: 6px 12px;
                                 border-radius: 20px; font-size: 11px; border: 1px solid #334155;">
                        Enterprise
                    </span>
                </div>
            </div>
            <div style="display: flex; gap: 24px; margin-top: 20px; flex-wrap: wrap;">
                <div style="display: flex; align-items: center; gap: 8px; color: #64748b; font-size: 13px;">
                    <span style="color: #3b82f6;">🧠</span> Gemini 2.0 Flash
                </div>
                <div style="display: flex; align-items: center; gap: 8px; color: #64748b; font-size: 13px;">
                    <span style="color: #10b981;">🔧</span> 29 MCP Tools
                </div>
                <div style="display: flex; align-items: center; gap: 8px; color: #64748b; font-size: 13px;">
                    <span style="color: #f59e0b;">🎯</span> Context Engineering
                </div>
                <div style="display: flex; align-items: center; gap: 8px; color: #64748b; font-size: 13px;">
                    <span style="color: #8b5cf6;">📊</span> Real-time Execution
                </div>
            </div>
        </div>
        """)

        # JavaScript to fix double scrollbar during generation
        gr.HTML("""
        <script>
        (function() {
            function fixChatbotScroll() {
                const chatbot = document.getElementById('fleetmind-chatbot');
                if (!chatbot) return;

                // Set chatbot container
                chatbot.style.overflow = 'hidden';
                chatbot.style.height = '480px';
                chatbot.style.maxHeight = '480px';

                // Get first child - the main scroll container
                const scrollContainer = chatbot.firstElementChild;
                if (scrollContainer) {
                    scrollContainer.style.overflowY = 'auto';
                    scrollContainer.style.overflowX = 'hidden';
                    scrollContainer.style.height = '100%';
                    scrollContainer.style.maxHeight = '480px';

                    // Remove scroll from ALL descendants
                    const descendants = scrollContainer.querySelectorAll('*');
                    descendants.forEach(el => {
                        // Skip thinking-content which should scroll
                        if (el.classList && el.classList.contains('thinking-content')) {
                            return;
                        }
                        el.style.overflow = 'visible';
                        el.style.overflowY = 'visible';
                        el.style.overflowX = 'visible';
                        el.style.maxHeight = 'none';
                        el.style.height = 'auto';
                    });
                }
            }

            // Run immediately
            fixChatbotScroll();

            // Run on short interval to catch state changes
            setInterval(fixChatbotScroll, 50);

            // Run on any DOM change
            const observer = new MutationObserver(() => {
                fixChatbotScroll();
            });

            // Start observing once DOM is ready
            function startObserving() {
                const chatbot = document.getElementById('fleetmind-chatbot');
                if (chatbot) {
                    observer.observe(chatbot, {
                        childList: true,
                        subtree: true,
                        attributes: true,
                        attributeFilter: ['style', 'class']
                    });
                    fixChatbotScroll();
                } else {
                    setTimeout(startObserving, 100);
                }
            }

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', startObserving);
            } else {
                startObserving();
            }
        })();
        </script>
        """)

        with gr.Row(equal_height=False):
            # Left column - Chat (main area)
            with gr.Column(scale=7):
                # Chat interface
                chatbot = gr.Chatbot(
                    label="",
                    height=480,
                    show_label=False,
                    elem_id="fleetmind-chatbot",
                )

                # Input area
                with gr.Row():
                    msg_input = gr.Textbox(
                        placeholder="Ask me to manage your fleet... (e.g., 'Create an urgent delivery to 123 Main St')",
                        show_label=False,
                        lines=1,
                        scale=6,
                    )
                    send_btn = gr.Button(
                        "Send →",
                        variant="primary",
                        scale=1,
                        min_width=100,
                        elem_id="send-btn",
                    )

                # Quick actions
                gr.HTML("""<div style="margin: 8px 0 6px 0; color: #64748b; font-size: 12px; font-weight: 500;">
                    Quick Actions
                </div>""")

                with gr.Row():
                    example_btns = []
                    for icon_label, prompt in EXAMPLE_PROMPTS[:4]:
                        btn = gr.Button(
                            icon_label,
                            size="sm",
                            variant="secondary",
                        )
                        example_btns.append((btn, prompt))

                with gr.Row():
                    for icon_label, prompt in EXAMPLE_PROMPTS[4:]:
                        btn = gr.Button(
                            icon_label,
                            size="sm",
                            variant="secondary",
                        )
                        example_btns.append((btn, prompt))

            # Right column - Settings & Info
            with gr.Column(scale=3):
                # Connection Settings
                with gr.Accordion("⚙️ Connection", open=True):
                    server_url = gr.Textbox(
                        label="MCP Server URL",
                        value=Config.MCP_SERVER_URL,
                        placeholder="https://your-server.hf.space",
                        lines=1,
                    )
                    api_key = gr.Textbox(
                        label="FleetMind API Key",
                        value=Config.MCP_API_KEY,
                        type="password",
                        placeholder="fm_xxxxx...",
                    )
                    gr.HTML("""
                    <div style="font-size: 11px; color: #64748b; margin-top: 4px; line-height: 1.4;">
                        Get your API key from the
                        <a href="https://huggingface.co/spaces/MCP-1st-Birthday/fleetmind-dispatch-ai" target="_blank" style="color: #3b82f6;">
                            FleetMind MCP Server
                        </a> → Click "Get API Key" button
                    </div>
                    """)

                    with gr.Row():
                        connect_btn = gr.Button(
                            "🔗 Connect",
                            variant="primary",
                            scale=2,
                            elem_id="connect-btn",
                        )
                        clear_btn = gr.Button(
                            "🗑️ Clear",
                            variant="secondary",
                            scale=1,
                        )

                    connection_status = gr.Textbox(
                        label="Status",
                        interactive=False,
                        lines=1,
                        value="Not connected",
                    )
                    connection_state = gr.State(value="disconnected")
                    tools_info = gr.Markdown(
                        value="*Connect to see available tools*",
                    )

                # AI Reasoning Panel
                with gr.Accordion("🧠 AI Reasoning", open=True):
                    reasoning_display = gr.Markdown(
                        value="*Start a conversation to see AI reasoning here...*",
                    )

                # Tools Panel
                with gr.Accordion("🔧 Tools Used", open=False):
                    tools_display = gr.Markdown(
                        value="*Tools used will appear here...*",
                    )

        # Footer info
        gr.HTML("""
        <div style="margin-top: 32px; padding: 24px; background: #111827; border-radius: 16px;
                    border: 1px solid #1e293b;">
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 24px;">
                <div>
                    <h4 style="color: #f1f5f9; margin: 0 0 12px 0; font-size: 14px;">🔑 Getting Started</h4>
                    <p style="color: #64748b; font-size: 13px; line-height: 1.6; margin: 0;">
                        <strong style="color: #94a3b8;">1.</strong> Get FleetMind API Key from
                        <a href="https://huggingface.co/spaces/MCP-1st-Birthday/fleetmind-dispatch-ai" target="_blank" style="color: #3b82f6;">FleetMind MCP Server</a>
                        → Click "Get API Key"<br>
                        <strong style="color: #94a3b8;">2.</strong> Enter key above and click Connect<br>
                        <strong style="color: #94a3b8;">3.</strong> Start chatting with natural language!
                    </p>
                </div>
                <div>
                    <h4 style="color: #f1f5f9; margin: 0 0 12px 0; font-size: 14px;">🎯 What This Agent Does</h4>
                    <p style="color: #64748b; font-size: 13px; line-height: 1.6; margin: 0;">
                        Autonomously manages delivery fleets using natural language.
                        Creates orders, assigns drivers, and optimizes routes.
                    </p>
                </div>
                <div>
                    <h4 style="color: #f1f5f9; margin: 0 0 12px 0; font-size: 14px;">🧠 How It Works</h4>
                    <p style="color: #64748b; font-size: 13px; line-height: 1.6; margin: 0;">
                        Uses Gemini 2.0 Flash for reasoning, connects to FleetMind MCP Server
                        for execution, maintains context across conversations.
                    </p>
                </div>
            </div>
            <div style="text-align: center; margin-top: 20px; padding-top: 16px; border-top: 1px solid #1e293b;">
                <span style="color: #64748b; font-size: 12px;">
                    Built with ❤️ for the MCP 1st Birthday Hackathon • Track 2: MCP in Action - Enterprise
                </span>
            </div>
        </div>
        """)

        # Event handlers
        def handle_connect(server_url, api_key):
            # Clear agent history on new connection
            global agent
            if agent:
                agent.clear_history()

            status, tools, state = sync_connect(server_url, api_key)
            # Return status, tools, state, and clear chat + reasoning displays
            return (
                status,
                tools,
                state,
                [],  # Clear chatbot
                "*Connected! Start a conversation...*",  # Clear reasoning
                "*Tools used will appear here...*"  # Clear tools display
            )

        connect_btn.click(
            fn=handle_connect,
            inputs=[server_url, api_key],
            outputs=[connection_status, tools_info, connection_state, chatbot, reasoning_display, tools_display]
        )

        # Step 1: Show user message immediately and clear input
        def user_message_submitted(message, history):
            if not message.strip():
                return history, "", gr.update(interactive=True)
            # Add user message to history immediately
            history = history + [{"role": "user", "content": message}]
            # Return updated history, clear input, disable input while processing
            return history, "", gr.update(interactive=False)

        # Step 2: Generate AI response (runs after user message is shown)
        def generate_response(history):
            if not history or history[-1]["role"] != "user":
                return history, "", "", gr.update(interactive=True)

            # Get the last user message
            user_message = history[-1]["content"]
            # Remove it from history (sync_process_chat will add it back with response)
            history_without_last = history[:-1]

            # Process and get response
            result = sync_process_chat(user_message, history_without_last)

            # Return: updated history, reasoning, tools, re-enable input
            return result[0], result[1], result[2], gr.update(interactive=True)

        # Chain the events: first show user message, then generate response
        send_btn.click(
            fn=user_message_submitted,
            inputs=[msg_input, chatbot],
            outputs=[chatbot, msg_input, msg_input]
        ).then(
            fn=generate_response,
            inputs=[chatbot],
            outputs=[chatbot, reasoning_display, tools_display, msg_input]
        )

        msg_input.submit(
            fn=user_message_submitted,
            inputs=[msg_input, chatbot],
            outputs=[chatbot, msg_input, msg_input]
        ).then(
            fn=generate_response,
            inputs=[chatbot],
            outputs=[chatbot, reasoning_display, tools_display, msg_input]
        )

        clear_btn.click(
            fn=clear_chat,
            outputs=[chatbot, reasoning_display, tools_display]
        )

        # Example button handlers
        for btn, prompt in example_btns:
            btn.click(
                fn=lambda p=prompt: p,
                outputs=[msg_input]
            )

    return app


# Main entry point
if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )
