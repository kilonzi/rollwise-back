# Calendar Integration Enhancements

## Overview
Comprehensive calendar integration improvements that automatically set up calendar functionality when creating agents, include calendar information in agent prompts, and prevent overbooking through slot-based appointment limits.

## Major Changes

### 1. Database Schema Updates

**Field Rename: max_daily_appointments → max_slot_appointments**
```sql
-- Old field (daily limit)
max_daily_appointments = Column(Integer, default=8)

-- New field (slot-based limit to prevent overbooking)
max_slot_appointments = Column(Integer, default=1)
```

**Migration**: `alembic/versions/14415f9d20fc_rename_max_daily_appointments_to_max_.py`
- Migrates existing data with new default value of 1 (no overbooking)
- Preserves data integrity during transition

### 2. Automatic Agent Setup

**Calendar Creation on Agent Creation** (`app/api/user_endpoints.py`):
```python
# Auto-creates Google Calendar for each new agent
calendar_id = calendar_service.create_agent_calendar(agent.id, agent.name)
agent.calendar_id = calendar_id
```

**Default Values Set on Creation**:
- **Business Hours**: Monday-Friday, 8 AM to 5 PM (UTC)
- **Slot Duration**: 30 minutes
- **Max Slot Appointments**: 1 (no overbooking)
- **Buffer Time**: 10 minutes between appointments
- **Booking Enabled**: True
- **Default Invitees**: Agent creator automatically added

### 3. Enhanced Agent Prompts

**Calendar Information in Prompts** (`app/utils/agent_config_builder.py`):

**When booking_enabled = true:**
```
CALENDAR BOOKING INFORMATION:
- Business Hours: Monday, Tuesday, Wednesday, Thursday, Friday from 08:00 to 17:00 (UTC)
- Default appointment duration: 30 minutes
- Buffer time between appointments: 10 minutes
- Overbooking policy: No overlapping appointments allowed (maximum 1 appointment per time slot)
- Calendar ID: cal_abc123

When customers request appointments, use the calendar tools to check availability and create bookings within business hours only.
```

**When booking_enabled = false:**
```
CALENDAR BOOKING:
Booking and appointments are not allowed at the moment. Please inform customers that appointment scheduling is currently unavailable.
```

## Implementation Details

### Agent Creation Process

**Before Enhancement:**
```python
agent = Agent(
    tenant_id=tenant_id,
    name=agent_data.name,
    greeting=agent_data.greeting,
    # ... basic fields only
)
```

**After Enhancement:**
```python
# Get current user for default invitee
user_email = current_user.get("email", "")
user_name = current_user.get("name", "User")

# Default business hours (Monday to Friday, 8 AM to 5 PM)
default_business_hours = {
    "start": "08:00",
    "end": "17:00",
    "timezone": "UTC",
    "days": [1, 2, 3, 4, 5]
}

# Default invitees (creator of the agent)
default_invitees = [
    {
        "name": user_name,
        "email": user_email,
        "availability": "always"
    }
] if user_email else []

agent = Agent(
    # ... basic fields
    # Calendar defaults
    business_hours=default_business_hours,
    default_slot_duration=30,
    max_slot_appointments=1,  # No overbooking
    buffer_time=10,
    invitees=default_invitees,
    booking_enabled=True
)

# Auto-create Google Calendar
calendar_id = calendar_service.create_agent_calendar(agent.id, agent.name)
agent.calendar_id = calendar_id
```

### Prompt Generation Enhancement

**Calendar Information Builder** (`app/utils/agent_config_builder.py:build_calendar_info`):
- Dynamically builds calendar section based on agent settings
- Includes business hours, slot duration, buffer time, overbooking policy
- Lists blocked dates and calendar ID
- Provides clear guidance for booking vs. no-booking scenarios

**Integration into Prompts**:
```python
# Before
full_prompt = default_identity + "\n\n" + formatted_general_prompt

# After
calendar_info = AgentConfigBuilder.build_calendar_info(agent)
full_prompt = default_identity + "\n\n" + formatted_general_prompt + calendar_info
```

### Overbooking Prevention

**Concept Change**:
- **Old**: Daily appointment limits (max 8 per day)
- **New**: Slot-based limits (max 1 per time slot = no overlapping)

**Benefits**:
- Prevents double-booking the same time slot
- More intuitive scheduling logic
- Better customer experience (no conflicts)
- Configurable per agent (can be increased if needed)

## API Schema Updates

### User Endpoints (`app/api/user_endpoints.py`)
```python
# AgentUpdateRequest
max_slot_appointments: Optional[int] = None  # max appointments per time slot

# AgentResponse
max_slot_appointments: Optional[int] = None
```

### Admin Endpoints (`app/api/admin_endpoints.py`)
```python
# AgentUpdate
max_slot_appointments: Optional[int] = None  # max appointments per time slot

# AgentResponse
max_slot_appointments: Optional[int] = None
```

