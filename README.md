# FleetMind AI Agent

**Track 2: MCP in Action - Enterprise Category**

Tags: `mcp-in-action-track-enterprise`

An autonomous AI agent for enterprise fleet management that leverages the Model Context Protocol (MCP) to execute complex delivery operations through natural language.

## Overview

FleetMind AI Agent is a chat-based interface that connects to the [FleetMind MCP Server](https://huggingface.co/spaces/your-username/fleetmind-mcp) and uses Google's Gemini 2.0 Flash model to:

- **Understand** natural language requests for fleet operations
- **Plan** multi-step execution strategies
- **Execute** MCP tools autonomously
- **Explain** reasoning and results clearly

## Features

### Natural Language Fleet Management
```
User: "Create an urgent delivery for John Doe at 123 Main St, due by 5pm"

Agent: I'll help you create this urgent delivery order.

Step 1: Geocoding address "123 Main St"...
Step 2: Creating order with priority=urgent, deadline=5pm...

Order ORD-20251122-xxx created successfully:
- Customer: John Doe
- Address: 123 Main St (37.xxx, -122.xxx)
- Priority: URGENT
- Deadline: 5:00 PM today

Would you like me to find the best available driver?
```

### AI-Powered Assignment
Leverages Gemini 2.0 Flash for intelligent driver assignment:
- Analyzes order requirements (priority, fragility, deadlines)
- Evaluates driver capabilities (skills, vehicle type, capacity)
- Considers real-time factors (traffic, weather, distance)
- Provides confidence scores and reasoning

### 29 MCP Tools Available
- **Geocoding & Routing**: Address conversion, traffic-aware routes
- **Order Management**: Create, track, update, search orders
- **Driver Management**: Onboard drivers, track locations, manage status
- **Assignment System**: Manual, automatic, and AI-powered assignment
- **Delivery Tracking**: Complete/fail deliveries with cascading updates

## Quick Start

### 1. Clone and Setup
```bash
cd fleetmind-agent-track2
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your API keys
```

Required keys:
- `MCP_SERVER_URL`: Your FleetMind MCP server URL
- `MCP_API_KEY`: FleetMind API key (get from MCP server /generate-key)
- `GEMINI_API_KEY`: Google Gemini API key

### 3. Run the App
```bash
python app.py
```

Open http://localhost:7860 in your browser.

## Architecture

```
┌─────────────────────────────────────────┐
│         Gradio UI (app.py)              │
│    Chat Interface + Reasoning Panel     │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│       FleetMind Agent (agent.py)        │
│    • Natural Language Understanding     │
│    • Multi-step Planning               │
│    • Tool Selection & Execution        │
│    • Response Generation               │
└─────────────────┬───────────────────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
┌───────────────┐   ┌───────────────────┐
│  Gemini 2.0   │   │  MCP Client       │
│  Flash API    │   │  (mcp_client.py)  │
│  (Reasoning)  │   │  (Tool Execution) │
└───────────────┘   └────────┬──────────┘
                             │
                             ▼
                  ┌───────────────────────┐
                  │  FleetMind MCP Server │
                  │  (29 Tools via SSE)   │
                  └───────────────────────┘
```

## Example Interactions

### Create a Driver
```
"Add a new driver named Sarah with a truck, capacity 2000kg"
```

### Create an Order
```
"I need a delivery to 456 Oak Ave for customer Mike, priority express, due in 3 hours"
```

### Intelligent Assignment
```
"Use AI to find the best driver for order ORD-20251122-001"
```

### Fleet Status
```
"Show me all available drivers and pending orders"
```

### Complete Delivery
```
"Mark the delivery for order ORD-xxx as complete"
```

## Deployment to Hugging Face Spaces

1. Create a new Space on Hugging Face (Gradio SDK)
2. Add secrets in Space settings:
   - `MCP_SERVER_URL`
   - `MCP_API_KEY`
   - `GEMINI_API_KEY`
3. Push code to the Space repository

## Technology Stack

- **UI**: Gradio 4.x
- **AI Model**: Google Gemini 2.0 Flash
- **Protocol**: Model Context Protocol (MCP)
- **Transport**: SSE (Server-Sent Events)
- **Backend**: FleetMind MCP Server (29 tools)

## MCP Hackathon

This project is a submission for **Track 2: MCP in Action** in the Enterprise category.

### Why This Qualifies

1. **Complete AI Agent**: Autonomous reasoning, planning, and execution
2. **MCP Integration**: Full MCP client connecting to production server
3. **Enterprise Value**: Real-world fleet management use case
4. **AI-Powered**: Gemini 2.0 Flash for intelligent decision making
5. **Production Ready**: Can connect to live MCP servers

## License

MIT License

## Credits

- FleetMind MCP Server - Enterprise fleet management tools
- Google Gemini - AI reasoning capabilities
- Gradio - User interface framework
- Model Context Protocol - Tool standardization
