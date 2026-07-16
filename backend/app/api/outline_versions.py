"""Canonical registration point for outline versions and DHO candidates."""

from fastapi import APIRouter

from app.api.chapter_versions import router as versions_router
from app.api.outline_revision import router as candidates_router

router = APIRouter()
router.include_router(versions_router)
router.include_router(candidates_router)
