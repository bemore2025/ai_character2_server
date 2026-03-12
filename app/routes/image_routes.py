from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from app.models.schemas import (
    ImageEditRequest, ImageEditResponse, ImagePreviewResponse,
    CartoonizeRequest, CartoonizeResponse, TimingInfo
)
from app.services.image_service import ImageService
from app.services.async_job_service import async_job_service
import os
import tempfile
import base64
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

router = APIRouter(prefix="/api/v1", tags=["images"])
image_service = ImageService()

# 백그라운드 작업용 스레드 풀 (최대 3개 동시 작업)
executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cartoonize")

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
            image2_url=request.image2_url,
            custom_prompt=request.custom_prompt
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
            image2_url=request.image2_url,
            custom_prompt=request.custom_prompt
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
            image2_url=request.image2_url,
            custom_prompt=request.custom_prompt
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

@router.post("/cartoonize")
async def cartoonize_image(request: CartoonizeRequest):
    """
    비동기 이미지 생성 - 즉시 응답하고 백그라운드에서 처리
    
    프론트엔드 플로우에 맞춘 API:
    1. 이 API 호출 → 즉시 success 응답 (API Gateway 타임아웃 회피)
    2. 백그라운드에서 이미지 생성 시작
    3. 완료되면 Supabase image 테이블의 result 컬럼에 결과 URL 저장
    4. 프론트엔드는 job_id로 DB 폴링하여 result 확인

    - **image_url**: 첫 번째 이미지 (얼굴 이미지 URL)
    - **character_id**: 캐릭터 ID (두 번째 이미지를 Supabase에서 가져오기 위한 ID)
    - **custom_prompt**: 포즈 묘사 (선택사항)
    - **job_id**: 작업 ID (필수 - 프론트엔드에서 생성한 job_id)
    """
    try:
        if not request.job_id:
            raise HTTPException(status_code=400, detail="job_id는 필수입니다.")
        
        # 백그라운드 작업을 별도 스레드에서 실행 (GIL 블로킹 방지)
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            executor,
            process_cartoonize_background_sync,
            request.job_id,
            str(request.image_url),
            request.character_id,
            request.custom_prompt,
            request.regeneration_count
        )
        
        # 즉시 응답 (API Gateway 29초 타임아웃 회피)
        return {
            "success": True,
            "job_id": request.job_id,
            "message": "이미지 생성이 시작되었습니다. job_id로 결과를 확인하세요."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")

def process_cartoonize_background_sync(
    job_id: str,
    image_url: str,
    character_id: str,
    custom_prompt: str = None,
    regeneration_count: int = 2
):
    """
    백그라운드에서 실제 이미지 생성 작업 수행 (동기 버전 - 별도 스레드에서 실행)
    완료되면 Supabase DB의 image 테이블에 result 업데이트
    """
    try:
        print(f"[Background Job {job_id}] 이미지 생성 시작... (스레드: {threading.current_thread().name})")
        
        # 실제 이미지 생성 (동기 버전)
        # asyncio.run()을 사용하여 async 함수를 동기적으로 실행
        result = asyncio.run(image_service.cartoonize_with_character(
            image_url=image_url,
            character_id=character_id,
            custom_prompt=custom_prompt
        ))
        
        if result['success']:
            print(f"[Background Job {job_id}] 이미지 생성 완료 (base64 수신)")
            
            # regeneration_count에 따라 적절한 컴럼 선택
            # count = 2: result (초기 생성)
            # count = 1: result_add1 (첫 번째 재생성)
            # count = 0: result_add2 (두 번째 재생성)
            if regeneration_count == 2:
                target_column = "result"
            elif regeneration_count == 1:
                target_column = "result_add1"
            elif regeneration_count == 0:
                target_column = "result_add2"
            else:
                target_column = "result"  # 기본값
            
            print(f"[Background Job {job_id}] regeneration_count={regeneration_count}, target_column={target_column}")
            
            # Supabase DB 업데이트 (적절한 컴럼에 업데이트)
            if image_service.supabase:
                try:
                    # ✅ 수정: base64 → Supabase Storage 업로드 → URL을 DB에 저장
                    image_b64 = result['result.get('result_image_b64') or result.get('result_image_data_url', '')']from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from app.models.schemas import (
    ImageEditRequest, ImageEditResponse, ImagePreviewResponse,
    CartoonizeRequest, CartoonizeResponse, TimingInfo
)
from app.services.image_service import ImageService
from app.services.async_job_service import async_job_service
import os
import tempfile
import base64
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

router = APIRouter(prefix="/api/v1", tags=["images"])
image_service = ImageService()

# 백그라운드 작업용 스레드 풀 (최대 3개 동시 작업)
executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cartoonize")

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
            image2_url=request.image2_url,
            custom_prompt=request.custom_prompt
        )
        
        if result_image:
            if result_image.startswith(('data:image/', 'http')):
                preview_url = result_image
            else:
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
    try:
        if not request.image1_url or not request.image2_url:
            raise HTTPException(status_code=400, detail="image1_url과 image2_url은 필수입니다.")

        if not request.image1_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="image1_url은 유효한 URL이어야 합니다.")
        if not request.image2_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="image2_url은 유효한 URL이어야 합니다.")

        result_image = await image_service.edit_images(
            image1_url=request.image1_url,
            image2_url=request.image2_url,
            custom_prompt=request.custom_prompt
        )
        
        if result_image:
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
    try:
        if not request.image1_url or not request.image2_url:
            raise HTTPException(status_code=400, detail="image1_url과 image2_url은 필수입니다.")

        result_image = await image_service.edit_images(
            image1_url=request.image1_url,
            image2_url=request.image2_url,
            custom_prompt=request.custom_prompt
        )
        
        if result_image:
            if result_image.startswith('data:image/'):
                base64_data = result_image.split(',')[1]
                image_bytes = base64.b64decode(base64_data)
            elif result_image.startswith('http'):
                raise HTTPException(status_code=400, detail="URL 형식의 이미지는 직접 미리보기를 지원하지 않습니다.")
            else:
                image_bytes = base64.b64decode(result_image)
            
            return Response(content=image_bytes, media_type="image/png")
        else:
            raise HTTPException(status_code=400, detail="이미지 생성에 실패했습니다.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")

