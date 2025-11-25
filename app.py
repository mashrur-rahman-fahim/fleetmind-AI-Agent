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


async def connect_to_mcp(server_url: str, api_key: str) -> tuple[str, str]:
    """Connect to the MCP server"""
    global mcp_client, agent

    if not server_url or not api_key:
        return "Please provide both server URL and API key", ""

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
            # Initialize agent
            gemini_key = Config.GEMINI_API_KEY
            if not gemini_key:
                return "⚠️ Connected to MCP but GEMINI_API_KEY not configured", json.dumps(result, indent=2)

            agent = FleetMindAgent(mcp_client, gemini_key)

            tools_list = "\n".join([f"• {t}" for t in result.get("tools", [])[:15]])
            if len(result.get("tools", [])) > 15:
                tools_list += f"\n• ... and {len(result.get('tools', [])) - 15} more"

            return (
                f"✅ Connected! Session: {result.get('session_id', 'N/A')[:20]}...\n"
                f"Tools available: {result.get('tools_count', 0)}",
                f"**Available Tools:**\n{tools_list}"
            )
        else:
            return f"❌ Connection failed: {result.get('error', 'Unknown error')}", ""

    except Exception as e:
        return f"❌ Error: {str(e)}", ""


def sync_connect(server_url: str, api_key: str) -> tuple[str, str]:
    """Synchronous wrapper for connect - uses persistent event loop"""
    return run_async(connect_to_mcp(server_url, api_key))


async def process_chat_message(
    message: str,
    history: list,
    gemini_key: str
) -> tuple[list, str, str]:
    """Process a chat message through the agent"""
    global agent, mcp_client

    if not mcp_client or not mcp_client.is_connected:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": "❌ Not connected to MCP server. Please connect first."})
        return history, "", ""

    if not agent:
        # Try to initialize agent with provided key
        if gemini_key:
            agent = FleetMindAgent(mcp_client, gemini_key)
        else:
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": "❌ Gemini API key not configured. Please provide it in settings."})
            return history, "", ""

    try:
        # Process the message
        response: AgentResponse = await agent.process_message(message)

        # Build reasoning display
        reasoning_text = f"**Reasoning:**\n{response.reasoning}\n\n"
        if response.steps:
            reasoning_text += "**Execution Steps:**\n"
            for step in response.steps:
                reasoning_text += f"\n**Step {step.step_number}:** {step.action}\n"
                if step.tool_name:
                    reasoning_text += f"- Tool: `{step.tool_name}`\n"
                    if step.tool_args:
                        args_str = json.dumps(step.tool_args, indent=2)
                        reasoning_text += f"- Arguments:\n```json\n{args_str}\n```\n"
                    if step.result:
                        result_str = json.dumps(step.result, indent=2) if isinstance(step.result, (dict, list)) else str(step.result)
                        # Truncate if too long
                        if len(result_str) > 500:
                            result_str = result_str[:500] + "..."
                        reasoning_text += f"- Result:\n```json\n{result_str}\n```\n"

        # Build tools called display
        tools_text = ""
        if response.tools_called:
            tools_text = "**Tools Called:**\n" + "\n".join([f"• `{t}`" for t in response.tools_called])

        # Add messages in the new format
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": response.message})
        return history, reasoning_text, tools_text

    except Exception as e:
        error_msg = f"❌ Error processing message: {str(e)}"
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": error_msg})
        return history, f"**Error:** {str(e)}", ""


def sync_process_chat(
    message: str,
    history: list,
    gemini_key: str
) -> tuple[list, str, str]:
    """Synchronous wrapper for chat processing - uses persistent event loop"""
    return run_async(process_chat_message(message, history, gemini_key))


def clear_chat() -> tuple[list, str, str]:
    """Clear chat history"""
    global agent
    if agent:
        agent.clear_history()
    return [], "", ""


# Example prompts
EXAMPLE_PROMPTS = [
    "Show me all available drivers",
    "Create a new driver named John Smith with a van",
    "List all pending orders",
    "Create an urgent order for Sarah at 456 Oak Street, due in 2 hours",
    "Find the best driver for the latest order using AI",
    "What's the status of my fleet right now?",
    "Geocode the address: 1600 Amphitheatre Parkway, Mountain View, CA",
]


