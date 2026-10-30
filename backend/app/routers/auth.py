from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import get_db, users
from ..schemas import AuthOut, LoginIn, RegisterIn, UserOut
from ..security import create_token, current_user_id, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthOut, status_code=201)
def register(body: RegisterIn, conn: Connection = Depends(get_db)):
    user_id = uuid4().hex
    created = conn.execute(
        pg_insert(users)
        .values(id=user_id, email=body.email, name=body.name, password_hash=hash_password(body.password))
        .on_conflict_do_nothing(index_elements=["email"])
        .returning(users.c.id)
    ).first()
    if not created:
        raise HTTPException(409, "An account with this email already exists")
    user = UserOut(id=user_id, name=body.name, email=body.email)
    return AuthOut(token=create_token(user_id, body.email), user=user)


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, conn: Connection = Depends(get_db)):
    row = conn.execute(select(users).where(users.c.email == body.email)).first()
    if not row or not verify_password(body.password, row.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    user = UserOut(id=row.id, name=row.name, email=row.email)
    return AuthOut(token=create_token(user.id, user.email), user=user)


@router.get("/me", response_model=UserOut)
def me(user_id: str = Depends(current_user_id), conn: Connection = Depends(get_db)):
    row = conn.execute(select(users).where(users.c.id == user_id)).first()
    if not row:
        raise HTTPException(401, "Account not found")
    return UserOut(id=row.id, name=row.name, email=row.email)
