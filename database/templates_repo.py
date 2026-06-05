"""CRUD для шаблонов контента и черновиков."""
from datetime import datetime

from sqlalchemy import select

from database.models import ContentPost, ContentTemplate
from database.session import async_session_factory


async def create_template(name: str, text: str, photo_file_id: str | None = None) -> ContentTemplate:
    async with async_session_factory() as session:
        t = ContentTemplate(
            name=name,
            text=text,
            photo_file_id=photo_file_id,
            enabled=True,
        )
        session.add(t)
        await session.commit()
        await session.refresh(t)
        return t


async def list_templates(only_enabled: bool = False) -> list[ContentTemplate]:
    async with async_session_factory() as session:
        q = select(ContentTemplate).order_by(ContentTemplate.id.desc())
        if only_enabled:
            q = q.where(ContentTemplate.enabled.is_(True))
        result = await session.execute(q)
        return list(result.scalars().all())


async def get_template(template_id: int) -> ContentTemplate | None:
    async with async_session_factory() as session:
        return await session.get(ContentTemplate, template_id)


async def delete_template(template_id: int) -> bool:
    async with async_session_factory() as session:
        t = await session.get(ContentTemplate, template_id)
        if not t:
            return False
        await session.delete(t)
        await session.commit()
        return True


async def toggle_template(template_id: int) -> ContentTemplate | None:
    async with async_session_factory() as session:
        t = await session.get(ContentTemplate, template_id)
        if not t:
            return None
        t.enabled = not t.enabled
        await session.commit()
        await session.refresh(t)
        return t


async def create_post(
    template_id: int,
    admin_chat_id: int,
    admin_message_id: int,
    rendered_text: str,
    scheduled_slot: str,
) -> ContentPost:
    async with async_session_factory() as session:
        p = ContentPost(
            template_id=template_id,
            admin_chat_id=admin_chat_id,
            admin_message_id=admin_message_id,
            rendered_text=rendered_text,
            status="draft",
            scheduled_slot=scheduled_slot,
        )
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p


async def get_post_by_admin_msg(admin_chat_id: int, admin_message_id: int) -> ContentPost | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ContentPost).where(
                ContentPost.admin_chat_id == admin_chat_id,
                ContentPost.admin_message_id == admin_message_id,
            )
        )
        return result.scalar_one_or_none()


async def update_post_status(post_id: int, status: str) -> None:
    async with async_session_factory() as session:
        p = await session.get(ContentPost, post_id)
        if not p:
            return
        p.status = status
        p.actioned_at = datetime.utcnow()
        await session.commit()
