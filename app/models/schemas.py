from pydantic import BaseModel
from typing import Optional


class ImageEditRequest(BaseModel):
    image1_url: str
    image2_url: str
    custom_prompt: Optional[str] = None


class ImageEditResponse(BaseModel):
    success: bool
    image_data: Optional[str] = None
    preview_url: Optional[str] = None
    message: str


class UploadPhotoResponse(BaseModel):
    success: bool
    image_url: Optional[str] = None
    message: str


class CartoonizeRequest(BaseModel):
    image_url: str  # 첫 번째 이미지 (얼굴 이미지, URL 또는 base64)
    character_id: str  # 캐릭터 ID
    custom_prompt: Optional[str] = None  # 포즈 묘사
    job_id: Optional[str] = None
    regeneration_count: Optional[int] = 2  # 재생성 횟수


class TimingInfo(BaseModel):
    character_image_fetch: Optional[float] = None
    step1_generation: Optional[float] = None
    step2_generation: Optional[float] = None
    background_removal: Optional[float] = None
    image_upload: Optional[float] = None
    total_time: Optional[float] = None


class CartoonizeResponse(BaseModel):
    success: bool
    result_image_url: Optional[str] = None  # 최종 결과물 (Supabase URL)
    background_removed_image_url: Optional[str] = None  # 배경 제거된 이미지 (Supabase URL)
    character_id: Optional[str] = None
    character_image_url: Optional[str] = None  # 캐릭터 이미지 URL
    timing: Optional[TimingInfo] = None
    job_id: Optional[str] = None
    error: Optional[str] = None
