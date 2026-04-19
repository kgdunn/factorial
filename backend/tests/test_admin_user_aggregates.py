"""Integration test for ``admin_service.list_users`` aggregation rollups."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import ColumnDefault
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base

# Importing all models so SQLite creates every table the aggregation query needs.
from app.models.admin_event import AdminEvent  # noqa: F401
from app.models.conversation import ChatEvent, Conversation, Message, ToolCall  # noqa: F401
from app.models.experiment import Experiment
from app.models.experiment_share import ExperimentShare  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.setup_token import SetupToken  # noqa: F401
from app.models.signup_request import SignupRequest
from app.models.tool_usage import ToolUsage  # noqa: F401
from app.models.user import User
from app.models.user_balance import UserBalance
from app.models.user_feedback import UserFeedback
from app.services import admin_service


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    for table in Base.metadata.tables.values():
        for col in table.columns:
            if col.server_default is not None and "gen_random_uuid" in str(getattr(col.server_default, "arg", "")):
                col.server_default = None
                col.default = ColumnDefault(uuid.uuid4)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_list_users_returns_zeroed_aggregates_for_new_user(db_session: AsyncSession) -> None:
    user = User(
        email="nobody@example.com",
        password_hash="x",  # noqa: S106 — fixture-only
    )
    db_session.add(user)
    await db_session.flush()

    users, aggregates, total = await admin_service.list_users(db_session)
    assert total == 1
    assert len(users) == 1
    agg = aggregates[user.id]
    assert agg.total_cost_usd == Decimal("0")
    assert agg.total_tokens == 0
    assert agg.conversation_count == 0
    assert agg.feedback_count == 0
    assert agg.open_experiments == 0
    assert agg.avg_runs_per_experiment is None
    assert agg.balance_usd is None
    assert agg.signup_status is None


async def test_list_users_rolls_up_conversation_feedback_experiment_balance_signup(
    db_session: AsyncSession,
) -> None:
    user = User(
        email="heavy@example.com",
        password_hash="x",  # noqa: S106 — fixture-only
    )
    db_session.add(user)
    await db_session.flush()

    db_session.add_all(
        [
            Conversation(
                user_id=user.id,
                total_input_tokens=100,
                total_output_tokens=200,
                total_cost_usd=Decimal("1.25"),
                total_markup_cost_usd=Decimal("1.87"),
            ),
            Conversation(
                user_id=user.id,
                total_input_tokens=50,
                total_output_tokens=75,
                total_cost_usd=Decimal("0.50"),
                total_markup_cost_usd=Decimal("0.75"),
            ),
            UserFeedback(user_id=user.id, topic="bug", message="abcdefghij"),
            UserFeedback(user_id=user.id, topic="bug", message="abcdefghij"),
            UserFeedback(user_id=user.id, topic="bug", message="abcdefghij"),
            Experiment(user_id=user.id, status="draft", results_data=[{"r": 1}, {"r": 2}]),
            Experiment(user_id=user.id, status="draft", results_data=[{"r": 1}, {"r": 2}, {"r": 3}, {"r": 4}]),
            Experiment(user_id=user.id, status="completed", results_data=[{"r": 1}]),
            UserBalance(user_id=user.id, balance_usd=Decimal("10.0000"), balance_tokens=5_000_000),
            SignupRequest(
                email="heavy@example.com",
                use_case="testing",
                status="registered",
                accepted_disclaimers=True,
            ),
        ]
    )
    await db_session.flush()

    _users, aggregates, _total = await admin_service.list_users(db_session)
    agg = aggregates[user.id]

    assert agg.conversation_count == 2
    assert agg.total_tokens == 100 + 200 + 50 + 75
    assert agg.total_cost_usd == Decimal("1.75")
    assert agg.total_markup_cost_usd == Decimal("2.62")

    assert agg.feedback_count == 3

    assert agg.open_experiments == 2  # completed excluded
    assert agg.avg_runs_per_experiment is not None
    # (2 + 4 + 1) / 3 across ALL experiments, including the completed one
    assert abs(agg.avg_runs_per_experiment - (7 / 3)) < 1e-6

    assert agg.balance_usd == Decimal("10.0000")
    assert agg.balance_tokens == 5_000_000

    assert agg.signup_status == "registered"
    assert agg.disclaimers_accepted is True
