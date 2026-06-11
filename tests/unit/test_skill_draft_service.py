import pytest

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.skill import Skill
from app.models.user import User
from app.services.skill_draft_service import SkillDraftService
from app.services.skill_service import SkillService
from app.workspace.paths import tenant_root


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("/skill create json csv to table", "json csv to table"),
        ("/做技能 把 json 数据 csv 转换成表格", "把 json 数据 csv 转换成表格"),
        (
            "帮我建一个 skill，通过 json 数据cvs 转换成表格",
            "通过 json 数据cvs 转换成表格",
        ),
        (
            "请帮我创建一个技能：把 json 数据 csv 转成表格",
            "把 json 数据 csv 转成表格",
        ),
        (
            "create a skill that converts json/csv data into a table",
            "that converts json/csv data into a table",
        ),
    ],
)
def test_parse_create_intent_matches_supported_patterns(content: str, expected: str):
    assert SkillDraftService.parse_create_intent(content) == expected


@pytest.mark.parametrize(
    "content",
    [
        "这个 skill 怎么用？",
        "skills 页面在哪",
        "把这个表格导出一下",
        "hello world",
    ],
)
def test_parse_create_intent_ignores_non_creation_messages(content: str):
    assert SkillDraftService.parse_create_intent(content) is None


@pytest.mark.asyncio
async def test_commit_draft_marks_chat_skill_card_saved(db_session, monkeypatch):
    user = User(id='u-skill-draft', username='skilldraft', password_hash='x', role='agent')
    conversation = Conversation(id='conv-skill-draft', user_id=user.id, title='Skill chat', status='active')
    message = Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role='assistant',
        content='已从对话生成技能草稿 **json-csv-to-table**，确认后保存到技能库。',
        extra_data={
            'skill_draft': {
                'type': 'skill_draft',
                'draft_id': 'draft-skill-1',
                'name': 'json-csv-to-table',
                'file_count': 1,
            }
        },
    )
    db_session.add_all([user, conversation, message])
    await db_session.flush()

    service = SkillDraftService(db_session)
    service._write_draft_files(
        user.id,
        'draft-skill-1',
        {'SKILL.md': '---\nname: json-csv-to-table\ndescription: "demo"\ntype: tool\n---\n'},
    )
    service._save_manifest(
        user.id,
        'draft-skill-1',
        {
            'id': 'draft-skill-1',
            'user_id': user.id,
            'conversation_id': conversation.id,
            'name': 'json-csv-to-table',
            'description': 'demo',
            'skill_type': 'tool',
            'status': 'draft',
            'created_at': '2026-06-07T00:00:00+00:00',
            'updated_at': '2026-06-07T00:00:00+00:00',
        },
    )

    async def fake_require_authoring(_: str) -> None:
        return None

    async def fake_reload_skills(self, user_id: str):
        existing = await self.db.get(Skill, 'saved-skill-1')
        if existing is None:
            self.db.add(
                Skill(
                    id='saved-skill-1',
                    user_id=user_id,
                    name='json-csv-to-table',
                    description='demo',
                    skill_type='tool',
                    path=str(SkillService._skills_root(user_id) / 'json-csv-to-table' / 'SKILL.md'),
                )
            )
            await self.db.flush()
        return {}

    async def fake_refresh_storage_usage(self, user_id: str) -> None:
        return None

    monkeypatch.setattr(service, '_require_authoring', fake_require_authoring)
    monkeypatch.setattr(SkillService, 'reload_skills', fake_reload_skills)
    monkeypatch.setattr(SkillService, '_refresh_storage_usage', fake_refresh_storage_usage)

    try:
        skill = await service.commit_draft(user.id, 'draft-skill-1', bind_channel=False)

        await db_session.refresh(message)
        skill_draft = message.extra_data['skill_draft']
        assert skill.name == 'json-csv-to-table'
        assert skill_draft['status'] == 'committed'
        assert skill_draft['saved_skill'] == {
            'id': 'saved-skill-1',
            'name': 'json-csv-to-table',
        }
    finally:
        import shutil

        shutil.rmtree(tenant_root(user.id), ignore_errors=True)