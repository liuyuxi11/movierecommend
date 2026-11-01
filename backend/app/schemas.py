import re
from datetime import date
from typing import List, Literal
from pydantic import AliasChoices, BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional

class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="昵称")
    password: str = Field(..., min_length=8, max_length=255, description="密码")
    confirm_password: str = Field(..., min_length=8, max_length=255, description="确认密码")
    email: EmailStr = Field(..., max_length=254, description="邮箱")
    phone: str = Field(..., min_length=1, max_length=32, description="手机号")
    avatar: Optional[str] = Field(None, max_length=1000, description="头像URL")

    @field_validator("username", "phone", mode="before")
    @classmethod
    def strip_identity_fields(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def password_strength(cls, value):
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("密码必须同时包含字母和数字")
        return value

    @field_validator("phone")
    @classmethod
    def phone_must_be_digits(cls, value):
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError("手机号必须全部为数字")
        return value

    @model_validator(mode="after")
    def check_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self
    
class UserLogin(BaseModel):
    account: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("account", "username"),
        description="手机号/邮箱/昵称",
    )
    password: str = Field(..., description="密码")

    @field_validator("account", mode="before")
    @classmethod
    def strip_account(cls, value):
        return value.strip() if isinstance(value, str) else value

class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[EmailStr] = Field(None, max_length=254)
    phone: Optional[str] = Field(None, min_length=1, max_length=32)
    avatar: Optional[str] = Field(None, max_length=1000)

    @field_validator("username", "phone", mode="before")
    @classmethod
    def strip_identity_fields(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).strip().lower() if value is not None else value

    @field_validator("phone")
    @classmethod
    def phone_must_be_digits(cls, value):
        if value is not None and not re.fullmatch(r"[0-9]+", value):
            raise ValueError("手机号必须全部为数字")
        return value


    @model_validator(mode="after")
    def require_contact_fields_to_remain_set(self):
        for field_name in ("username", "email", "phone"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能为空")
        return self


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)

class UserChangePassword(BaseModel):
    old_password: str = Field(..., description="原密码")
    new_password: str = Field(..., min_length=8, max_length=255, description="新密码")

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value):
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("密码必须同时包含字母和数字")
        return value

class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(..., max_length=254, description="\u7528\u4e8e\u63a5\u6536\u9a8c\u8bc1\u7801\u7684\u90ae\u7bb1")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).strip().lower()


class PasswordResetConfirm(BaseModel):
    email: EmailStr = Field(..., max_length=254)
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).strip().lower()

    @field_validator("code")
    @classmethod
    def code_must_be_digits(cls, value):
        if not value.isdigit():
            raise ValueError("\u9a8c\u8bc1\u7801\u5fc5\u987b\u662f 6 \u4f4d\u6570\u5b57")
        return value

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, value):
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("\u5bc6\u7801\u5fc5\u987b\u540c\u65f6\u5305\u542b\u5b57\u6bcd\u548c\u6570\u5b57")
        return value


class AdminCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="管理员账号")
    password: str = Field(..., min_length=8, max_length=255, description="管理员密码")
    role: Literal["admin", "superadmin"] = Field(
        ..., description="admin 为普通管理员，superadmin 为超级管理员"
    )

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def password_strength(cls, value):
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("密码必须同时包含字母和数字")
        return value


class AdminLogin(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=1, max_length=255)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value):
        return value.strip() if isinstance(value, str) else value


class AdminAccountUpdate(BaseModel):
    role: Optional[Literal["admin", "superadmin"]] = None
    status: Optional[Literal["active", "disabled"]] = None


class UserAdminUpdate(BaseModel):
    status: Literal["active", "disabled"]


class MovieCreate(BaseModel):
    # movieinfo.movieid is a required, non-auto-increment primary key in the
    # existing database, so callers must provide the dataset/movie identifier.
    movieid: int = Field(..., gt=0)
    moviename: str = Field(..., min_length=1, max_length=1000)
    releasetime: Optional[date] = None
    director: Optional[str] = Field(None, max_length=1000)
    leadactors: Optional[str] = Field(None, max_length=1000)
    picture: Optional[str] = Field(None, max_length=1000)
    description: Optional[str] = Field(None, max_length=1000)
    typelist: Optional[str] = Field(None, max_length=255)
    category_ids: List[int] = Field(default_factory=list, max_length=100)

    @field_validator("moviename", mode="before")
    @classmethod
    def clean_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class MovieUpdate(BaseModel):
    moviename: Optional[str] = Field(None, min_length=1, max_length=1000)
    releasetime: Optional[date] = None
    director: Optional[str] = Field(None, max_length=1000)
    leadactors: Optional[str] = Field(None, max_length=1000)
    picture: Optional[str] = Field(None, max_length=1000)
    description: Optional[str] = Field(None, max_length=1000)
    typelist: Optional[str] = Field(None, max_length=255)
    category_ids: Optional[List[int]] = Field(None, max_length=100)

    @field_validator("moviename", mode="before")
    @classmethod
    def clean_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class CategoryUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class RatingSubmit(BaseModel):
    # Optional for clients using the previous contract; the server always uses
    # the authenticated user and rejects a mismatched value.
    userid: Optional[int] = None
    movieids: List[int] = Field(..., min_length=1)
    ratings: List[int] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_rating_batch(self):
        if self.userid is not None and self.userid < 1:
            raise ValueError("userid 必须为正整数")
        if len(self.movieids) != len(self.ratings):
            raise ValueError("movieids 和 ratings 数量必须一致")
        if any(movieid < 1 for movieid in self.movieids):
            raise ValueError("movieid 必须为正整数")
        if len(set(self.movieids)) != len(self.movieids):
            raise ValueError("同一批次不能重复提交同一部电影")
        if any(rating < 1 or rating > 10 for rating in self.ratings):
            raise ValueError("评分必须在 1 到 10 之间")
        return self


class CommentCreate(BaseModel):
    movieid: int = Field(..., gt=0)
    content: str = Field(..., min_length=1, max_length=500)

    @field_validator("content", mode="before")
    @classmethod
    def clean_content(cls, value):
        return value.strip() if isinstance(value, str) else value


class ReportCreate(BaseModel):
    reason_code: Literal[
        "malicious_attack", "insulting_language", "harmful_information",
        "excessive_promotion", "advertisement", "other"
    ]
    reason_detail: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_other_detail(self):
        if self.reason_code == "other" and not (self.reason_detail or "").strip():
            raise ValueError("选择 other 时必须填写 reason_detail")
        if self.reason_code != "other":
            self.reason_detail = None
        return self


class ReportDecision(BaseModel):
    status: Literal["accepted", "rejected"]
