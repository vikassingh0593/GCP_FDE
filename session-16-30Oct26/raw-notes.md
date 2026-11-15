Full Name + Email
        ↓
Create stable user_id
        ↓
Create Session
        ↓
session_id generated
        ↓
User sends message
        ↓
Runner executes Agent
        ↓
Agent/Gemini may call Tool
        ↓
ToolContext.state updates state
        ↓
ADK SessionService persists session
        ↓
Browser Lifecycle Inspector shows
user_id + session_id + state + events








Mayur                     ← User
   │
   ├── Session A           ← Conversation 1
   │     └── current_case
   │
   └── Session B           ← Conversation 2
         └── current_case

Mayur's preference        ← user: state
"Preferred region = India"

Long-term historical fact ← Memory
"Q4 migration codename was Blue Lantern"




| Bucket | Example | Lifetime | Who sees it? |
|---|---|---|---|
| Session State | `current_case` | One conversation/session | That session |
| User State | `user:preferred_region` | Across user's sessions | Same user |
| App State | `app:lab_topic` | Across application | Application/users |
| Temp State | `temp:last_state_tool` | Current invocation | Current execution |
| Memory | historical conversation facts | Long term | Retrieved when needed |
