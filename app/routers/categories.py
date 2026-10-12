"""Categories CRUD (owner-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.db import get_session
from app.deps import require_csrf, require_login, require_owner
from app.models import Category, Product
from app.templates import templates

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
def list_categories(
    request: Request,
    session: Session = Depends(get_session),
    _user=Depends(require_login),
):
    cats = session.exec(select(Category).order_by(Category.name)).all()
    return templates.TemplateResponse(request, "categories/list.html.j2", {"categories": cats})


@router.post("", dependencies=[Depends(require_csrf), Depends(require_owner)])
def create_category(
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    existing = session.exec(select(Category).where(Category.name == name)).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"category '{name}' already exists")
    session.add(Category(name=name))
    session.commit()
    return RedirectResponse(url="/categories", status_code=303)


@router.post("/{category_id}/delete", dependencies=[Depends(require_csrf), Depends(require_owner)])
def delete_category(
    category_id: int,
    session: Session = Depends(get_session),
):
    cat = session.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="category not found")
    in_use = session.exec(select(Product).where(Product.category_id == category_id)).first()
    if in_use:
        raise HTTPException(status_code=400, detail="category in use by products")
    session.delete(cat)
    session.commit()
    return RedirectResponse(url="/categories", status_code=303)
