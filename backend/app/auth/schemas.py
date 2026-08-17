import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info):
        if info.data.get("password") is not None and v != info.data["password"]:
            raise ValueError("Passwords do not match.")
        return v


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    id: uuid.UUID
    full_name: str
    username: str
    email: str
    is_active: bool
    face_enrolled: bool

    model_config = {"from_attributes": True}


class AuthStageResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    stage: str
    user: UserOut
