"""CRUD для библиотеки картинок."""
import random

from sqlalchemy import func, select

from database.models import ContentImage
from database.session import async_session_factory


async def add_image(file_id: str, category: str | None, description: str | None) -> ContentImage:
    async with async_session_factory() as session:
        img = ContentImage(
            file_id=file_id,
            category=(category or None),
            description=(description or None),
        )
        session.add(img)
        await session.commit()
        await session.refresh(img)
        return img


async def list_images(category: str | None = None) -> list[ContentImage]:
    async with async_session_factory() as session:
        q = select(ContentImage).order_by(ContentImage.id.desc())
        if category is not None:
            q = q.where(ContentImage.category == category)
        result = await session.execute(q)
        return list(result.scalars().all())


async def get_image(image_id: int) -> ContentImage | None:
    async with async_session_factory() as session:
        return await session.get(ContentImage, image_id)


async def delete_image(image_id: int) -> bool:
    async with async_session_factory() as session:
        img = await session.get(ContentImage, image_id)
        if not img:
            return False
        await session.delete(img)
        await session.commit()
        return True


async def random_for_category(category: str | None) -> ContentImage | None:
    """Случайная картинка из категории (или из категории + пул без категории)."""
    async with async_session_factory() as session:
        if category:
            q = select(ContentImage).where(
                (ContentImage.category == category) | (ContentImage.category.is_(None))
            )
        else:
            q = select(ContentImage)
        result = await session.execute(q)
        items = list(result.scalars().all())
        return random.choice(items) if items else None


async def counts_by_category() -> dict[str, int]:
    async with async_session_factory() as session:
        q = select(ContentImage.category, func.count(ContentImage.id)).group_by(ContentImage.category)
        result = await session.execute(q)
        return {(row[0] or "без категории"): int(row[1]) for row in result.all()}
