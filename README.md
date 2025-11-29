---
title: FleetMind AI Agent
emoji: 🚛
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: "6.0.1"
app_file: app.py
pinned: true
short_description: Autonomous AI dispatcher using Gemini 2.0 Flash + 29 MCP tools
tags:
  - mcp
  - mcp-in-action-track-enterprise
  - model-context-protocol
  - autonomous-agent
  - fleet-management
  - gradio
  - enterprise
  - logistics
  - gemini
  - context-engineering
  - ai-agent
---

<div align="center">

# 🚛 FleetMind AI Agent

### Autonomous Fleet Dispatcher Powered by Gemini 2.0 Flash

**The Problem:** Managing delivery dispatch requires constant decision-making—who to assign, which route to take, how to handle urgent orders.

**The Solution:** FleetMind AI Agent autonomously handles complex dispatch workflows through natural conversation, powered by **Gemini 2.0 Flash** and **29 MCP tools**.

**The Impact:** Say *"Create urgent delivery for Sarah, find the best driver considering weather"* and watch AI plan, reason, and execute the entire workflow.

[![Try It Live](https://img.shields.io/badge/🚀_Try_It_Live-7C3AED?style=for-the-badge)](https://huggingface.co/spaces/MCP-1st-Birthday/fleetmind-in-action)
[![MCP Server](https://img.shields.io/badge/📡_MCP_Server-blue?style=for-the-badge)](https://huggingface.co/spaces/MCP-1st-Birthday/fleetmind-dispatch-ai)

</div>

---

## ⚡ Quick Start

### Step 1: Open the App
👉 **[Launch FleetMind AI Agent](https://huggingface.co/spaces/MCP-1st-Birthday/fleetmind-in-action)**

### Step 2: Connect to MCP Server
- Enter MCP Server URL (pre-filled)
- Enter your API Key ([Get one here](https://mcp-1st-birthday-fleetmind-dispatch-ai.hf.space/generate-key))
- Click **Connect**

### Step 3: Start Dispatching!
```
You: "Create an urgent delivery for Dr. Emily Watson at UCSF Medical Center,
     fragile medical supplies, assign the best driver"

Agent:
  🔧 Step 1: Geocoding address... ✓ (37.7631, -122.4586)
  🔧 Step 2: Creating order... ✓ ORD-abc123
  🔧 Step 3: AI assignment... ✓ Driver Mike selected (92% confidence)

  ✅ Created urgent order for Dr. Watson and assigned to Mike Chen.
     ETA: 25 minutes. AI selected Mike because: closest driver with
     refrigerated van, experienced with medical supplies.
```

---

## 🏆 What Makes This Special?

| Feature | Description |
|---------|-------------|
| **🤖 True Autonomy** | Plans multi-step workflows, not just single tool calls |
| **🧠 Iterative Reasoning** | Sees each tool result before deciding next action |
| **💭 Transparent Thinking** | Shows reasoning process in collapsible UI blocks |
| **📚 Context Engineering** | Remembers preferences, summarizes long conversations |
| **⚡ 29 MCP Tools** | Full fleet management via official MCP SDK |

---

## 🛠️ The 29 Tools

<details>
<summary><b>📍 Geocoding & Routing (3)</b></summary>

- `geocode_address` - Address → GPS coordinates
- `calculate_route` - Traffic-aware routing
- `calculate_intelligent_route` - Weather + traffic AI routing

</details>

<details>
<summary><b>📦 Orders (8)</b></summary>

- `create_order`, `fetch_orders`, `get_order_details`
- `search_orders`, `get_incomplete_orders`, `count_orders`
- `update_order`, `delete_order`

</details>

<details>
<summary><b>👥 Drivers (8)</b></summary>

- `create_driver`, `fetch_drivers`, `get_driver_details`
- `search_drivers`, `get_available_drivers`, `count_drivers`
- `update_driver`, `delete_driver`

</details>

<details>
<summary><b>🔗 Assignments (8)</b></summary>

- `create_assignment` - Manual assignment
- **`auto_assign_order`** - Nearest driver
- **`intelligent_assign_order`** - 🤖 Gemini AI assignment
- `get_assignment_details`, `update_assignment`
- `unassign_order`, `complete_delivery`, `fail_delivery`

</details>

<details>
<summary><b>🗑️ Bulk (2)</b></summary>

- `delete_all_orders`, `delete_all_drivers`

</details>

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Gradio UI (app.py)                    │
│      Dark theme • Reasoning visualization • Chat        │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              FleetMind Agent (agent.py)                 │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────┐ │
│  │    Context    │  │ Gemini 2.0    │  │  Iterative  │ │
│  │  Engineering  │  │    Flash      │  │ Agentic Loop│ │
│  └───────────────┘  └───────────────┘  └─────────────┘ │
└────────────────────────┬────────────────────────────────┘
                         │ MCP SDK (SSE)
                         ▼
┌─────────────────────────────────────────────────────────┐
│           FleetMind MCP Server (29 tools)               │
│   PostgreSQL • Google Maps • Gemini AI • OpenWeather    │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Local Development

```bash
# Clone & install
git clone https://github.com/mashrur-rahman-fahim/fleetmind-agent-track2.git
cd fleetmind-agent-track2
pip install -r requirements.txt

# Configure .env
MCP_SERVER_URL=https://mcp-1st-birthday-fleetmind-dispatch-ai.hf.space
MCP_API_KEY=fm_your_key_here
GEMINI_API_KEY=your_gemini_key_here

# Run
python app.py
```

---

## 📊 Technical Specs

| Component | Technology |
|-----------|------------|
| **AI Model** | Gemini 2.0 Flash (gemini-2.0-flash-exp) |
| **UI Framework** | Gradio 6.0.1 |
| **MCP Transport** | SSE (Server-Sent Events) |
| **MCP SDK** | Official Python SDK |
| **Language** | Python 3.11+ |

---

## 🔗 Links

| Resource | URL |
|----------|-----|
| **Live Demo** | [FleetMind AI Agent](https://huggingface.co/spaces/MCP-1st-Birthday/fleetmind-in-action) |
| **MCP Server** | [FleetMind MCP](https://huggingface.co/spaces/MCP-1st-Birthday/fleetmind-dispatch-ai) |
| **Get API Key** | [Generate Key](https://mcp-1st-birthday-fleetmind-dispatch-ai.hf.space/generate-key) |

---

## 👥 Team

**FleetMind Development Team**

*MCP 1st Birthday Hackathon - Track 2: MCP in Action (Enterprise Category)*

---

<div align="center">

**Built with ❤️ using Gemini 2.0 Flash + MCP for the MCP 1st Birthday Hackathon**

[![MCP](https://img.shields.io/badge/MCP-1.0-orange)](https://modelcontextprotocol.io)
[![Gradio](https://img.shields.io/badge/Gradio-6.0.1-blue)](https://gradio.app)
[![Gemini](https://img.shields.io/badge/Gemini-2.0_Flash-red)](https://ai.google.dev)

</div>
