"""Read-only sqladmin ``ModelView`` classes for every persisted model.

All views inherit from :class:`ReadOnlyView`, which disables every
mutation in the UI. Sensitive columns (``users.password_hash``,
``setup_tokens.token``, ``signup_requests.invite_token``) are excluded
from list AND detail rendering. JSONB / JSON columns are pretty-printed
on the detail page so an operator can actually read them.
"""

from __future__ import annotations

import json
from typing import Any

from sqladmin import ModelView

from app.models.admin_event import AdminEvent
from app.models.conversation import ChatEvent, Conversation, Message, ToolCall
from app.models.experiment import Experiment
from app.models.experiment_share import ExperimentShare
from app.models.role import Role
from app.models.setup_token import SetupToken
from app.models.signup_request import SignupRequest
from app.models.simulator import Simulator
from app.models.tool_usage import ToolUsage
from app.models.user import User
from app.models.user_balance import UserBalance
from app.models.user_feedback import UserFeedback


def _pretty(value: Any) -> str:
    if value is None:
        return ""
    try:
        return json.dumps(value, indent=2, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


class ReadOnlyView(ModelView):
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    can_view_details = True
    page_size = 50
    page_size_options = [25, 50, 100, 200]


class UserAdmin(ReadOnlyView, model=User):
    name = "User"
    name_plural = "Users"
    category = "Identity"
    icon = "fa-solid fa-user"
    column_list = [
        User.email,
        User.display_name,
        User.is_admin,
        User.is_active,
        User.role_id,
        User.last_login_at,
        User.country,
        User.created_at,
    ]
    column_details_exclude_list = [User.password_hash]
    column_searchable_list = [User.email, User.display_name]
    column_sortable_list = [User.email, User.created_at, User.last_login_at, User.is_admin]
    column_default_sort = [(User.created_at, True)]


class RoleAdmin(ReadOnlyView, model=Role):
    name = "Role"
    name_plural = "Roles"
    category = "Identity"
    icon = "fa-solid fa-id-badge"
    column_list = [Role.name, Role.description, Role.is_builtin, Role.created_at]
    column_searchable_list = [Role.name]
    column_sortable_list = [Role.name, Role.created_at]


class SignupRequestAdmin(ReadOnlyView, model=SignupRequest):
    name = "Signup request"
    name_plural = "Signup requests"
    category = "Identity"
    icon = "fa-solid fa-user-plus"
    column_list = [
        SignupRequest.email,
        SignupRequest.status,
        SignupRequest.requested_role,
        SignupRequest.role_id,
        SignupRequest.accepted_disclaimers,
        SignupRequest.created_at,
    ]
    # Hide the live invite token everywhere — possession of it grants account
    # creation. The expiry timestamp stays visible so operators can confirm
    # whether a pending invite is still valid.
    column_details_exclude_list = [SignupRequest.invite_token]
    column_searchable_list = [SignupRequest.email]
    column_sortable_list = [SignupRequest.email, SignupRequest.status, SignupRequest.created_at]
    column_default_sort = [(SignupRequest.created_at, True)]


class SetupTokenAdmin(ReadOnlyView, model=SetupToken):
    name = "Setup token"
    name_plural = "Setup tokens"
    category = "Identity"
    icon = "fa-solid fa-key"
    column_list = [
        SetupToken.user_id,
        SetupToken.purpose,
        SetupToken.expires_at,
        SetupToken.used_at,
        SetupToken.created_at,
    ]
    # Possession of this token resets a password — never expose it.
    column_details_exclude_list = [SetupToken.token]
    column_sortable_list = [SetupToken.created_at, SetupToken.expires_at, SetupToken.used_at]
    column_default_sort = [(SetupToken.created_at, True)]


class UserBalanceAdmin(ReadOnlyView, model=UserBalance):
    name = "User balance"
    name_plural = "User balances"
    category = "Identity"
    icon = "fa-solid fa-coins"
    column_list = [
        UserBalance.user_id,
        UserBalance.balance_usd,
        UserBalance.balance_tokens,
        UserBalance.updated_at,
    ]
    column_sortable_list = [UserBalance.balance_usd, UserBalance.balance_tokens, UserBalance.updated_at]


class ConversationAdmin(ReadOnlyView, model=Conversation):
    name = "Conversation"
    name_plural = "Conversations"
    category = "Chat"
    icon = "fa-solid fa-comments"
    column_list = [
        Conversation.id,
        Conversation.user_id,
        Conversation.title,
        Conversation.status,
        Conversation.model_key,
        Conversation.message_count,
        Conversation.total_input_tokens,
        Conversation.total_output_tokens,
        Conversation.total_cost_usd,
        Conversation.starred,
        Conversation.created_at,
        Conversation.updated_at,
    ]
    column_searchable_list = [Conversation.title, Conversation.summary]
    column_sortable_list = [
        Conversation.created_at,
        Conversation.updated_at,
        Conversation.message_count,
        Conversation.total_cost_usd,
    ]
    column_default_sort = [(Conversation.updated_at, True)]


class MessageAdmin(ReadOnlyView, model=Message):
    name = "Message"
    name_plural = "Messages"
    category = "Chat"
    icon = "fa-solid fa-message"
    column_list = [
        Message.id,
        Message.conversation_id,
        Message.sequence,
        Message.role,
        Message.tool_name,
        Message.is_tool_result,
        Message.input_tokens,
        Message.output_tokens,
        Message.model_used,
        Message.created_at,
    ]
    column_sortable_list = [Message.created_at, Message.sequence]
    column_default_sort = [(Message.created_at, True)]
    column_formatters_detail = {
        Message.tool_input: lambda m, _a: _pretty(m.tool_input),
        Message.extra: lambda m, _a: _pretty(m.extra),
    }


class ToolCallAdmin(ReadOnlyView, model=ToolCall):
    name = "Tool call"
    name_plural = "Tool calls"
    category = "Chat"
    icon = "fa-solid fa-wrench"
    column_list = [
        ToolCall.id,
        ToolCall.conversation_id,
        ToolCall.tool_name,
        ToolCall.status,
        ToolCall.duration_ms,
        ToolCall.agent_turn,
        ToolCall.call_order,
        ToolCall.created_at,
    ]
    column_searchable_list = [ToolCall.tool_name]
    column_sortable_list = [ToolCall.created_at, ToolCall.duration_ms, ToolCall.tool_name]
    column_default_sort = [(ToolCall.created_at, True)]
    column_formatters_detail = {
        ToolCall.tool_input: lambda m, _a: _pretty(m.tool_input),
        ToolCall.tool_output: lambda m, _a: _pretty(m.tool_output),
    }


class ChatEventAdmin(ReadOnlyView, model=ChatEvent):
    name = "Chat event"
    name_plural = "Chat events"
    category = "Chat"
    icon = "fa-solid fa-bolt"
    column_list = [
        ChatEvent.id,
        ChatEvent.conversation_id,
        ChatEvent.turn_id,
        ChatEvent.sequence,
        ChatEvent.event_type,
        ChatEvent.created_at,
    ]
    column_sortable_list = [ChatEvent.created_at, ChatEvent.turn_id, ChatEvent.sequence]
    column_default_sort = [(ChatEvent.created_at, True)]
    column_formatters_detail = {
        ChatEvent.data: lambda m, _a: _pretty(m.data),
    }


class ExperimentAdmin(ReadOnlyView, model=Experiment):
    name = "Experiment"
    name_plural = "Experiments"
    category = "DOE"
    icon = "fa-solid fa-flask"
    column_list = [
        Experiment.id,
        Experiment.user_id,
        Experiment.name,
        Experiment.status,
        Experiment.design_type,
        Experiment.conversation_id,
        Experiment.created_at,
        Experiment.updated_at,
    ]
    column_searchable_list = [Experiment.name]
    column_sortable_list = [Experiment.created_at, Experiment.updated_at, Experiment.name]
    column_default_sort = [(Experiment.updated_at, True)]
    column_formatters_detail = {
        Experiment.factors: lambda m, _a: _pretty(m.factors),
        Experiment.design_data: lambda m, _a: _pretty(m.design_data),
        Experiment.results_data: lambda m, _a: _pretty(m.results_data),
        Experiment.evaluation_data: lambda m, _a: _pretty(m.evaluation_data),
    }


class ExperimentShareAdmin(ReadOnlyView, model=ExperimentShare):
    name = "Experiment share"
    name_plural = "Experiment shares"
    category = "DOE"
    icon = "fa-solid fa-share-nodes"
    column_list = [
        ExperimentShare.id,
        ExperimentShare.experiment_id,
        ExperimentShare.created_by,
        ExperimentShare.allow_results,
        ExperimentShare.expires_at,
        ExperimentShare.revoked_at,
        ExperimentShare.view_count,
        ExperimentShare.created_at,
    ]
    column_sortable_list = [ExperimentShare.created_at, ExperimentShare.view_count]
    column_default_sort = [(ExperimentShare.created_at, True)]


class SimulatorAdmin(ReadOnlyView, model=Simulator):
    name = "Simulator"
    name_plural = "Simulators"
    category = "DOE"
    icon = "fa-solid fa-dice"
    column_list = [
        Simulator.sim_id,
        Simulator.user_id,
        Simulator.conversation_id,
        Simulator.reveal_request_count,
        Simulator.created_at,
    ]
    column_searchable_list = [Simulator.sim_id]
    column_sortable_list = [Simulator.created_at, Simulator.reveal_request_count]
    column_default_sort = [(Simulator.created_at, True)]
    column_formatters_detail = {
        Simulator.public_summary: lambda m, _a: _pretty(m.public_summary),
        Simulator.private_state: lambda m, _a: _pretty(m.private_state),
    }


class AdminEventAdmin(ReadOnlyView, model=AdminEvent):
    name = "Admin event"
    name_plural = "Admin events"
    category = "Operations"
    icon = "fa-solid fa-clipboard-list"
    column_list = [
        AdminEvent.id,
        AdminEvent.event_type,
        AdminEvent.status,
        AdminEvent.source,
        AdminEvent.actor,
        AdminEvent.duration_ms,
        AdminEvent.created_at,
    ]
    column_searchable_list = [AdminEvent.event_type, AdminEvent.source, AdminEvent.actor]
    column_sortable_list = [AdminEvent.created_at, AdminEvent.event_type, AdminEvent.status]
    column_default_sort = [(AdminEvent.created_at, True)]
    column_formatters_detail = {
        AdminEvent.payload: lambda m, _a: _pretty(m.payload),
    }


class ToolUsageAdmin(ReadOnlyView, model=ToolUsage):
    name = "Tool usage (daily)"
    name_plural = "Tool usage (daily)"
    category = "Operations"
    icon = "fa-solid fa-gauge-high"
    column_list = [
        ToolUsage.user_id,
        ToolUsage.day,
        ToolUsage.cpu_seconds_used,
        ToolUsage.call_count,
        ToolUsage.updated_at,
    ]
    column_sortable_list = [ToolUsage.day, ToolUsage.cpu_seconds_used, ToolUsage.call_count]
    column_default_sort = [(ToolUsage.day, True)]


class UserFeedbackAdmin(ReadOnlyView, model=UserFeedback):
    name = "User feedback"
    name_plural = "User feedback"
    category = "Operations"
    icon = "fa-solid fa-comment-dots"
    column_list = [
        UserFeedback.id,
        UserFeedback.user_id,
        UserFeedback.topic,
        UserFeedback.app_version,
        UserFeedback.replied_at,
        UserFeedback.created_at,
    ]
    # Inline PNG bytes are big and unreadable in HTML; keep them out of the
    # list view but they remain on the detail page.
    column_searchable_list = [UserFeedback.topic, UserFeedback.message]
    column_sortable_list = [UserFeedback.created_at, UserFeedback.replied_at]
    column_default_sort = [(UserFeedback.created_at, True)]


ALL_VIEWS: list[type[ReadOnlyView]] = [
    UserAdmin,
    RoleAdmin,
    SignupRequestAdmin,
    SetupTokenAdmin,
    UserBalanceAdmin,
    ConversationAdmin,
    MessageAdmin,
    ToolCallAdmin,
    ChatEventAdmin,
    ExperimentAdmin,
    ExperimentShareAdmin,
    SimulatorAdmin,
    AdminEventAdmin,
    ToolUsageAdmin,
    UserFeedbackAdmin,
]
