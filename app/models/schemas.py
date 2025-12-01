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

class ImagePreviewResponse(BaseModel):
    success: bool
    image_url: Optional[str] = None
    message: str