## Usage Examples

### 1. Creating an Agent (Now Auto-Configured)
```http
POST /api/tenants/{tenant_id}/agents
{
  "name": "Customer Service Agent",
  "greeting": "Hello! How can I help you today?",
  "voice_model": "aura-2-thalia-en"
}

# Response automatically includes:
{
  "agent": {
    "calendar_id": "cal_abc123xyz",
    "business_hours": {
      "start": "08:00",
      "end": "17:00",
      "timezone": "UTC",
      "days": [1,2,3,4,5]
    },
    "default_slot_duration": 30,
    "max_slot_appointments": 1,
    "buffer_time": 10,
    "booking_enabled": true,
    "invitees": [
      {
        "name": "John Smith",
        "email": "john@company.com",
        "availability": "always"
      }
    ]
  }
}
```

### 2. Agent Prompt Example Output
```
You are Thalia, a friendly and professional representative for Acme Corp. Your role is to assist customers with their inquiries, provide information about services, and help with general business questions.

CURRENT DATE AND TIME CONTEXT:
Today is Monday, September 16, 2024...

CALENDAR BOOKING INFORMATION:
- Business Hours: Monday, Tuesday, Wednesday, Thursday, Friday from 08:00 to 17:00 (UTC)
- Default appointment duration: 30 minutes
- Buffer time between appointments: 10 minutes
- Overbooking policy: No overlapping appointments allowed (maximum 1 appointment per time slot)
- Calendar ID: cal_abc123xyz

When customers request appointments, use the calendar tools to check availability and create bookings within business hours only.
```

### 3. Customizing Calendar Settings
```http
PUT /api/tenants/{tenant_id}/agents/{agent_id}
{
  "business_hours": {
    "start": "09:00",
    "end": "18:00",
    "timezone": "EST",
    "days": [1,2,3,4,5,6]  // Include Saturday
  },
  "max_slot_appointments": 2,  // Allow up to 2 overlapping appointments
  "buffer_time": 15,
  "blocked_dates": ["2024-12-25", "2024-01-01"]
}
```

## Benefits

### For Administrators
1. **Zero Configuration**: Agents are ready for booking immediately after creation
2. **Consistent Defaults**: All agents start with sensible calendar settings
3. **Overbooking Prevention**: Default 1-appointment-per-slot prevents conflicts
4. **Auto-Calendar Creation**: Each agent gets dedicated Google Calendar

### For AI Agents
1. **Calendar Awareness**: Agents understand their booking capabilities and limitations
2. **Business Hours Enforcement**: Prompts include specific working hours
3. **Booking Guidance**: Clear instructions on when/how to use calendar tools
4. **Context-Aware**: Agents know if booking is enabled or disabled

### For Customers
1. **No Double Booking**: Slot-based limits prevent scheduling conflicts
2. **Business Hours Respect**: Appointments only scheduled during business hours
3. **Buffer Time**: Adequate time between appointments for preparation
4. **Consistent Experience**: All agents follow same booking patterns

## Migration Guide

### Database Migration
```bash
# Apply the schema changes
alembic upgrade head

# All existing agents will be updated with:
# - max_slot_appointments = 1 (was max_daily_appointments = 8)
# - booking_enabled = true
```

### For Existing Agents
1. **Calendar Setup**: Existing agents without calendar_id can be updated:
   ```http
   PUT /api/agents/{agent_id}
   {"calendar_id": "new_calendar_id"}
   ```

2. **Business Hours**: Set appropriate business hours:
   ```http
   PUT /api/agents/{agent_id}
   {
     "business_hours": {
       "start": "09:00", "end": "17:00",
       "timezone": "UTC", "days": [1,2,3,4,5]
     }
   }
   ```

3. **Invitees**: Add default attendees:
   ```http
   PUT /api/agents/{agent_id}
   {
     "invitees": [
       {"name": "Manager", "email": "manager@company.com", "availability": "always"}
     ]
   }
   ```

## Files Modified

1. **`app/models/database.py`** - Renamed max_daily_appointments to max_slot_appointments
2. **`app/api/user_endpoints.py`** - Enhanced agent creation with calendar setup and defaults
3. **`app/api/admin_endpoints.py`** - Updated schemas for new field
4. **`app/utils/agent_config_builder.py`** - Added calendar information to agent prompts
5. **`app/services/calendar_service.py`** - Updated to use slot-based appointment limits
6. **Migration**: `alembic/versions/14415f9d20fc_rename_max_daily_appointments_to_max_.py`

## Future Enhancements

1. **Multi-Slot Booking**: Enhanced logic for max_slot_appointments > 1
2. **Time Zone Support**: Dynamic time zone handling per agent
3. **Advanced Scheduling**: Recurring appointments, multi-day events
4. **Calendar Sync**: Two-way sync with external calendar systems
5. **Availability Rules**: Complex availability patterns beyond business hours