@router.post("/cartoonize")
async def cartoonize_image(request: CartoonizeRequest):
    """
    비동기 이미지 생성 - 즉시 응답하고 백그라운드에서 처리
    """
    try:
        if not request.job_id:
            raise HTTPException(status_code=400, detail="job_id는 필수입니다.")
        
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            executor,
            process_cartoonize_background_sync,
            request.job_id,
            str(request.image_url),
            request.character_id,
            request.custom_prompt,
            request.regeneration_count
        )
        
        return {
            "success": True,
            "job_id": request.job_id,
            "message": "이미지 생성이 시작되었습니다. job_id로 결과를 확인하세요."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")

def process_cartoonize_background_sync(
    job_id: str,
    image_url: str,
    character_id: str,
    custom_prompt: str = None,
    regeneration_count: int = 2
):
    """
    백그라운드에서 실제 이미지 생성 작업 수행 (동기 버전 - 별도 스레드에서 실행)
    완료되면 Supabase DB의 image 테이블에 result 업데이트
    """
    try:
        print(f"[Background Job {job_id}] 이미지 생성 시작... (스레드: {threading.current_thread().name})")
        
        result = asyncio.run(image_service.cartoonize_with_character(
            image_url=image_url,
            character_id=character_id,
            custom_prompt=custom_prompt
        ))

        # [DEBUG] 반환값 확인
        print(f"[Background Job {job_id}] cartoonize 반환 타입: {type(result)}")
        print(f"[Background Job {job_id}] cartoonize 반환 키: {list(result.keys()) if isinstance(result, dict) else 'NOT DICT'}")
        print(f"[Background Job {job_id}] success 값: {result.get('success')}")
        
        if result['success']:
            print(f"[Background Job {job_id}] 이미지 생성 완료")
            
            if regeneration_count == 2:
                target_column = "result"
            elif regeneration_count == 1:
                target_column = "result_add1"
            elif regeneration_count == 0:
                target_column = "result_add2"
            else:
                target_column = "result"
            
            print(f"[Background Job {job_id}] regeneration_count={regeneration_count}, target_column={target_column}")
            
            if image_service.supabase:
                try:
                    # [FIX] result.get('result_image_b64') or result.get('result_image_data_url', '') -> result_image_b64 키 이름 오타 수정
                    image_b64 = result.get('result_image_b64') or result.get('result_image_data_url', '')
                    
                    if not image_b64:
                        raise Exception(f"이미지 데이터 없음. 실제 키 목록: {list(result.keys())}")
                    
                    # data:image/png;base64, 접두사 제거
                    if image_b64.startswith('data:'):
                        image_b64 = image_b64.split(',', 1)[1]
                    
                    print(f"[Background Job {job_id}] base64 길이: {len(image_b64)}")
                    
                    image_bytes = base64.b64decode(image_b64)
                    file_name = f"cartoon_results/{job_id}.png"
                    print(f"[Background Job {job_id}] Supabase Storage 업로드 시작: {file_name}")
                    
                    public_url = image_service.upload_image_to_supabase(image_bytes, file_name)
                    
                    if not public_url:
                        raise Exception("Supabase Storage 업로드 실패 - URL 반환 없음")
                    
                    print(f"[Background Job {job_id}] Storage 업로드 완료: {public_url}")
                    
                    update_result = image_service.supabase.table("image").update({
                        target_column: public_url
                    }).eq("job_id", job_id).execute()
                    
                    print(f"[Background Job {job_id}] DB 업데이트 완료 (column: {target_column})")
                    
                except Exception as db_error:
                    print(f"[Background Job {job_id}] DB 업데이트 실패: {db_error}")
                    import traceback
                    print(traceback.format_exc())
                    try:
                        image_service.supabase.table("image").update({
                            "result": f"ERROR: {str(db_error)}"
                        }).eq("job_id", job_id).execute()
                    except Exception:
                        pass
        else:
            print(f"[Background Job {job_id}] 이미지 생성 실패: {result.get('error')}")
            if image_service.supabase:
                try:
                    image_service.supabase.table("image").update({
                        "result": f"ERROR: {result.get('error', '알 수 없는 오류')}"
                    }).eq("job_id", job_id).execute()
                    print(f"[Background Job {job_id}] 에러 상태 DB 업데이트 완료")
                except Exception as db_error:
                    print(f"[Background Job {job_id}] DB 업데이트 실패: {db_error}")
                    
    except Exception as e:
        print(f"[Background Job {job_id}] 예외 발생: {str(e)}")
        import traceback
        print(traceback.format_exc())
        if image_service.supabase:
            try:
                image_service.supabase.table("image").update({
                    "result": f"ERROR: {str(e)}"
                }).eq("job_id", job_id).execute()
                print(f"[Background Job {job_id}] 예외 상태 DB 업데이트 완료")
            except Exception as db_error:
                print(f"[Background Job {job_id}] DB 업데이트 실패: {db_error}")

                    image_bytes = base64.b64decode(image_b64)
                    file_name = f"cartoon_results/{job_id}.png"
                    print(f"[Background Job {job_id}] Supabase Storage 업로드 시작: {file_name}")
                    public_url = image_service.upload_image_to_supabase(image_bytes, file_name)
                    
                    if not public_url:
                        raise Exception("Supabase Storage 업로드 실패 - URL 반환 없음")
                    
                    print(f"[Background Job {job_id}] Storage 업로드 완료: {public_url}")
                    
                    update_result = image_service.supabase.table("image").update({
                        target_column: public_url
                    }).eq("job_id", job_id).execute()
                    
                    print(f"[Background Job {job_id}] DB 업데이트 완료 (column: {target_column})")
                except Exception as db_error:
                    print(f"[Background Job {job_id}] DB 업데이트 실패: {db_error}")
        else:
            print(f"[Background Job {job_id}] 이미지 생성 실패: {result.get('error')}")
            
            # 실패 시에도 result에 에러 메시지 저장 (프론트엔드가 폴링으로 확인)
            if image_service.supabase:
                try:
                    image_service.supabase.table("image").update({
                        "result": f"ERROR: {result.get('error', '알 수 없는 오류')}"
                    }).eq("job_id", job_id).execute()
                    print(f"[Background Job {job_id}] 에러 상태 DB 업데이트 완료")
                except Exception as db_error:
                    print(f"[Background Job {job_id}] DB 업데이트 실패: {db_error}")
                    
    except Exception as e:
        print(f"[Background Job {job_id}] 예외 발생: {str(e)}")
        
        # 에러 발생 시 result에 에러 메시지 저장
        if image_service.supabase:
            try:
                image_service.supabase.table("image").update({
                    "result": f"ERROR: {str(e)}"
                }).eq("job_id", job_id).execute()
                print(f"[Background Job {job_id}] 예외 상태 DB 업데이트 완료")
            except Exception as db_error:
                print(f"[Background Job {job_id}] DB 업데이트 실패: {db_error}")
