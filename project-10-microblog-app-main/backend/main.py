import json
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Annotated, Optional
import aiofiles
# --- добавлено для SQLAlchemy ---
from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
import os
from fastapi import Response

app = FastAPI()

# --- CORS ---
origins = ["http://localhost:3000"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- SQLAlchemy setup ---
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "app.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Модели SQLAlchemy ---
class UserDB(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    posts = relationship("PostDB", back_populates="owner")
    likes = relationship("LikeDB", back_populates="user")

class PostDB(Base):
    __tablename__ = "posts"
    id = Column(String, primary_key=True, index=True)
    text = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    owner_username = Column(String, nullable=False)
    owner = relationship("UserDB", back_populates="posts")
    likes = relationship("LikeDB", back_populates="post")

class LikeDB(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    post_id = Column(String, ForeignKey("posts.id"), nullable=False)
    user = relationship("UserDB", back_populates="likes")
    post = relationship("PostDB", back_populates="likes")
    __table_args__ = (UniqueConstraint('user_id', 'post_id', name='_user_post_uc'),)

# --- Pydantic модели ---
class Post(BaseModel):
    id: str
    text: str
    timestamp: datetime
    owner_id: str
    owner_username: str
    class Config:
        orm_mode = True

class PostCreate(BaseModel):
    text: str

class User(BaseModel):
    id: str
    username: str
    class Config:
        orm_mode = True

class PostWithLikes(Post):
    likes_count: int
    liked_by_me: Optional[bool] = False

# --- Фейковые данные пользователей (для аутентификации) ---
FAKE_USERS_DB = {
    "user1": {"id": "1", "username": "user1", "password": "password1"},
    "user2": {"id": "2", "username": "user2", "password": "password2"},
}

# --- Создание таблиц и начальных пользователей ---
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    for u in FAKE_USERS_DB.values():
        if not db.query(UserDB).filter_by(username=u["username"]).first():
            db.add(UserDB(id=u["id"], username=u["username"], password=u["password"]))
    db.commit()
    db.close()

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Аутентификация ---
async def get_current_user(authorization: Annotated[str, Header()], db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid scheme")
    token = authorization.split(" ")[1] # токен - это просто username
    user_db = db.query(UserDB).filter_by(username=token).first()
    if not user_db:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return User.from_orm(user_db)

@app.post("/api/login")
async def login(form_data: Dict[str, str], db: Session = Depends(get_db)):
    username = form_data.get("username")
    password = form_data.get("password")
    user = db.query(UserDB).filter_by(username=username).first()
    if not user or user.password != password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    return {"access_token": user.username, "token_type": "bearer", "user": {"id": user.id, "username": user.username}}

# --- Эндпоинты для постов ---
@app.get("/api/posts", response_model=List[PostWithLikes])
async def list_posts(db: Session = Depends(get_db), authorization: Optional[str] = Header(None)):
    posts = db.query(PostDB).order_by(PostDB.timestamp.desc()).all()
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        user = db.query(UserDB).filter_by(username=token).first()
        if user:
            user_id = user.id
    result = []
    for post in posts:
        likes_count = db.query(LikeDB).filter_by(post_id=post.id).count()
        liked_by_me = False
        if user_id:
            liked_by_me = db.query(LikeDB).filter_by(post_id=post.id, user_id=user_id).first() is not None
        result.append(PostWithLikes(
            id=post.id,
            text=post.text,
            timestamp=post.timestamp,
            owner_id=post.owner_id,
            owner_username=post.owner_username,
            likes_count=likes_count,
            liked_by_me=liked_by_me
        ))
    return result

@app.post("/api/posts", response_model=Post, status_code=201)
async def create_post(post_data: PostCreate, current_user: Annotated[User, Depends(get_current_user)], db: Session = Depends(get_db)):
    new_post = PostDB(
        id=str(uuid.uuid4()),
        text=post_data.text,
        timestamp=datetime.now(timezone.utc),
        owner_id=current_user.id,
        owner_username=current_user.username
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post

@app.delete("/api/posts/{post_id}", status_code=204)
async def delete_post(post_id: str, current_user: Annotated[User, Depends(get_current_user)], db: Session = Depends(get_db)):
    post = db.query(PostDB).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    if post.owner_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to delete this post")
    db.delete(post)
    db.commit()

# --- Эндпоинты для лайков ---
@app.post("/api/posts/{post_id}/like", status_code=201)
async def like_post(post_id: str, current_user: Annotated[User, Depends(get_current_user)], db: Session = Depends(get_db)):
    post = db.query(PostDB).filter_by(id=post_id).first()
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    # Проверяем, лайкал ли уже
    like = db.query(LikeDB).filter_by(user_id=current_user.id, post_id=post_id).first()
    if like:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Already liked")
    new_like = LikeDB(user_id=current_user.id, post_id=post_id)
    db.add(new_like)
    db.commit()
    return {"message": "Liked"}

@app.delete("/api/posts/{post_id}/like", status_code=204)
async def unlike_post(post_id: str, current_user: Annotated[User, Depends(get_current_user)], db: Session = Depends(get_db)):
    like = db.query(LikeDB).filter_by(user_id=current_user.id, post_id=post_id).first()
    if not like:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Like not found")
    db.delete(like)
    db.commit()
    return Response(status_code=204)

# --- Эндпоинт для получения постов пользователя ---
@app.get("/api/users/{username}/posts", response_model=List[PostWithLikes])
async def get_user_posts(username: str, db: Session = Depends(get_db), authorization: Optional[str] = Header(None)):
    user = db.query(UserDB).filter_by(username=username).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    posts = db.query(PostDB).filter_by(owner_id=user.id).order_by(PostDB.timestamp.desc()).all()
    user_id = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        auth_user = db.query(UserDB).filter_by(username=token).first()
        if auth_user:
            user_id = auth_user.id
    result = []
    for post in posts:
        likes_count = db.query(LikeDB).filter_by(post_id=post.id).count()
        liked_by_me = False
        if user_id:
            liked_by_me = db.query(LikeDB).filter_by(post_id=post.id, user_id=user_id).first() is not None
        result.append(PostWithLikes(
            id=post.id,
            text=post.text,
            timestamp=post.timestamp,
            owner_id=post.owner_id,
            owner_username=post.owner_username,
            likes_count=likes_count,
            liked_by_me=liked_by_me
        ))
    return result