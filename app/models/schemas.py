from pydantic import BaseModel, HttpUrl
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

class ImagePreviewResponse(BaseModel):
    success: bool
    image_url: Optional[str] = None
    message: str

# target.py와 동일한 구조
class CartoonizeRequest(BaseModel):
    image_url: HttpUrl  # 첫 번째 이미지 (얼굴 이미지)
    character_id: str  # 캐릭터 ID (두 번째 이미지를 가져오기 위한 ID)
    custom_prompt: Optional[str] = None  # 포즈 묘사
    job_id: Optional[str] = None
    regeneration_count: Optional[int] = 2  # 재생성 횟수 (2: 초기, 1: 첫 번째 재생성, 0: 두 번째 재생성)

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