# Build the Gradio interface
def create_app() -> gr.Blocks:
    """Create the Gradio application"""

    # Custom CSS matching Track 1's dark theme
    custom_css = """
    /* Track 1 Dark Theme - Matching fleetmind-mcp design */
    :root {
        --bg-primary: #0f172a;
        --bg-secondary: #1e293b;
        --bg-tertiary: #334155;
        --text-primary: #e2e8f0;
        --text-secondary: #94a3b8;
        --accent-blue: #3b82f6;
        --accent-blue-hover: #2563eb;
        --accent-green: #10b981;
        --accent-red: #ef4444;
        --border-color: #334155;
    }

    /* Main container */
    .gradio-container {
        background: var(--bg-primary) !important;
        color: var(--text-primary) !important;
    }

    /* All blocks */
    .block {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
        box-shadow: 0 8px 16px rgba(0,0,0,0.4) !important;
    }

    /* Textbox, Textarea */
    textarea, input[type="text"], input[type="password"] {
        background: var(--bg-primary) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 6px !important;
    }

    /* Buttons */
    .primary {
        background: var(--accent-blue) !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
    }

    .primary:hover {
        background: var(--accent-blue-hover) !important;
    }

    .secondary {
        background: var(--bg-tertiary) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
    }

    /* Chatbot */
    .message-wrap {
        background: var(--bg-secondary) !important;
    }

    /* Markdown */
    .prose {
        color: var(--text-primary) !important;
    }

    .prose h1, .prose h2, .prose h3 {
        color: #f1f5f9 !important;
    }

    .prose code {
        background: var(--bg-tertiary) !important;
        color: var(--accent-blue) !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
    }

    .prose pre {
        background: var(--bg-primary) !important;
        border: 1px solid var(--border-color) !important;
    }

    /* Accordion */
    .accordion {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border-color) !important;
    }

    /* Labels */
    label {
        color: var(--text-primary) !important;
    }

    /* Success/Error states */
    .success {
        background: rgba(16, 185, 129, 0.1) !important;
        border-left: 4px solid var(--accent-green) !important;
    }

    .error {
        background: rgba(239, 68, 68, 0.1) !important;
        border-left: 4px solid var(--accent-red) !important;
    }
    """

    with gr.Blocks(title="FleetMind AI Agent - MCP in Action") as app:
        # Inject custom CSS using HTML
        gr.HTML(f"<style>{custom_css}</style>")
        gr.Markdown("""
        # 🚛 FleetMind AI Agent
        ### Autonomous Enterprise Fleet Management

        <div style="background: #1e3a5f; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #3b82f6;">
        <strong>🏆 Track 2: MCP in Action - Enterprise Category</strong><br>
        Tags: <code>mcp-in-action-track-enterprise</code>
        </div>

        **Autonomous AI Agent Features:**
        - 🧠 **Planning & Reasoning** - Multi-step execution with Gemini 2.0 Flash
        - 🔧 **29 MCP Tools** - Complete fleet management toolkit
        - 🎯 **Context Engineering** - Smart conversation memory and context management
        - 🤖 **AI-Powered Assignment** - Intelligent driver matching with confidence scores
        - 📊 **Real-time Execution** - Watch the agent think, plan, and execute
        """)

        with gr.Row():
            # Left column - Chat
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(
                    label="Chat with FleetMind Agent",
                    height=500
                )

                with gr.Row():
                    msg_input = gr.Textbox(
                        label="Your message",
                        placeholder="e.g., Create a new order for delivery to 123 Main St...",
                        lines=2,
                        scale=4
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)

                with gr.Row():
                    clear_btn = gr.Button("Clear Chat", size="sm")

                gr.Markdown("**Try these examples:**")
                example_btns = []
                with gr.Row():
                    for i, example in enumerate(EXAMPLE_PROMPTS[:4]):
                        btn = gr.Button(example[:40] + "..." if len(example) > 40 else example, size="sm")
                        example_btns.append((btn, example))

            # Right column - Settings & Reasoning
            with gr.Column(scale=1):
                with gr.Accordion("⚙️ Connection Settings", open=True):
                    server_url = gr.Textbox(
                        label="MCP Server URL",
                        value=Config.MCP_SERVER_URL,
                        placeholder="https://your-mcp-server.hf.space"
                    )
                    api_key = gr.Textbox(
                        label="FleetMind API Key",
                        value=Config.MCP_API_KEY,
                        type="password",
                        placeholder="fm_xxxxx..."
                    )
                    gemini_key = gr.Textbox(
                        label="Gemini API Key",
                        value=Config.GEMINI_API_KEY,
                        type="password",
                        placeholder="AIza..."
                    )
                    connect_btn = gr.Button("Connect to MCP Server", variant="secondary")
                    connection_status = gr.Textbox(
                        label="Connection Status",
                        interactive=False,
                        lines=2
                    )
                    tools_info = gr.Markdown("")

                with gr.Accordion("🧠 AI Reasoning", open=True):
                    reasoning_display = gr.Markdown(
                        value="*Reasoning will appear here after sending a message...*"
                    )

                with gr.Accordion("🔧 Tools Called", open=False):
                    tools_display = gr.Markdown(
                        value="*Tools will be listed here...*"
                    )

        # Event handlers
        connect_btn.click(
            fn=sync_connect,
            inputs=[server_url, api_key],
            outputs=[connection_status, tools_info]
        )

        def send_message(message, history, gemini_key):
            if not message.strip():
                return history, "", ""
            return sync_process_chat(message, history, gemini_key)

        send_btn.click(
            fn=send_message,
            inputs=[msg_input, chatbot, gemini_key],
            outputs=[chatbot, reasoning_display, tools_display]
        ).then(
            fn=lambda: "",
            outputs=[msg_input]
        )

        msg_input.submit(
            fn=send_message,
            inputs=[msg_input, chatbot, gemini_key],
            outputs=[chatbot, reasoning_display, tools_display]
        ).then(
            fn=lambda: "",
            outputs=[msg_input]
        )

        clear_btn.click(
            fn=clear_chat,
            outputs=[chatbot, reasoning_display, tools_display]
        )

        # Example button handlers
        for btn, example in example_btns:
            btn.click(
                fn=lambda ex=example: ex,
                outputs=[msg_input]
            )

        gr.Markdown("""
        ---

        <div style="background: #1e293b; padding: 30px; border-radius: 12px; margin-top: 20px;">

        ## 🏆 MCP Hackathon Submission

        **Track 2: MCP in Action - Enterprise Category**

        Tags: `mcp-in-action-track-enterprise`

        ### ✅ Track 2 Requirements Met

        <div style="background: #134e4a; padding: 15px; border-radius: 6px; margin: 10px 0; border-left: 4px solid #10b981;">

        ✅ **Autonomous Agent Behavior** - Gemini 2.0 Flash provides planning, reasoning, and execution<br>
        ✅ **MCP Tools Integration** - 29 enterprise fleet management tools via Model Context Protocol<br>
        ✅ **Gradio Application** - Professional dark-themed UI matching enterprise standards<br>
        ✅ **Context Engineering** - Enhanced conversation memory and context management<br>
        ✅ **Clear User Value** - Real-world fleet management with AI-powered optimization

        </div>

        ### 🎯 Why This Project Stands Out

        1. **Complete Autonomous System**: Not just tool calling - full planning, reasoning, and multi-step execution
        2. **Production-Ready Architecture**: Connects to live MCP server with 29 tools via SSE protocol
        3. **AI-Powered Intelligence**: Gemini 2.0 Flash for context-aware decision making
        4. **Enterprise Value**: Solves real business problems in logistics and delivery management
        5. **Advanced Features**: Context engineering, intelligent driver assignment, traffic-aware routing

        ### 🔧 Technology Stack

        - **Frontend**: Gradio 4.x with custom dark theme
        - **AI Model**: Google Gemini 2.0 Flash Experimental
        - **Protocol**: Model Context Protocol (MCP) via SSE transport
        - **MCP Server**: FleetMind Dispatch Coordinator (29 tools)
        - **Features**: Planning, Reasoning, Multi-step execution, Context management

        ### 📦 29 MCP Tools Available

        **Geocoding & Routing (3 tools)**
        - Address geocoding with Google Maps API
        - Traffic-aware route calculation
        - AI-powered weather + traffic routing

        **Order Management (8 tools)**
        - Create, read, update, delete orders
        - Search and filter capabilities
        - Status tracking and SLA monitoring

        **Driver Management (8 tools)**
        - Driver onboarding and profiles
        - Real-time location tracking
        - Availability and capacity management

        **Assignment System (8 tools)**
        - Manual driver assignment
        - Automatic nearest-driver assignment
        - **AI-powered intelligent assignment** using Gemini 2.0 Flash
        - Delivery completion and failure handling

        **Bulk Operations (2 tools)**
        - Batch order operations
        - Fleet-wide management

        ### 🚀 Autonomous Agent Capabilities

        The FleetMind AI Agent demonstrates true autonomous behavior:

        **Planning**: Breaks down complex requests into actionable steps
        ```
        User: "Create an urgent delivery for John at 123 Main St by 5pm and assign best driver"

        Agent Plans:
        1. Geocode address to get coordinates
        2. Create order with urgency and deadline
        3. Use AI to find optimal driver
        4. Create assignment with routing
        5. Report results and ETA
        ```

        **Reasoning**: Explains decision-making process transparently
        - Why certain tools were chosen
        - How parameters were determined
        - What trade-offs were considered

        **Execution**: Handles multi-step operations autonomously
        - Sequential tool calling with dependency management
        - Error handling and recovery
        - Result aggregation and reporting

        **Context Engineering**: Maintains coherent conversations
        - Conversation history management
        - User preference learning
        - Task continuation across messages

        ### 🌐 Live Demo

        **Try these autonomous workflows:**
        1. "Create 3 urgent orders for different addresses and assign them optimally"
        2. "Show me fleet status and recommend which driver to hire next"
        3. "Find the order taking longest and explain why"

        ### 🔗 Architecture

        ```
        User → Gradio UI → FleetMind Agent (Gemini 2.0) → MCP Client → MCP Server (29 Tools) → PostgreSQL
                                    ↓
                            Planning & Reasoning
                                    ↓
                            Multi-step Execution
                                    ↓
                            Natural Language Response
        ```

        ### 📚 Learn More

        - **FleetMind MCP Server**: [Track 1 Submission](https://huggingface.co/spaces/mcp-1st-birthday/fleetmind-dispatch-ai)
        - **Model Context Protocol**: [Anthropic MCP Docs](https://modelcontextprotocol.io)
        - **Track 2 Guide**: Enterprise AI agents using MCP tools

        </div>

        <div style="text-align: center; margin-top: 20px; color: #94a3b8;">
        Built with ❤️ for the MCP Hackathon | Track 2: MCP in Action - Enterprise
        </div>
        """)

    return app


# Main entry point
if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False
    )
