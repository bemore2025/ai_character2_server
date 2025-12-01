from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from app.models.schemas import ImageEditRequest, ImageEditResponse, ImagePreviewResponse
from app.services.image_service import ImageService
import os
import tempfile
import base64

router = APIRouter(prefix="/api/v1", tags=["images"])
image_service = ImageService()

@router.post("/edit", response_model=ImageEditResponse)
async def edit_images(request: ImageEditRequest):
    """
    두 이미지 URL을 입력받아 캐리커처로 합성합니다.

    - **image1_url**: 캐리커처화 할 얼굴 이미지 URL
    - **image2_url**: 합성할 대상 이미지 URL
    """

    try:
        # URL 검증
        if not request.image1_url or not request.image2_url:
            raise HTTPException(status_code=400, detail="image1_url과 image2_url은 필수입니다.")

        if not request.image1_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="image1_url은 유효한 URL이어야 합니다.")
        if not request.image2_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="image2_url은 유효한 URL이어야 합니다.")

        # 이미지 처리 서비스 호출
        result_image = await image_service.edit_images(
            image1_url=request.image1_url,
            image2_url=request.image2_url
        )
        
        if result_image:
            # base64 이미지를 data URL로 변환하여 웹에서 바로 볼 수 있도록 함
            if result_image.startswith(('data:image/', 'http')):
                # 이미 URL 형식이거나 data URL 형식인 경우
                preview_url = result_image
            else:
                # 순수 base64인 경우 data URL로 변환
                preview_url = f"data:image/png;base64,{result_image}"
            
            return ImageEditResponse(
                success=True,
                image_data=result_image,
                preview_url=preview_url,
                message="이미지 합성이 성공적으로 완료되었습니다."
            )
        else:
            return ImageEditResponse(
                success=False,
                message="이미지 생성에 실패했습니다. 프롬프트나 이미지를 확인해주세요."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")

@router.get("/health")
async def health_check():
    """API 상태 확인"""
    return {"status": "healthy", "message": "Image Edit API is running"}

@router.post("/preview", response_model=ImagePreviewResponse)
async def preview_images(request: ImageEditRequest):
    """
    두 이미지 URL을 입력받아 캐리커처로 합성하고 JSON 응답으로 image_url을 반환합니다.
    image_url을 복사하여 웹 브라우저에 붙여넣으면 이미지를 볼 수 있습니다.
    (Swagger UI에서 바로 이미지를 보려면 /preview-image 엔드포인트를 사용하세요)
    """

    try:
        # URL 검증
        if not request.image1_url or not request.image2_url:
            raise HTTPException(status_code=400, detail="image1_url과 image2_url은 필수입니다.")

        if not request.image1_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="image1_url은 유효한 URL이어야 합니다.")
        if not request.image2_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="image2_url은 유효한 URL이어야 합니다.")

        # 이미지 처리 서비스 호출
        result_image = await image_service.edit_images(
            image1_url=request.image1_url,
            image2_url=request.image2_url
        )
        
        if result_image:
            # base64 이미지를 data URL로 변환
            if result_image.startswith('data:image/'):
                image_url = result_image
            elif result_image.startswith('http'):
                image_url = result_image
            else:
                image_url = f"data:image/png;base64,{result_image}"
            
            return ImagePreviewResponse(
                success=True,
                image_url=image_url,
                message="이미지 합성이 성공적으로 완료되었습니다."
            )
        else:
            return ImagePreviewResponse(
                success=False,
                message="이미지 생성에 실패했습니다. 프롬프트나 이미지를 확인해주세요."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")

@router.post("/preview-image", responses={200: {"content": {"image/png": {}}}})
async def preview_image_direct(request: ImageEditRequest):
    """
    두 이미지 URL을 입력받아 캐리커처로 합성하고 이미지를 직접 반환합니다.
    Swagger UI에서 'Download file'을 클릭하면 이미지를 바로 볼 수 있습니다.
    (이 엔드포인트가 Swagger UI에서 이미지를 바로 보는 방법입니다)
    """

    try:
        # URL 검증
        if not request.image1_url or not request.image2_url:
            raise HTTPException(status_code=400, detail="image1_url과 image2_url은 필수입니다.")

        if not request.image1_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="image1_url은 유효한 URL이어야 합니다.")
        if not request.image2_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="image2_url은 유효한 URL이어야 합니다.")

        # 이미지 처리 서비스 호출
        result_image = await image_service.edit_images(
            image1_url=request.image1_url,
            image2_url=request.image2_url
        )
        
        if result_image:
            # base64 이미지를 바이트로 변환하여 직접 반환
            if result_image.startswith('data:image/'):
                # data URL에서 base64 부분 추출
                base64_data = result_image.split(',')[1]
                image_bytes = base64.b64decode(base64_data)
            elif result_image.startswith('http'):
                # URL인 경우 에러 반환 (직접 이미지 반환 불가)
                raise HTTPException(status_code=400, detail="URL 형식의 이미지는 직접 미리보기를 지원하지 않습니다.")
            else:
                # 순수 base64인 경우
                image_bytes = base64.b64decode(result_image)
            
            return Response(content=image_bytes, media_type="image/png")
        else:
            raise HTTPException(status_code=400, detail="이미지 생성에 실패했습니다. 프롬프트나 이미지를 확인해주세요.")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")
