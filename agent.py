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
        # Safety check - ensure we have strings
        if not isinstance(user_message, str):
            return
        if not isinstance(agent_response, str):
            agent_response = str(agent_response) if agent_response else ""

        # Simple pattern matching for common preferences
        user_lower = user_message.lower()
        if "urgent" in user_lower or "asap" in user_lower:
            self.user_preferences["prefers_urgent"] = True

        if "fragile" in user_lower:
            self.user_preferences["handles_fragile"] = True

        # Extract common addresses (simple heuristic)
        if "deliver to" in user_lower or "address" in user_lower:
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
        # Build execution summary - extract key data from results
        execution_summary = []
        all_items = []  # Collect list items for display

        for step in steps:
            result = step.result
            result_str = ""

            if result:
                # Handle list results (orders, drivers, etc.)
                if isinstance(result, dict):
                    # Check for list-type responses
                    if 'orders' in result and isinstance(result['orders'], list):
                        all_items = result['orders']
                        result_str = f"Found {len(all_items)} orders"
                    elif 'drivers' in result and isinstance(result['drivers'], list):
                        all_items = result['drivers']
                        result_str = f"Found {len(all_items)} drivers"
                    elif 'assignments' in result and isinstance(result['assignments'], list):
                        all_items = result['assignments']
                        result_str = f"Found {len(all_items)} assignments"
                    else:
                        result_str = json.dumps(result, indent=2)[:2000]
                elif isinstance(result, list):
                    all_items = result
                    result_str = f"Found {len(result)} items"
                else:
                    result_str = str(result)[:2000]

            execution_summary.append(f"Step {step.step_number}: {step.action}\nTool: {step.tool_name}\nResult: {result_str}")

        summary_text = "\n".join(execution_summary)

        # Build items table if we have list data
        items_table = ""
        if all_items:
            # Detect type and build appropriate table
            if all_items and isinstance(all_items[0], dict):
                if 'order_id' in all_items[0]:
                    items_table = "\n\nORDERS DATA:\n| Order ID | Customer | Address | Status | Priority | Driver |\n|----------|----------|---------|--------|----------|--------|\n"
                    for item in all_items:
                        # Handle NESTED structure (fetch_orders, get_incomplete_orders)
                        customer = item.get('customer', {})
                        if isinstance(customer, dict):
                            customer_name = customer.get('name', '')
                        else:
                            # Handle FLAT structure (search_orders)
                            customer_name = item.get('customer_name', 'N/A')

                        delivery = item.get('delivery', {})
                        if isinstance(delivery, dict):
                            address = delivery.get('address', '')
                        else:
                            address = item.get('delivery_address', 'N/A')

                        details = item.get('details', {})
                        if isinstance(details, dict):
                            status = details.get('status', '')
                            priority = details.get('priority', 'standard')
                        else:
                            status = item.get('status', 'N/A')
                            priority = item.get('priority', 'standard')

                        # Get assigned driver
                        assigned_driver = item.get('assigned_driver_id')
                        if assigned_driver:
                            driver_str = str(assigned_driver)[-8:]  # Last 8 chars
                        else:
                            driver_str = 'none'

                        # Truncate for table display
                        order_id = str(item.get('order_id', 'N/A'))[:22]
                        customer_name = str(customer_name)[:15] if customer_name else 'N/A'
                        address = str(address)[:25] if address else 'N/A'

                        items_table += f"| {order_id} | {customer_name} | {address}... | {status or 'N/A'} | {priority} | {driver_str} |\n"

                elif 'driver_id' in all_items[0]:
                    items_table = "\n\nDRIVERS DATA:\n| Driver ID | Name | Phone | Status | Vehicle | Location | Skills |\n|-----------|------|-------|--------|---------|----------|--------|\n"
                    for item in all_items:
                        driver_id = str(item.get('driver_id', 'N/A'))[:15]
                        name = str(item.get('name', 'N/A'))[:25]
                        status = item.get('status', 'N/A')

                        # Handle NESTED structure (fetch_drivers, get_available_drivers)
                        vehicle = item.get('vehicle', {})
                        if isinstance(vehicle, dict):
                            vehicle_type = vehicle.get('type', 'N/A')
                        else:
                            # Handle FLAT structure (search_drivers)
                            vehicle_type = item.get('vehicle_type', 'N/A')

                        contact = item.get('contact', {})
                        if isinstance(contact, dict):
                            phone = contact.get('phone') or item.get('phone')
                        else:
                            phone = item.get('phone')
                        phone = phone if phone else 'N/A'

                        # Handle location - prefer address, fallback to lat/lng
                        location = item.get('location', {})
                        if isinstance(location, dict):
                            loc_address = location.get('address')
                            if loc_address:
                                loc_str = str(loc_address)[:20]
                            elif location.get('latitude') and location.get('longitude'):
                                loc_str = f"{location.get('latitude', 0):.4f},{location.get('longitude', 0):.4f}"
                            else:
                                loc_str = 'N/A'
                        else:
                            loc_str = 'N/A'

                        # Handle skills array
                        skills = item.get('skills', [])
                        if skills and isinstance(skills, list):
                            skills_str = ','.join(str(s) for s in skills[:2])  # Show first 2
                            if len(skills) > 2:
                                skills_str += '...'
                        else:
                            skills_str = 'none'

                        items_table += f"| {driver_id} | {name} | {phone} | {status} | {vehicle_type} | {loc_str} | {skills_str} |\n"

                elif 'assignment_id' in all_items[0]:
                    items_table = "\n\nASSIGNMENTS DATA:\n| Assignment ID | Order ID | Driver ID | Status | ETA | Distance |\n|---------------|----------|-----------|--------|-----|----------|\n"
                    for item in all_items:
                        assignment_id = str(item.get('assignment_id', 'N/A'))[:15]
                        order_id = str(item.get('order_id', 'N/A'))[:15]
                        driver_id = str(item.get('driver_id', 'N/A'))[:15]
                        status = item.get('status', 'N/A')

                        # Handle ETA
                        eta = item.get('estimated_arrival', 'N/A')
                        if eta and eta != 'N/A' and len(str(eta)) > 10:
                            eta = str(eta)[11:16]  # Extract HH:MM from ISO datetime

                        # Handle distance - try route.distance_meters or flat
                        route = item.get('route', {})
                        if isinstance(route, dict):
                            distance = route.get('distance_meters')
                        else:
                            distance = item.get('route_distance_meters')
                        if distance:
                            distance = f"{int(distance)/1000:.1f}km"
                        else:
                            distance = 'N/A'

                        items_table += f"| {assignment_id} | {order_id} | {driver_id} | {status} | {eta} | {distance} |\n"

        # Generate concise response with Gemini
        response_prompt = f"""Based on the following tool execution results, provide a CONCISE response to the user.

User's original request: {user_message}

Execution Results:
{summary_text}

Guidelines:
- Be brief and direct (2-3 sentences max for simple queries)
- State the key result/answer first
- Only mention relevant details
- Don't repeat the user's question
- Don't explain what tools were used unless there was an error

Respond naturally as if talking to the user."""

        try:
            response = self.model.generate_content(response_prompt)
            final_text = response.text.strip()

            # Add the data table if we have items
            if items_table:
                final_text += items_table

            return final_text
        except Exception:
            # Fallback to simple summary
            return f"Completed {len(steps)} operation(s)." + items_table

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        self.context_summary = ""
        self.task_context = {}
