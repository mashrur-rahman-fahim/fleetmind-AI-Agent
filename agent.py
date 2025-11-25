"""
FleetMind AI Agent
Autonomous fleet management agent using Gemini 2.0 Flash
Track 2: MCP in Action - Enterprise Category
"""

import json
import re
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field

import google.generativeai as genai

from config import Config, AGENT_SYSTEM_PROMPT
from mcp_client import FleetMindMCPClient, MCPResponse


@dataclass
class AgentStep:
    """Represents a step in the agent's execution"""
    step_number: int
    action: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    result: Optional[any] = None
    reasoning: str = ""


@dataclass
class AgentResponse:
    """Complete response from the agent"""
    message: str
    steps: list[AgentStep] = field(default_factory=list)
    reasoning: str = ""
    tools_called: list[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class FleetMindAgent:
    """
    AI Agent for FleetMind Fleet Management
    Uses Gemini 2.0 Flash for reasoning and MCP tools for execution

    Advanced Features:
    - Context Engineering: Smart conversation memory with summarization
    - Multi-step Planning: Complex task breakdown and execution
    - Reasoning Transparency: Detailed explanation of decision-making
    """

    def __init__(self, mcp_client: FleetMindMCPClient, gemini_api_key: str):
        self.mcp_client = mcp_client
        self.conversation_history: list[dict] = []
        self.max_tool_calls = Config.MAX_TOOL_CALLS_PER_TURN

        # Context Engineering: Enhanced memory management
        self.context_summary: str = ""  # Rolling summary of conversation
        self.user_preferences: dict = {}  # Learned user preferences
        self.task_context: dict = {}  # Current task context
        self.max_history_length = 20  # Max messages before summarization

        # Initialize Gemini
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel(
            model_name=Config.GEMINI_MODEL,
            generation_config={
                "temperature": Config.AGENT_TEMPERATURE,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
        )

    async def _summarize_conversation(self) -> str:
        """
        Context Engineering: Summarize conversation when it gets too long
        This prevents context window overflow and maintains relevant information
        """
        if len(self.conversation_history) < self.max_history_length:
            return ""

        # Take older messages (not the most recent 6)
        messages_to_summarize = self.conversation_history[:-6]

        summary_prompt = f"""Summarize the following conversation history concisely.
Focus on:
1. Key actions taken (orders created, drivers assigned, etc.)
2. User preferences or patterns
3. Important context for future requests

Conversation:
{json.dumps(messages_to_summarize, indent=2)}

Provide a concise summary in 3-4 sentences."""

        try:
            response = self.model.generate_content(summary_prompt)
            summary = response.text
            # Keep only recent messages + summary
            self.conversation_history = self.conversation_history[-6:]
            return summary
        except Exception:
            return ""

    def _extract_user_preferences(self, user_message: str, agent_response: str):
        """
        Context Engineering: Learn user preferences over time
        Examples: preferred priority levels, common addresses, driver preferences
        """
        # Simple pattern matching for common preferences
        if "urgent" in user_message.lower() or "asap" in user_message.lower():
            self.user_preferences["prefers_urgent"] = True

        if "fragile" in user_message.lower():
            self.user_preferences["handles_fragile"] = True

        # Extract common addresses (simple heuristic)
        if "deliver to" in user_message.lower() or "address" in user_message.lower():
            # Could extract and store frequently used addresses
            pass

    def _build_tools_schema(self) -> str:
        """Build a schema of available tools for the AI"""
        tools = self.mcp_client.list_tools()
        schema_parts = []

        for tool in tools:
            params = tool.get("parameters", {})
            properties = params.get("properties", {})
            required = params.get("required", [])

            param_list = []
            for name, prop in properties.items():
                req_marker = "*" if name in required else ""
                param_type = prop.get("type", "any")
                desc = prop.get("description", "")
                param_list.append(f"  - {name}{req_marker} ({param_type}): {desc[:100]}")

            params_str = "\n".join(param_list) if param_list else "  (no parameters)"
            schema_parts.append(f"**{tool['name']}**: {tool['description']}\nParameters:\n{params_str}")

        return "\n\n".join(schema_parts)

    def _create_prompt(self, user_message: str) -> str:
        """
        Create the full prompt for the AI model with Context Engineering
        Includes conversation summary, user preferences, and task context
        """
        # Get current date/time for context
        now = datetime.now()
        current_time = now.strftime("%Y-%m-%d %H:%M:%S")
        default_delivery_time = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")

        # Build context with Context Engineering enhancements
        context = f"""
Current Date/Time: {current_time}
Default Expected Delivery Time (if not specified): {default_delivery_time}

Connected to MCP Server: {self.mcp_client.is_connected}
Available Tools: {len(self.mcp_client.tools)}
"""

        # Add conversation summary if available (Context Engineering)
        if self.context_summary:
            context += f"\n**Conversation Summary**: {self.context_summary}\n"

        # Add learned user preferences (Context Engineering)
        if self.user_preferences:
            prefs_text = "\n**Learned User Preferences**:\n"
            if self.user_preferences.get("prefers_urgent"):
                prefs_text += "- User often creates urgent deliveries\n"
            if self.user_preferences.get("handles_fragile"):
                prefs_text += "- User frequently handles fragile items\n"
            context += prefs_text

        # Recent conversation context (limited to prevent overflow)
        recent_history = self.conversation_history[-6:] if self.conversation_history else []
        history_text = ""
        if recent_history:
            history_text = "\n\n**Recent Conversation**:\n"
            for msg in recent_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:500]
                history_text += f"{role.upper()}: {content}\n"

        # Tool schema
        tools_schema = self._build_tools_schema()

        return f"""{AGENT_SYSTEM_PROMPT}

## Context
{context}
{history_text}

## Available Tools Schema
{tools_schema}

## User Request
{user_message}

## Your Response Format
Respond with a JSON object containing:
{{
    "reasoning": "Your step-by-step thinking process (be detailed and explain WHY you choose certain actions)",
    "plan": [
        {{
            "step": 1,
            "action": "Description of what you're doing",
            "tool": "tool_name or null if no tool needed",
            "arguments": {{}} // tool arguments if applicable
        }}
    ],
    "final_message": "Your response to the user after executing the plan"
}}

If no tools are needed (e.g., answering a question), set plan to an empty array.
IMPORTANT: Only include the JSON object in your response, no other text.
"""

    def _parse_ai_response(self, response_text: str) -> dict:
        """Parse the AI's JSON response"""
        # Try to extract JSON from the response
        try:
            # First try direct parse
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in text
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: return as simple message
        return {
            "reasoning": "Direct response",
            "plan": [],
            "final_message": response_text
        }

    async def process_message(self, user_message: str) -> AgentResponse:
        """
        Process a user message and return the agent's response

        Context Engineering Applied:
        - Summarizes long conversations to prevent context overflow
        - Learns and applies user preferences
        - Maintains task context across messages

        Args:
            user_message: The user's natural language input

        Returns:
            AgentResponse with message, steps, and reasoning
        """
        # Context Engineering: Summarize if conversation is getting long
        if len(self.conversation_history) >= self.max_history_length:
            self.context_summary = await self._summarize_conversation()

        # Add to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Generate AI response
        prompt = self._create_prompt(user_message)

        try:
            response = self.model.generate_content(prompt)
            ai_response_text = response.text
        except Exception as e:
            return AgentResponse(
                message=f"Error generating AI response: {str(e)}",
                success=False,
                error=str(e)
            )

        # Parse the response
        parsed = self._parse_ai_response(ai_response_text)
        reasoning = parsed.get("reasoning", "")
        plan = parsed.get("plan", [])
        final_message = parsed.get("final_message", "")

        # Execute the plan
        steps: list[AgentStep] = []
        tools_called: list[str] = []

        for i, step_plan in enumerate(plan[:self.max_tool_calls]):
            step = AgentStep(
                step_number=i + 1,
                action=step_plan.get("action", ""),
                tool_name=step_plan.get("tool"),
                tool_args=step_plan.get("arguments", {}),
                reasoning=step_plan.get("reasoning", "")
            )

            # Execute tool if specified
            if step.tool_name:
                tool_result = await self.mcp_client.call_tool(
                    step.tool_name,
                    step.tool_args
                )
                step.result = tool_result.result if tool_result.success else tool_result.error
                tools_called.append(step.tool_name)

                # If tool failed, note it
                if not tool_result.success:
                    step.action += f" (FAILED: {tool_result.error})"

            steps.append(step)

        # If we executed tools, regenerate final message with results
        if steps:
            final_message = await self._generate_final_response(
                user_message, steps, reasoning
            )

        # Add assistant response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": final_message
        })

        # Context Engineering: Extract and learn user preferences
        self._extract_user_preferences(user_message, final_message)

        return AgentResponse(
            message=final_message,
            steps=steps,
            reasoning=reasoning,
            tools_called=tools_called,
            success=True
        )

    async def _generate_final_response(
        self,
        user_message: str,
        steps: list[AgentStep],
        reasoning: str
    ) -> str:
        """Generate a final user-friendly response after tool execution"""
        # Build execution summary
        execution_summary = []
        for step in steps:
            result_str = json.dumps(step.result, indent=2) if step.result else "No result"
            execution_summary.append(f"""
Step {step.step_number}: {step.action}
Tool: {step.tool_name or 'None'}
Arguments: {json.dumps(step.tool_args, indent=2) if step.tool_args else 'None'}
Result: {result_str[:1000]}
""")

        summary_text = "\n".join(execution_summary)

        prompt = f"""Based on the tool execution results below, provide a clear, helpful response to the user.

User Request: {user_message}

Initial Reasoning: {reasoning}

Execution Results:
{summary_text}

Provide a concise, user-friendly summary of what was accomplished. Include:
1. What actions were taken
2. Key results (order IDs, driver names, etc.)
3. Any relevant next steps or suggestions

Keep the response conversational and helpful. Do not include raw JSON - format data nicely.
"""

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception:
            # Fallback to basic summary
            return f"Completed {len(steps)} operations. Check the execution steps for details."

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []


# Utility functions for common operations
def format_order_summary(order: dict) -> str:
    """Format an order for display"""
    return f"""
**Order {order.get('order_id', 'N/A')}**
- Customer: {order.get('customer_name', 'N/A')}
- Address: {order.get('delivery_address', 'N/A')}
- Status: {order.get('status', 'N/A')}
- Priority: {order.get('priority', 'standard')}
- Created: {order.get('created_at', 'N/A')}
"""


def format_driver_summary(driver: dict) -> str:
    """Format a driver for display"""
    return f"""
**Driver {driver.get('driver_id', 'N/A')}**
- Name: {driver.get('name', 'N/A')}
- Status: {driver.get('status', 'N/A')}
- Vehicle: {driver.get('vehicle_type', 'N/A')} ({driver.get('vehicle_plate', 'N/A')})
- Capacity: {driver.get('capacity_kg', 0)}kg / {driver.get('capacity_m3', 0)}m³
"""


def format_assignment_summary(assignment: dict) -> str:
    """Format an assignment for display"""
    return f"""
**Assignment {assignment.get('assignment_id', 'N/A')}**
- Order: {assignment.get('order_id', 'N/A')}
- Driver: {assignment.get('driver_id', 'N/A')}
- Status: {assignment.get('status', 'N/A')}
- Distance: {assignment.get('route_distance_meters', 0) / 1000:.1f} km
- ETA: {assignment.get('estimated_arrival', 'N/A')}
"""
