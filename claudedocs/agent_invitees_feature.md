# Agent Default Invitees Feature

## Overview
Added a new `invitees` field to agents that stores default invitees who will be automatically included in all calendar events created by the agent. This allows agents to have a consistent set of people (like supervisors, assistants, or team members) who should be included in all appointments.

## Implementation Details

### 1. Database Schema Changes

**Agent Model Updates** (`app/models/database.py`):
```python
invitees = Column(JSON, nullable=True)  # [{"name": "John Doe", "email": "john@example.com", "availability": "always"}]
```

**Migration Created**:
- File: `alembic/versions/03c741585071_add_invitees_field_to_agents.py`
- Adds `invitees` JSON column to `agents` table
- Nullable field to maintain backward compatibility

### 2. API Schema Updates

**AgentUpdateRequest** (both user and admin endpoints):
- Added `invitees: Optional[List[Dict[str, Any]]]` field
- Allows updating the default invitees list

**AgentResponse** (both user and admin endpoints):
- Added `invitees: Optional[List[Dict[str, Any]]]` field
- Returns current default invitees in API responses

### 3. Calendar Integration

**Default Invitee Merging**:
- When creating calendar events, default invitees are automatically merged with event-specific attendees
- Duplicates are removed while preserving order
- Default invitees take precedence in ordering

**Updated Methods**:
1. `create_calendar_event()` - Merges agent's default invitees with event attendees
2. `update_calendar_event()` - Merges default invitees when updating attendees

## Data Structure

### Invitees Format
```json
[
  {
    "name": "John Doe",
    "email": "john@example.com",
    "availability": "always"
  },
  {
    "name": "Jane Smith",
    "email": "jane@company.com",
    "availability": "business_hours"
  }
]
```

### Fields:
- **name** (string): Display name of the invitee
- **email** (string, required): Email address for calendar invitations
- **availability** (string): When this person should be included ("always", "business_hours", etc.)

## Usage Examples

### 1. Setting Default Invitees via API
```http
PUT /api/tenants/{tenant_id}/agents/{agent_id}
Content-Type: application/json

{
  "invitees": [
    {
      "name": "Manager",
      "email": "manager@company.com",
      "availability": "always"
    },
    {
      "name": "Assistant",
      "email": "assistant@company.com",
      "availability": "business_hours"
    }
  ]
}
```

### 2. Calendar Event Creation
When the agent creates a calendar event:
```python
# Event with specific attendees
create_calendar_event(
    agent_id="agent123",
    summary="Client Meeting",
    attendees=["client@external.com"]
)

# Resulting attendees will be:
# 1. manager@company.com (from default invitees)
# 2. assistant@company.com (from default invitees)
# 3. client@external.com (event-specific)
```

### 3. Automatic Merging Logic
- **Default invitees** are added first (in order from agent settings)
- **Event-specific attendees** are added next
- **Duplicates are removed** (if someone is in both lists, they appear only once)
- **Order is preserved** (default invitees first, then event attendees)

## Benefits

1. **Consistency**: Ensures key stakeholders are always included in agent appointments
2. **Automation**: No need to manually add the same people to every event
3. **Flexibility**: Can still add event-specific attendees as needed
4. **Customizable**: Different availability settings for different invitees
5. **Backward Compatible**: Existing agents without invitees continue to work normally

## Migration Path

### To apply the changes:
1. **Run migration**: `alembic upgrade head`
2. **Update agents**: Use the API to set default invitees for existing agents
3. **Test calendar events**: Verify invitees are automatically included

### Example agent update:
```bash
curl -X PUT "http://localhost:8000/api/tenants/tenant123/agents/agent456" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "invitees": [
      {
        "name": "Operations Manager",
        "email": "ops@company.com",
        "availability": "always"
      }
    ]
  }'
```

## Files Modified

1. **`app/models/database.py`** - Added invitees column to Agent model
2. **`app/api/user_endpoints.py`** - Updated AgentUpdateRequest and AgentResponse schemas
3. **`app/api/admin_endpoints.py`** - Updated AgentUpdate and AgentResponse schemas
4. **`app/tools/calendar_tools.py`** - Added invitee merging logic to calendar event creation/updates
5. **`alembic/versions/03c741585071_add_invitees_field_to_agents.py`** - Database migration

## Future Enhancements

Potential future improvements:
- **Availability filtering**: Only include invitees based on their availability setting
- **Role-based invitees**: Different invitees for different types of meetings
- **Time-based rules**: Include/exclude invitees based on meeting time
- **Notification preferences**: Custom notification settings per invitee
- **Approval workflows**: Require approval for certain invitees