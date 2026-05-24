from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

router = APIRouter()
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/health")
async def health(db: DbDep):
    result = await db.execute(text("SELECT 1"))
    db_ok = result.scalar() == 1
    return {"status": "ok", "db": db_ok}
