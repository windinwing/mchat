"""Workflow template marketplace and sharing."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.models.workflow import SkillWorkflowTemplate
from app.schemas.workflow import WorkflowTemplateVisibilityUpdate
from app.services.workflow_service import WorkflowService


@pytest.mark.asyncio
async def test_marketplace_lists_shared_templates(db_session):
    owner = User(id="u-owner", username="owner1", password_hash="x", role="agent")
    viewer = User(id="u-view", username="viewer1", password_hash="x", role="user")
    db_session.add_all([owner, viewer])
    await db_session.flush()
    db_session.add(
        SkillWorkflowTemplate(
            id="tpl-shared",
            user_id=owner.id,
            name="Shared flow",
            description="demo",
            category="custom",
            graph_json={"version": 1, "nodes": [{"id": "a"}], "edges": []},
            visibility="shared",
        )
    )
    db_session.add(
        SkillWorkflowTemplate(
            id="tpl-private",
            user_id=owner.id,
            name="Private flow",
            description="hidden",
            category="custom",
            graph_json={"version": 1, "nodes": [], "edges": []},
            visibility="private",
        )
    )
    await db_session.flush()

    svc = WorkflowService(db_session)
    market = await svc.list_marketplace(user_id=viewer.id, locale="zh")
    ids = {t.id for t in market.community}
    assert "tpl-shared" in ids
    assert "tpl-private" not in ids
    assert any(t.author_name == "owner1" for t in market.community)


@pytest.mark.asyncio
async def test_create_from_shared_template_for_other_user(db_session):
    owner = User(id="u-own2", username="owner2", password_hash="x", role="agent")
    viewer = User(id="u-view2", username="viewer2", password_hash="x", role="agent")
    db_session.add_all([owner, viewer])
    await db_session.flush()
    tpl = SkillWorkflowTemplate(
        id="tpl-use",
        user_id=owner.id,
        name="Use me",
        description="",
        category="custom",
        graph_json={
            "version": 1,
            "nodes": [
                {"id": "start", "type": "start", "name": "Start", "config": {}},
                {"id": "end", "type": "end", "name": "End", "config": {}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        },
        visibility="shared",
        use_count=0,
    )
    db_session.add(tpl)
    await db_session.flush()

    svc = WorkflowService(db_session)
    wf = await svc.create_from_template(
        user_id=viewer.id,
        template_id="tpl-use",
        name="Cloned",
    )
    assert wf.name == "Cloned"
    await db_session.refresh(tpl)
    assert tpl.use_count == 1


@pytest.mark.asyncio
async def test_private_template_not_accessible_to_others(db_session):
    owner = User(id="u-own3", username="owner3", password_hash="x", role="agent")
    viewer = User(id="u-view3", username="viewer3", password_hash="x", role="agent")
    db_session.add_all([owner, viewer])
    await db_session.flush()
    db_session.add(
        SkillWorkflowTemplate(
            id="tpl-sec",
            user_id=owner.id,
            name="Secret",
            description="",
            category="custom",
            graph_json={"version": 1, "nodes": [], "edges": []},
            visibility="private",
        )
    )
    await db_session.flush()

    svc = WorkflowService(db_session)
    with pytest.raises(HTTPException) as exc:
        await svc.create_from_template(
            user_id=viewer.id,
            template_id="tpl-sec",
            name="Nope",
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_owner_can_toggle_visibility(db_session):
    owner = User(id="u-own4", username="owner4", password_hash="x", role="agent")
    db_session.add(owner)
    await db_session.flush()
    tpl = SkillWorkflowTemplate(
        id="tpl-toggle",
        user_id=owner.id,
        name="Toggle",
        description="",
        category="custom",
        graph_json={"version": 1, "nodes": [], "edges": []},
        visibility="private",
    )
    db_session.add(tpl)
    await db_session.flush()

    svc = WorkflowService(db_session)
    updated = await svc.update_template_visibility(
        user_id=owner.id,
        user_role="agent",
        template_id="tpl-toggle",
        data=WorkflowTemplateVisibilityUpdate(visibility="shared"),
    )
    assert updated.visibility == "shared"
