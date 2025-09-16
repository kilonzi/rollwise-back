# Agent Booking Control Feature

## Overview
Added a `booking_enabled` boolean field to control whether calendar booking functionality is enabled for each agent. This provides fine-grained control over which agents can accept calendar bookings while still allowing them to view existing appointments.

## Implementation Details

### 1. Database Schema Changes

**Agent Model Updates** (`app/models/database.py`):
```python
booking_enabled = Column(Boolean, default=True)  # Whether calendar booking is enabled for this agent
```

**Migration Created**:
- File: `alembic/versions/3b48e4a7f421_add_booking_enabled_field_to_agents.py`
- Adds `booking_enabled` Boolean column to `agents` table
- Sets default value to `true` for backward compatibility
- Updates existing records to have `booking_enabled = true`

### 2. API Schema Updates

**Complete Field Coverage**:
- All database fields are now properly exposed in API responses
- All updatable fields are available in update requests
- Added missing fields: `calendar_id`, `active`, `tenant_id`, `updated_at`

**AgentUpdateRequest** (both user and admin endpoints):
```python
booking_enabled: Optional[bool] = None  # Whether calendar booking is enabled
calendar_id: Optional[str] = None  # Google Calendar ID
active: Optional[bool] = None  # Whether agent is active
```

**AgentResponse** (both user and admin endpoints):
```python
booking_enabled: Optional[bool] = None
tenant_id: str  # Now included
updated_at: datetime  # Now included
```

### 3. Calendar Tool Integration

**Booking Control Logic**:
- Create events: Blocked if `booking_enabled = false`
- Cancel events: Blocked if `booking_enabled = false`
- Update events: Blocked if `booking_enabled = false`
- Search events: Allowed (view-only operations still work)
- List events: Allowed (view-only operations still work)

**Error Messages**:
When booking is disabled, calendar modification operations return:
```json
{
  "success": false,
  "error": "Calendar booking is disabled for this agent"
}
```

## Usage Examples

### 1. Enable/Disable Booking via API
```http
PUT /api/tenants/{tenant_id}/agents/{agent_id}
Content-Type: application/json

{
  "booking_enabled": false
}
```

### 2. Calendar Tool Behavior

**With booking_enabled = true:**
```python
create_calendar_event(agent_id="agent123", summary="Meeting")
# ✅ Creates event successfully

cancel_calendar_event(agent_id="agent123", event_id="event456")
# ✅ Cancels event successfully
```

**With booking_enabled = false:**
```python
create_calendar_event(agent_id="agent123", summary="Meeting")
# ❌ Returns: {"success": false, "error": "Calendar booking is disabled for this agent"}

list_calendar_events(agent_id="agent123", start_date="2024-01-01", end_date="2024-01-07")
# ✅ Still works - view-only operations are allowed
```

## Complete Field Coverage Verification

### Database Fields (20 total):
✅ **Core Fields**: `id`, `tenant_id`, `name`, `phone_number`, `greeting`, `voice_model`, `system_prompt`, `language`, `tools`
✅ **Calendar Fields**: `calendar_id`, `business_hours`, `default_slot_duration`, `max_daily_appointments`, `buffer_time`, `blocked_dates`, `invitees`, `booking_enabled`
✅ **System Fields**: `active`, `created_at`, `updated_at`

### API Response Coverage:
- **User API**: ✅ All 20 database fields exposed
- **Admin API**: ✅ All 20 database fields exposed

### Update Request Coverage:
- **Updatable Fields**: ✅ All 16 updatable fields available (excludes `id`, `tenant_id`, `created_at`, `updated_at`)

## Use Cases

### 1. Temporary Booking Suspension
```http
# Temporarily disable bookings during maintenance
PUT /api/agents/{agent_id}
{"booking_enabled": false}

# Re-enable after maintenance
PUT /api/agents/{agent_id}
{"booking_enabled": true}
```

### 2. Agent-Specific Booking Control
```http
# Only certain agents can accept bookings
PUT /api/agents/customer-service-agent
{"booking_enabled": true}

PUT /api/agents/information-only-agent
{"booking_enabled": false}
```

### 3. Gradual Rollout
```http
# Enable booking for agents one by one
PUT /api/agents/pilot-agent-1
{"booking_enabled": true}

# Others remain disabled until ready
PUT /api/agents/agent-2
{"booking_enabled": false}
```

## Benefits

1. **Fine-Grained Control**: Enable/disable booking per agent
2. **Operational Flexibility**: Quickly suspend booking for maintenance or issues
3. **Gradual Rollouts**: Enable calendar features incrementally
4. **View Access Preserved**: Agents can still view existing appointments even when booking is disabled
5. **Backward Compatible**: Defaults to `true` for existing agents

## Migration Instructions

### To Apply Changes:
1. **Run Migration**: `alembic upgrade head`
2. **Verify Settings**: All existing agents will have `booking_enabled = true` by default
3. **Configure as Needed**: Update specific agents to disable booking if required

### Example Configuration:
```bash
# Check current status
curl "http://localhost:8000/api/tenants/tenant123/agents/agent456"

# Disable booking for specific agent
curl -X PUT "http://localhost:8000/api/tenants/tenant123/agents/agent456" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"booking_enabled": false}'

# Verify change
curl "http://localhost:8000/api/tenants/tenant123/agents/agent456" | grep booking_enabled
```

## Files Modified

1. **`app/models/database.py`** - Added `booking_enabled` column to Agent model
2. **`app/api/user_endpoints.py`** - Updated schemas to include all database fields
3. **`app/api/admin_endpoints.py`** - Updated schemas to include all database fields
4. **`app/tools/calendar_tools.py`** - Added booking validation to create/cancel/update operations
5. **`alembic/versions/3b48e4a7f421_add_booking_enabled_field_to_agents.py`** - Database migration

## Technical Notes

- **Default Value**: `true` to maintain backward compatibility
- **Validation**: Applied to modification operations (create, cancel, update) but not view operations (search, list)
- **Error Handling**: Clear error messages when booking is disabled
- **Performance**: No impact on view-only operations
- **Database**: Uses PostgreSQL Boolean type with proper indexing