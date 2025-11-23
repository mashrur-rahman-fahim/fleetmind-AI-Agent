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

import gradio as gr

from config import Config
from mcp_client import FleetMindMCPClient
from agent import FleetMindAgent, AgentResponse


# Global state
mcp_client: FleetMindMCPClient | None = None
agent: FleetMindAgent | None = None


async def connect_to_mcp(server_url: str, api_key: str) -> tuple[str, str]:
    """Connect to the MCP server"""
    global mcp_client, agent

    if not server_url or not api_key:
        return "❌ Please provide both server URL and API key", ""

    try:
        mcp_client = FleetMindMCPClient(server_url, api_key)
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
    """Synchronous wrapper for connect"""
    return asyncio.run(connect_to_mcp(server_url, api_key))


async def process_chat_message(
    message: str,
    history: list[list[str]],
    gemini_key: str
) -> tuple[list[list[str]], str, str]:
    """Process a chat message through the agent"""
    global agent, mcp_client

    if not mcp_client or not mcp_client.is_connected:
        history.append([message, "❌ Not connected to MCP server. Please connect first."])
        return history, "", ""

    if not agent:
        # Try to initialize agent with provided key
        if gemini_key:
            agent = FleetMindAgent(mcp_client, gemini_key)
        else:
            history.append([message, "❌ Gemini API key not configured. Please provide it in settings."])
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

        history.append([message, response.message])
        return history, reasoning_text, tools_text

    except Exception as e:
        error_msg = f"❌ Error processing message: {str(e)}"
        history.append([message, error_msg])
        return history, f"**Error:** {str(e)}", ""


def sync_process_chat(
    message: str,
    history: list[list[str]],
    gemini_key: str
) -> tuple[list[list[str]], str, str]:
    """Synchronous wrapper for chat processing"""
    return asyncio.run(process_chat_message(message, history, gemini_key))


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

    with gr.Blocks() as app:
        gr.Markdown("""
        # 🚛 FleetMind AI Agent
        ### Enterprise Fleet Management with Autonomous AI

        **Track 2: MCP in Action - Enterprise Category**

        Chat naturally with the AI agent to manage your delivery fleet. The agent will:
        - Understand your requests in natural language
        - Plan and execute multi-step operations
        - Use AI-powered assignment for optimal driver selection
        - Explain its reasoning process
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
        **About FleetMind AI Agent**

        This application demonstrates the power of MCP (Model Context Protocol) for building
        autonomous AI agents. It connects to the FleetMind MCP server which provides 29 tools
        for comprehensive fleet management:

        - 📍 **Geocoding & Routing** - Address conversion and intelligent route planning
        - 📦 **Order Management** - Create, track, and manage delivery orders
        - 🚗 **Driver Management** - Onboard and manage delivery drivers
        - 🔄 **Assignment System** - Manual, automatic, and AI-powered driver assignment
        - 📊 **Analytics** - Fleet performance and SLA tracking

        Built for the **MCP Hackathon Track 2: MCP in Action**

        Tags: `mcp-in-action-track-enterprise`
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
