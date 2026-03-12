from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.models.schemas import (
    ImageEditRequest,
    ImageEditResponse,
    ImagePreviewResponse,
    CartoonizeRequest,
)
from app.services.image_service import ImageService
import base64
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import traceback

router = APIRouter(prefix="/api/v1", tags=["images"])
image_service = ImageService()

# 백그라운드 작업용 스레드 풀 (최대 3개 동시 작업)
executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="cartoonize")


@router.post("/edit", response_model=ImageEditResponse)
async def edit_images(request: ImageEditRequest):
    """
    두 이미지 URL을 입력받아 캐리커처로 합성합니다.
    - image1_url: 캐리커처화 할 얼굴 이미지 URL
    - image2_url: 합성할 대상 이미지 URL
    """
    try:
        if not request.image1_url or not request.image2_url:
            raise HTTPException(status_code=400, detail="image1_url과 image2_url은 필수입니다.")

        if not request.image1_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="image1_url은 유효한 URL이어야 합니다.")
        if not request.image2_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="image2_url은 유효한 URL이어야 합니다.")

        result_image = await image_service.edit_images(
            image1_url=request.image1_url,
            image2_url=request.image2_url,
            custom_prompt=request.custom_prompt,
        )

        if result_image:
            if result_image.startswith(("data:image/", "http")):
                preview_url = result_image
            else:
                preview_url = f"data:image/png;base64,{result_image}"

            return ImageEditResponse(
                success=True,
                image_data=result_image,
                preview_url=preview_url,
                message="이미지 합성이 성공적으로 완료되었습니다.",
            )

        return ImageEditResponse(
            success=False,
            message="이미지 생성에 실패했습니다. 프롬프트나 이미지를 확인해주세요.",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


@router.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Image Edit API is running"}


@router.post("/preview", response_model=ImagePreviewResponse)
async def preview_images(request: ImageEditRequest):
    try:
        if not request.image1_url or not request.image2_url:
            raise HTTPException(status_code=400, detail="image1_url과 image2_url은 필수입니다.")

        if not request.image1_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="image1_url은 유효한 URL이어야 합니다.")
        if not request.image2_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="image2_url은 유효한 URL이어야 합니다.")

        result_image = await image_service.edit_images(
            image1_url=request.image1_url,
            image2_url=request.image2_url,
            custom_prompt=request.custom_prompt,
        )

        if result_image:
            if result_image.startswith("data:image/"):
                image_url = result_image
            elif result_image.startswith("http"):
                image_url = result_image
            else:
                image_url = f"data:image/png;base64,{result_image}"

            return ImagePreviewResponse(
                success=True,
                image_url=image_url,
                message="이미지 합성이 성공적으로 완료되었습니다.",
            )

        return ImagePreviewResponse(
            success=False,
            message="이미지 생성에 실패했습니다. 프롬프트나 이미지를 확인해주세요.",
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
            custom_prompt=request.custom_prompt,
        )

        if not result_image:
            raise HTTPException(status_code=400, detail="이미지 생성에 실패했습니다.")

        if result_image.startswith("data:image/"):
            base64_data = result_image.split(",", 1)[1]
            image_bytes = base64.b64decode(base64_data)
        elif result_image.startswith("http"):
            raise HTTPException(status_code=400, detail="URL 형식의 이미지는 직접 미리보기를 지원하지 않습니다.")
        else:
            image_bytes = base64.b64decode(result_image)

        return Response(content=image_bytes, media_type="image/png")

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
            request.regeneration_count,
        )

        return {
            "success": True,
            "job_id": request.job_id,
            "message": "이미지 생성이 시작되었습니다. job_id로 결과를 확인하세요.",
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
    regeneration_count: int = 2,
):
    """
    백그라운드에서 실제 이미지 생성 작업 수행
    완료되면 Supabase DB의 image 테이블에 result/result_add1/result_add2 업데이트
    """
    try:
        print(f"[Background Job {job_id}] 이미지 생성 시작... (스레드: {threading.current_thread().name})")

        result = asyncio.run(
            image_service.cartoonize_with_character(
                image_url=image_url,
                character_id=character_id,
                custom_prompt=custom_prompt,
            )
        )

        print(f"[Background Job {job_id}] cartoonize 반환 타입: {type(result)}")
        print(
            f"[Background Job {job_id}] cartoonize 반환 키: "
            f"{list(result.keys()) if isinstance(result, dict) else 'NOT DICT'}"
        )

        if not isinstance(result, dict):
            raise Exception(f"cartoonize 반환값이 dict가 아닙니다: {type(result)}")

        print(f"[Background Job {job_id}] success 값: {result.get('success')}")

        if result.get("success"):
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

            if not image_service.supabase:
                raise Exception("Supabase 클라이언트가 초기화되지 않았습니다.")

            try:
                image_b64 = result.get("result_image_b64") or result.get("result_image_data_url", "")

                if not image_b64:
                    raise Exception(f"이미지 데이터 없음. 실제 키 목록: {list(result.keys())}")

                if image_b64.startswith("data:"):
                    image_b64 = image_b64.split(",", 1)[1]

                print(f"[Background Job {job_id}] base64 길이: {len(image_b64)}")

                image_bytes = base64.b64decode(image_b64)
                file_name = f"cartoon_results/{job_id}.png"
                print(f"[Background Job {job_id}] Supabase Storage 업로드 시작: {file_name}")

                public_url = image_service.upload_image_to_supabase(image_bytes, file_name)

                if not public_url:
                    raise Exception("Supabase Storage 업로드 실패 - URL 반환 없음")

                print(f"[Background Job {job_id}] Storage 업로드 완료: {public_url}")

                image_service.supabase.table("image").update(
                    {target_column: public_url}
                ).eq("job_id", job_id).execute()

                print(f"[Background Job {job_id}] DB 업데이트 완료 (column: {target_column})")

            except Exception as db_error:
                print(f"[Background Job {job_id}] DB 업데이트 실패: {db_error}")
                print(traceback.format_exc())

                try:
                    image_service.supabase.table("image").update(
                        {"result": f"ERROR: {str(db_error)}"}
                    ).eq("job_id", job_id).execute()
                    print(f"[Background Job {job_id}] DB 에러 상태 저장 완료")
                except Exception as save_error:
                    print(f"[Background Job {job_id}] DB 에러 상태 저장 실패: {save_error}")

        else:
            error_message = result.get("error", "알 수 없는 오류")
            print(f"[Background Job {job_id}] 이미지 생성 실패: {error_message}")

            if image_service.supabase:
                try:
                    image_service.supabase.table("image").update(
                        {"result": f"ERROR: {error_message}"}
                    ).eq("job_id", job_id).execute()
                    print(f"[Background Job {job_id}] 에러 상태 DB 업데이트 완료")
                except Exception as db_error:
                    print(f"[Background Job {job_id}] DB 업데이트 실패: {db_error}")

    except Exception as e:
        print(f"[Background Job {job_id}] 예외 발생: {str(e)}")
        print(traceback.format_exc())

        if image_service.supabase:
            try:
                image_service.supabase.table("image").update(
                    {"result": f"ERROR: {str(e)}"}
                ).eq("job_id", job_id).execute()
                print(f"[Background Job {job_id}] 예외 상태 DB 업데이트 완료")
            except Exception as db_error:
                print(f"[Background Job {job_id}] DB 업데이트 실패: {db_error}")
