from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional
import os
import google.generativeai as genai
from dotenv import load_dotenv
import requests
from PIL import Image
import io
import uvicorn
from supabase import create_client, Client
import random
import replicate
from datetime import datetime
import uuid
import json
import time
import numpy as np
from scipy.ndimage import gaussian_filter
import tempfile
from urllib.parse import urlparse

# .env 파일에서 환경변수 로드
load_dotenv()

# FastAPI 앱 생성
app = FastAPI(
    title="이미지 묘사 API",
    description="Gemini API를 사용해서 이미지를 영어로 묘사해주는 API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 운영환경에서는 구체적인 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 요청/응답 모델
class ImageDescribeRequest(BaseModel):
    image_url: HttpUrl
    character_id: Optional[str] = None
    custom_prompt: Optional[str] = None
    job_id: Optional[str] = None

class CartoonizeRequest(BaseModel):
    image_url: HttpUrl
    character_id: str
    custom_prompt: str
    job_id: Optional[str] = None
    
class ImageDescribeResponse(BaseModel):
    success: bool
    description: Optional[str] = None
    character_id: Optional[str] = None
    character_image_url: Optional[str] = None
    processing_time: Optional[float] = None
    job_id: Optional[str] = None
    error: Optional[str] = None

class TimingInfo(BaseModel):
    character_image_fetch: Optional[float] = None
    face_description: Optional[float] = None
    prompt_translation: Optional[float] = None
    image_generation: Optional[float] = None
    background_removal: Optional[float] = None
    image_upload: Optional[float] = None
    total_time: Optional[float] = None

class CartoonizeResponse(BaseModel):
    success: bool
    result_image_url: Optional[str] = None
    background_removed_image_url: Optional[str] = None
    character_id: Optional[str] = None
    character_image_url: Optional[str] = None
    translated_prompt: Optional[str] = None
    face_description: Optional[str] = None
    timing: Optional[TimingInfo] = None
    job_id: Optional[str] = None
    error: Optional[str] = None

def get_gemini_client():
    """Gemini 클라이언트를 설정합니다."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.0-flash-exp')

# Gemini 기반 배경 제거 구현

def get_supabase_client() -> Client:
    """Supabase 클라이언트를 설정합니다."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ACCESS_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL 또는 SUPABASE_ACCESS_KEY 환경변수가 설정되지 않았습니다.")
    
    return create_client(url, key)

def get_random_character_image(character_id: str) -> Optional[str]:
    """
    character_id를 이용해 character 테이블에서 picture_cartoon 중 랜덤한 이미지 URL을 반환합니다.
    
    Args:
        character_id (str): 찾을 캐릭터의 ID
    
    Returns:
        str: 랜덤하게 선택된 이미지 URL
        None: 에러가 발생하거나 데이터가 없는 경우
    """
    try:
        supabase = get_supabase_client()
        
        # character 테이블에서 해당 ID의 picture_cartoon 가져오기
        response = supabase.table("character").select("picture_cartoon").eq("id", character_id).execute()
        
        if not response.data:
            print(f"캐릭터 ID {character_id}를 찾을 수 없습니다.")
            return None
        
        picture_cartoon = response.data[0].get("picture_cartoon")
        
        if not picture_cartoon or not isinstance(picture_cartoon, list) or len(picture_cartoon) == 0:
            print(f"캐릭터 ID {character_id}의 picture_cartoon이 비어있거나 올바르지 않습니다.")
            return None
        
        # 리스트에서 랜덤하게 하나 선택
        random_item = random.choice(picture_cartoon)
        
        # 딕셔너리 형태인 경우 url 키의 값을 추출
        if isinstance(random_item, dict) and 'url' in random_item:
            return random_item['url']
        # 문자열인 경우 그대로 반환
        elif isinstance(random_item, str):
            return random_item
        else:
            print(f"예상치 못한 데이터 형태: {type(random_item)}, 값: {random_item}")
            return None
        
    except Exception as e:
        print(f"캐릭터 이미지 가져오기 중 오류 발생: {str(e)}")
        return None

def load_image_from_url(image_url: str) -> Optional[Image.Image]:
    """URL에서 이미지를 다운로드하여 PIL Image로 변환합니다."""
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content))
    except Exception as e:
        print(f"이미지 로드 중 오류 발생: {str(e)}")
        return None

def describe_face_simple(image_url: str, custom_prompt: Optional[str] = None) -> Optional[str]:
    """
    이미지를 영어로 묘사하는 함수
    
    Args:
        image_url (str): 분석할 이미지의 URL
        custom_prompt (Optional[str]): 사용자 정의 프롬프트
    
    Returns:
        str: 영어로 된 이미지 묘사
        None: 에러가 발생한 경우
    """
    try:
        model = get_gemini_client()
        
        # 이미지 로드
        image = load_image_from_url(image_url)
        if image is None:
            return None
        
        # 사용자 정의 프롬프트가 있으면 사용, 없으면 기본 프롬프트 사용
        if custom_prompt:
            prompt = custom_prompt
        else:
            prompt = """Please describe the person's appearance in simple keywords. Focus only on:
1. Eyes: size and features (big eyes, small eyes, wear glasses, etc.)
2. Face: basic features (round face, oval face, etc.)
3. Facial accessories: if any (wear glasses, earrings, etc.)

Respond with simple phrases like: "big brown eyes, round face, wear glasses"
Keep it very simple and use only basic descriptive phrases."""

        response = model.generate_content([prompt, image])
        
        if response.text:
            return response.text.strip()
        else:
            return None
        
    except Exception as e:
        print(f"이미지 묘사 중 오류 발생: {str(e)}")
        return None

def translate_to_english(korean_text: str) -> Optional[str]:
    """
    한국어 텍스트를 영어로 번역합니다.
    직업적 표현은 제거하고 외모와 행동 묘사만 번역합니다.
    
    Args:
        korean_text (str): 번역할 한국어 텍스트
    
    Returns:
        str: 영어로 번역된 텍스트
        None: 에러가 발생한 경우
    """
    try:
        model = get_gemini_client()
        
        prompt = f"""Translate this Korean text to English, but follow these rules:

1. INCLUDE hair descriptions (hair color, hairstyle, hair length, etc.)
2. EXCLUDE professional/occupational expressions (like "navy officer", "doctor", "teacher", etc.)
3. ONLY translate descriptions about:
   - Physical appearance (including hair, face, eyes, body, etc.)
   - Actions and behaviors
   - Clothing and accessories (but not uniforms that indicate profession)
   - Expressions and emotions

4. Remove any mentions of jobs, titles, or professional roles
5. Focus only on what the person looks like and what they are doing

Korean text: {korean_text}

Provide only the translated English text with appearance and behavior descriptions:"""
        
        response = model.generate_content(prompt)
        
        if response.text:
            return response.text.strip()
        else:
            return None
        
    except Exception as e:
        print(f"번역 중 오류 발생: {str(e)}")
        return None

def generate_cartoon_with_replicate(character_image_url: str, face_description: str, translated_prompt: str) -> Optional[str]:
    """
    Replicate API를 사용해서 캐릭터 이미지와 얼굴 묘사, 커스텀 프롬프트를 결합해서 이미지를 생성합니다.
    
    Args:
        character_image_url (str): 캐릭터 이미지 URL
        face_description (str): 얼굴 묘사
        translated_prompt (str): 영어로 번역된 커스텀 프롬프트
    
    Returns:
        str: 생성된 이미지의 URL
        None: 에러가 발생한 경우
    """
    try:
        # Replicate API 토큰 확인
        replicate_token = os.getenv('REPLICATE_API_TOKEN')
        if not replicate_token:
            print("❌ REPLICATE_API_TOKEN 환경변수가 설정되지 않았습니다.")
            return None
        
        print(f"✅ Replicate API 토큰 확인됨 (길이: {len(replicate_token)})")
        
        # 복합 프롬프트 생성 (he {묘사} and {prompt행동묘사} and white background 형태)
        combined_prompt = f"he {face_description} and {translated_prompt} and white background"
        
        input_data = {
            "prompt": combined_prompt.strip(),
            "input_image": character_image_url,
            "output_format": "jpg"
        }
        
        # Replicate에 보내는 JSON 값 출력
        print("=== Replicate API 요청 데이터 ===")
        print(json.dumps(input_data, indent=2, ensure_ascii=False))
        print("=============================")
        
        print("🚀 Replicate API 호출 시작...")
        
        # 타임아웃과 재시도 로직 추가
        max_retries = 2
        timeout_seconds = 300  # 5분
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    print(f"🔄 재시도 {attempt}/{max_retries}")
                    time.sleep(5)  # 5초 대기 후 재시도
                
                start_time = time.time()
                output = replicate.run(
                    "black-forest-labs/flux-kontext-pro",
                    input=input_data
                )
                end_time = time.time()
                
                print(f"⏱️ API 호출 소요 시간: {end_time - start_time:.2f}초")
                break
                
            except Exception as retry_error:
                print(f"❌ 시도 {attempt + 1} 실패: {str(retry_error)}")
                if attempt == max_retries:
                    raise retry_error
        
        print(f"📥 Replicate API 응답 받음 - 타입: {type(output)}")
        print(f"📄 응답 내용: {output}")
        
        # 다양한 응답 형태 처리
        result_url = None
        
        if output is None:
            print("❌ Replicate API가 None을 반환했습니다.")
            return None
        elif hasattr(output, 'url'):
            # url이 메서드인지 속성인지 확인
            if callable(getattr(output, 'url', None)):
                result_url = output.url()
                print(f"✅ output.url() 메서드로 URL 획득: {result_url}")
            else:
                result_url = output.url
                print(f"✅ output.url 속성으로 URL 획득: {result_url}")
        elif isinstance(output, str):
            result_url = output
            print(f"✅ 문자열로 URL 획득: {result_url}")
        elif isinstance(output, list) and len(output) > 0:
            # 리스트 형태인 경우 첫 번째 요소 확인
            first_item = output[0]
            if isinstance(first_item, str):
                result_url = first_item
                print(f"✅ 리스트 첫 번째 요소로 URL 획득: {result_url}")
            elif hasattr(first_item, 'url'):
                # url이 메서드인지 속성인지 확인
                if callable(getattr(first_item, 'url', None)):
                    result_url = first_item.url()
                    print(f"✅ 리스트 첫 번째 요소의 url() 메서드로 URL 획득: {result_url}")
                else:
                    result_url = first_item.url
                    print(f"✅ 리스트 첫 번째 요소의 url 속성으로 URL 획득: {result_url}")
        elif isinstance(output, dict):
            # 딕셔너리 형태인 경우
            if 'url' in output:
                result_url = output['url']
                print(f"✅ 딕셔너리에서 URL 획득: {result_url}")
            elif 'output' in output:
                result_url = output['output']
                print(f"✅ 딕셔너리에서 output 키로 URL 획득: {result_url}")
        
        if result_url:
            # URL 유효성 간단 검증
            if result_url.startswith(('http://', 'https://')):
                print(f"🎉 최종 생성된 이미지 URL: {result_url}")
                return result_url
            else:
                print(f"❌ 유효하지 않은 URL 형태: {result_url}")
                return None
        else:
            print(f"❌ 예상치 못한 출력 형태: {type(output)}")
            print(f"❌ 출력 내용 전체: {output}")
            return None
        
    except replicate.exceptions.ReplicateError as e:
        print(f"❌ Replicate API 오류: {str(e)}")
        print(f"❌ 오류 타입: {type(e)}")
        return None
    except Exception as e:
        print(f"❌ 일반 오류 발생: {str(e)}")
        print(f"❌ 오류 타입: {type(e)}")
        import traceback
        print(f"❌ 스택 트레이스: {traceback.format_exc()}")
        return None

def analyze_image_with_gemini_for_bg_removal(image_data: bytes, model_name: str = "gemini-2.0-flash-exp") -> dict:
    """
    Gemini를 사용하여 배경 제거를 위한 이미지 분석
    
    Args:
        image_data: 이미지 바이트 데이터
        model_name: 사용할 Gemini 모델 이름
    
    Returns:
        이미지 분석 결과
    """
    try:
        print(f"🔍 Gemini {model_name} 모델로 이미지 분석 시작")
        
        # 이미지를 PIL Image로 변환
        image = Image.open(io.BytesIO(image_data))
        
        # Gemini 모델 초기화
        model = genai.GenerativeModel(model_name)
        
        # 프롬프트 작성
        prompt = """
        이 이미지를 분석하고 다음 정보를 JSON 형식으로 제공해주세요:
        
        1. main_subject: 이미지의 주요 피사체 설명
        2. background_type: 배경 유형 (단색, 그라데이션, 복잡한 배경 등)
        3. has_person: 사람이 있는지 여부 (true/false)
        4. complexity: 배경 제거 난이도 (easy, medium, hard)
        5. recommended_method: 권장 배경 제거 방법
        6. description: 이미지 전체 설명
        
        JSON 형식으로만 응답해주세요.
        """
        
        # 이미지 분석 요청
        response = model.generate_content([prompt, image])
        
        # 응답 파싱
        try:
            # JSON 블록 추출
            response_text = response.text
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            analysis_result = json.loads(response_text.strip())
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 기본값 반환
            analysis_result = {
                "main_subject": "알 수 없음",
                "background_type": "복잡한 배경",
                "has_person": False,
                "complexity": "medium",
                "recommended_method": "u2net",
                "description": response.text[:200] if response.text else "분석 실패"
            }
        
        print(f"✅ 이미지 분석 완료: {analysis_result}")
        return analysis_result
        
    except Exception as e:
        print(f"❌ Gemini 이미지 분석 실패: {e}")
        return {
            "error": str(e),
            "main_subject": "분석 실패",
            "background_type": "알 수 없음",
            "has_person": False,
            "complexity": "unknown",
            "recommended_method": "isnet-general-use",
            "description": "이미지 분석에 실패했습니다."
        }

def remove_background_with_gemini(image_data: bytes, analysis: dict = None, model_name: str = "gemini-2.0-flash-exp") -> bytes:
    """
    Gemini AI를 사용한 배경 제거 처리
    
    Args:
        image_data: 원본 이미지 데이터
        analysis: Gemini 분석 결과 (선택적)
        model_name: 사용할 Gemini 모델명
    
    Returns:
        배경이 제거된 이미지 데이터
    """
    try:
        print("🤖 Gemini AI 배경 제거 처리 시작")
        
        # 이미지를 PIL Image로 변환
        image = Image.open(io.BytesIO(image_data))
        
        # 이미지 크기 최적화 (Gemini API 효율성을 위해)
        max_size = 1024
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            print(f"🔄 이미지 크기 조정: {new_size}")
        
        # Gemini 모델 초기화
        model = genai.GenerativeModel(model_name)
        
        # 분석 정보가 있으면 활용하여 더 정확한 프롬프트 생성
        main_subject = analysis.get('main_subject', 'main object') if analysis else 'main object'
        
        # 배경 제거를 위한 프롬프트 작성
        prompt = f"""Please create an image with the {main_subject} from this photo, but with a completely transparent background. Requirements:

1. Keep the {main_subject} exactly as it appears in the original image
2. Remove ALL background elements completely  
3. Make the background 100% transparent (alpha channel = 0)
4. Preserve all details, colors, and lighting of the {main_subject}
5. Ensure clean edges around the {main_subject}
6. Output as PNG format with transparency

Focus only on extracting the {main_subject} with perfect edge quality and transparent background."""

        print(f"🎯 배경 제거 프롬프트: {main_subject} 추출")
        
        # Gemini API로 배경 제거된 이미지 생성
        response = model.generate_content([prompt, image])
        
        # 응답이 이미지인지 확인하고 처리
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, 'inline_data'):
                        # 생성된 이미지 데이터 추출
                        generated_image_data = part.inline_data.data
                        
                        # Base64 디코딩이 필요한 경우
                        if isinstance(generated_image_data, str):
                            import base64
                            generated_image_data = base64.b64decode(generated_image_data)
                        
                        print("✅ Gemini로 배경 제거 완료")
                        return generated_image_data
        
        # 텍스트 응답만 있는 경우 다른 방식으로 시도
        print("⚠️ Gemini에서 직접 이미지 생성 실패, 마스크 기반 방식 시도")
        return create_transparent_background_mask(image_data, analysis, model_name)
        
    except Exception as e:
        print(f"❌ Gemini 배경 제거 실패: {e}")
        # 실패 시 기본 투명 배경 처리
        return create_simple_transparent_background(image_data)

def create_transparent_background_mask(image_data: bytes, analysis: dict = None, model_name: str = "gemini-2.0-flash-exp") -> bytes:
    """
    Gemini로 마스크를 생성하여 배경 제거
    
    Args:
        image_data: 원본 이미지 데이터
        analysis: Gemini 분석 결과
        model_name: 사용할 Gemini 모델명
    
    Returns:
        배경이 제거된 이미지 데이터
    """
    try:
        print("🎭 Gemini 마스크 기반 배경 제거 시작")
        
        # 이미지를 PIL Image로 변환
        image = Image.open(io.BytesIO(image_data))
        
        # Gemini 모델 초기화
        model = genai.GenerativeModel(model_name)
        
        main_subject = analysis.get('main_subject', 'main object') if analysis else 'main object'
        
        # 객체 영역 식별을 위한 프롬프트
        mask_prompt = f"""Analyze this image and identify the exact boundaries of the {main_subject}. 

Please provide detailed information about:
1. Object boundaries (top, bottom, left, right coordinates as percentages)
2. Object shape description
3. Key features that distinguish the object from background
4. Color differences between object and background
5. Recommended segmentation strategy

Respond in JSON format with precise boundary information."""

        # 마스크 정보 생성
        response = model.generate_content([mask_prompt, image])
        
        if response.text:
            # JSON 응답 파싱 시도
            try:
                import json
                response_text = response.text
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]
                
                mask_info = json.loads(response_text.strip())
                print(f"🎯 마스크 정보 생성 완료: {mask_info}")
                
                # 마스크 정보를 기반으로 배경 제거 수행
                return apply_mask_to_remove_background(image, mask_info)
                
            except (json.JSONDecodeError, KeyError) as e:
                print(f"⚠️ 마스크 정보 파싱 실패: {e}")
                # 단순 색상 기반 배경 제거로 대체
                return create_simple_transparent_background(image_data)
        
        return create_simple_transparent_background(image_data)
        
    except Exception as e:
        print(f"❌ 마스크 기반 배경 제거 실패: {e}")
        return create_simple_transparent_background(image_data)

def apply_mask_to_remove_background(image: Image.Image, mask_info: dict) -> bytes:
    """
    마스크 정보를 적용하여 배경 제거
    
    Args:
        image: PIL 이미지 객체
        mask_info: Gemini에서 생성한 마스크 정보
    
    Returns:
        배경이 제거된 이미지 데이터
    """
    try:
        print("🖼️ 마스크 적용하여 배경 제거 중")
        
        # RGBA 모드로 변환
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # 이미지를 numpy 배열로 변환
        img_array = np.array(image)
        
        # 경계 정보 추출 (퍼센트를 픽셀로 변환)
        height, width = img_array.shape[:2]
        
        # 기본값 설정 (전체 이미지의 중앙 80% 영역)
        boundaries = mask_info.get('boundaries', {})
        top = int(height * boundaries.get('top', 0.1) / 100)
        bottom = int(height * boundaries.get('bottom', 0.9) / 100)
        left = int(width * boundaries.get('left', 0.1) / 100)
        right = int(width * boundaries.get('right', 0.9) / 100)
        
        # 단순 경계 기반 마스킹 (개선 가능한 부분)
        mask = np.zeros((height, width), dtype=np.uint8)
        mask[top:bottom, left:right] = 255
        
        # 가장자리 부드럽게 처리
        mask_smooth = gaussian_filter(mask.astype(float), sigma=2.0)
        mask_smooth = (mask_smooth / mask_smooth.max() * 255).astype(np.uint8)
        
        # 알파 채널에 마스크 적용
        img_array[:, :, 3] = mask_smooth
        
        # PIL Image로 변환
        result_image = Image.fromarray(img_array, 'RGBA')
        
        # 바이트로 변환하여 반환
        output_buffer = io.BytesIO()
        result_image.save(output_buffer, format='PNG', optimize=True)
        output_buffer.seek(0)
        
        print("✅ 마스크 적용 배경 제거 완료")
        return output_buffer.getvalue()
        
    except Exception as e:
        print(f"❌ 마스크 적용 실패: {e}")
        # 최후 수단으로 단순 투명 배경 생성
        return create_simple_transparent_background_from_pil(image)

def create_simple_transparent_background(image_data: bytes) -> bytes:
    """
    단순한 투명 배경 생성 (최후 수단)
    
    Args:
        image_data: 원본 이미지 데이터
    
    Returns:
        투명 배경이 적용된 이미지 데이터
    """
    try:
        print("🎨 단순 투명 배경 처리 중")
        
        image = Image.open(io.BytesIO(image_data))
        return create_simple_transparent_background_from_pil(image)
        
    except Exception as e:
        print(f"❌ 단순 배경 제거 실패: {e}")
        # 원본 이미지를 RGBA로 변환해서 반환
        return image_data

def create_simple_transparent_background_from_pil(image: Image.Image) -> bytes:
    """
    PIL 이미지에서 단순 투명 배경 생성
    
    Args:
        image: PIL 이미지 객체
    
    Returns:
        투명 배경이 적용된 이미지 데이터
    """
    try:
        # RGBA 모드로 변환
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        # 이미지를 numpy 배열로 변환
        img_array = np.array(image)
        
        # 단순히 모서리 픽셀을 배경색으로 간주하고 제거
        height, width = img_array.shape[:2]
        
        # 모서리 픽셀들의 평균 색상 계산
        edge_pixels = []
        edge_pixels.extend(img_array[0, :, :3].reshape(-1, 3))  # 상단
        edge_pixels.extend(img_array[-1, :, :3].reshape(-1, 3))  # 하단
        edge_pixels.extend(img_array[:, 0, :3].reshape(-1, 3))  # 좌측
        edge_pixels.extend(img_array[:, -1, :3].reshape(-1, 3))  # 우측
        
        edge_pixels = np.array(edge_pixels)
        bg_color = np.mean(edge_pixels, axis=0)
        
        # 배경색과 유사한 픽셀들의 알파값을 0으로 설정
        color_diff = np.linalg.norm(img_array[:, :, :3] - bg_color, axis=2)
        threshold = 50  # 색상 차이 임계값
        
        alpha_channel = np.where(color_diff < threshold, 0, 255).astype(np.uint8)
        img_array[:, :, 3] = alpha_channel
        
        # 가장자리 부드럽게 처리
        alpha_smooth = gaussian_filter(alpha_channel.astype(float), sigma=1.0)
        img_array[:, :, 3] = np.clip(alpha_smooth, 0, 255).astype(np.uint8)
        
        # PIL Image로 변환
        result_image = Image.fromarray(img_array, 'RGBA')
        
        # 바이트로 변환하여 반환
        output_buffer = io.BytesIO()
        result_image.save(output_buffer, format='PNG', optimize=True)
        output_buffer.seek(0)
        
        print("✅ 단순 투명 배경 생성 완료")
        return output_buffer.getvalue()
        
    except Exception as e:
        print(f"❌ 투명 배경 생성 실패: {e}")
        # 최종 실패 시 원본 반환
        output_buffer = io.BytesIO()
        image.save(output_buffer, format='PNG')
        output_buffer.seek(0)
        return output_buffer.getvalue()

def remove_background_with_rapidapi(image_url: str) -> Optional[bytes]:
    """
    RapidAPI의 remove background API를 사용하여 배경을 제거합니다.
    
    Args:
        image_url (str): 배경을 제거할 이미지 URL
    
    Returns:
        bytes: 배경이 제거된 이미지 데이터
        None: 에러가 발생한 경우
    """
    try:
        import http.client
        import urllib.parse
        
        print(f"🔧 RapidAPI를 사용한 배경 제거 시작: {image_url}")
        

        
        # HTTP 연결 설정
        conn = http.client.HTTPSConnection("remove-background18.p.rapidapi.com")
        
        # 요청 페이로드 (URL 인코딩된 형태로 이미지 URL 전송)
        payload = urllib.parse.urlencode({
            'image_url': image_url
        })
        
        # 헤더 설정
        headers = {
            'x-rapidapi-key': "83c9d8d142msh1a0fc7490405bd2p1937f6jsnb3258526aab8",
            'x-rapidapi-host': "remove-background18.p.rapidapi.com",
            'Content-Type': "application/x-www-form-urlencoded"
        }
        
        # API 요청
        print("📡 RapidAPI에 배경 제거 요청 중...")
        conn.request("POST", "/public/remove-background", payload, headers)
        
        # 응답 받기
        res = conn.getresponse()
        data = res.read()
        conn.close()
        
        print(f"📥 RapidAPI 응답 상태: {res.status}")
        
        if res.status != 200:
            print(f"❌ RapidAPI 요청 실패: HTTP {res.status}")
            return None
        
        # 응답 데이터 파싱
        try:
            import json
            response_data = json.loads(data.decode("utf-8"))
            print(f"📋 RapidAPI 응답: {response_data}")
            
            # 응답에서 결과 URL 추출 (API 응답 구조에 따라 조정 필요)
            result_url = None
            if isinstance(response_data, dict):
                # 가능한 키들을 확인
                if 'result_url' in response_data:
                    result_url = response_data['result_url']
                elif 'url' in response_data:
                    result_url = response_data['url']
                elif 'output_url' in response_data:
                    result_url = response_data['output_url']
                elif 'image_url' in response_data:
                    result_url = response_data['image_url']
                elif 'data' in response_data and isinstance(response_data['data'], dict):
                    data_obj = response_data['data']
                    if 'url' in data_obj:
                        result_url = data_obj['url']
            
            if not result_url:
                print(f"❌ 응답에서 결과 URL을 찾을 수 없습니다: {response_data}")
                return None
                
            print(f"✅ 배경 제거된 이미지 URL 획득: {result_url}")
            
            # 결과 이미지 다운로드
            return download_image_from_url(result_url)
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON 응답 파싱 실패: {e}")
            print(f"원본 응답: {data.decode('utf-8')[:500]}...")
            return None
            
    except Exception as e:
        print(f"❌ RapidAPI 배경 제거 중 오류 발생: {str(e)}")
        return None

def download_image_from_url(image_url: str) -> Optional[bytes]:
    """
    URL에서 이미지를 다운로드하여 바이트 데이터로 반환합니다.
    
    Args:
        image_url (str): 다운로드할 이미지의 URL
    
    Returns:
        bytes: 다운로드된 이미지 데이터
        None: 에러가 발생한 경우
    """
    try:
        print(f"⬇️ 이미지 다운로드 시작: {image_url}")
        
        # 헤더 설정 (일부 사이트의 봇 차단 우회)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 이미지 다운로드
        response = requests.get(image_url, headers=headers, timeout=60)
        response.raise_for_status()
        
        # Content-Type 확인
        content_type = response.headers.get('content-type', '').lower()
        if 'image' not in content_type:
            print(f"⚠️ URL이 이미지가 아닙니다: {content_type}")
        
        image_data = response.content
        print(f"✅ 이미지 다운로드 완료 (크기: {len(image_data)} bytes)")
        
        return image_data
        
    except Exception as e:
        print(f"❌ 이미지 다운로드 중 오류 발생: {str(e)}")
        return None

def remove_background_from_url(image_url: str) -> Optional[bytes]:
    """
    이미지 URL에서 이미지를 다운로드하고 RapidAPI를 활용하여 배경을 제거합니다.
    
    Args:
        image_url (str): 배경을 제거할 이미지 URL
    
    Returns:
        bytes: 배경이 제거된 이미지 데이터
        None: 에러가 발생한 경우
    """
    try:
        print(f"🖼️ 배경 제거 프로세스 시작: {image_url}")
        
        # RapidAPI를 사용하여 배경 제거
        background_removed_data = remove_background_with_rapidapi(image_url)
        
        if background_removed_data:
            print(f"✅ 배경 제거 완료 (크기: {len(background_removed_data)} bytes)")
            return background_removed_data
        else:
            print("❌ 배경 제거 실패")
            return None
        
    except Exception as e:
        print(f"❌ 배경 제거 중 오류 발생: {str(e)}")
        return None

def upload_image_to_supabase(image_data: bytes, file_name: str = None) -> Optional[str]:
    """
    이미지 데이터를 Supabase 스토리지에 업로드하고 공개 URL을 반환합니다.
    
    Args:
        image_data (bytes): 업로드할 이미지 데이터
        file_name (str): 파일명 (None인 경우 UUID로 생성)
    
    Returns:
        str: 업로드된 이미지의 공개 URL
        None: 에러가 발생한 경우
    """
    try:
        supabase = get_supabase_client()
        
        # 파일명 생성
        if not file_name:
            file_name = f"bg_removed_{uuid.uuid4().hex}.png"
        
        print(f"📤 Supabase에 이미지 업로드 중: {file_name}")
        
        # 버킷명은 환경변수나 설정에 따라 조정 가능
        bucket_name = "images"  # Supabase에서 생성한 버킷명으로 변경
        
        # 이미지 업로드
        upload_response = supabase.storage.from_(bucket_name).upload(
            path=file_name,
            file=image_data,
            file_options={"content-type": "image/png"}
        )
        
        # Supabase storage 응답 확인 (에러가 없으면 성공)
        if hasattr(upload_response, 'error') and upload_response.error:
            print(f"❌ 업로드 실패: {upload_response.error}")
            return None
        else:
            print(f"✅ 이미지 업로드 성공: {file_name}")
            
            # 공개 URL 생성
            public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
            print(f"🌐 공개 URL: {public_url}")
            
            return public_url
            
    except Exception as e:
        print(f"❌ Supabase 업로드 중 오류 발생: {str(e)}")
        return None

def update_image_result_in_supabase(job_id: str, result_data: dict) -> bool:
    """
    Supabase의 image 테이블에서 job_id로 찾아서 result 컬럼을 업데이트합니다.
    
    Args:
        job_id (str): 업데이트할 행의 job_id
        result_data (dict): result 컬럼에 저장할 데이터
    
    Returns:
        bool: 업데이트 성공 여부
    """
    try:
        if not job_id:
            print("❌ job_id가 제공되지 않아 Supabase 업데이트를 건너뜁니다.")
            return False
            
        supabase = get_supabase_client()
        
        print(f"📝 Supabase image 테이블 업데이트 중 (job_id: {job_id})")
        
        # job_id로 행을 찾아서 result 컬럼 업데이트
        response = supabase.table("image").update({
            "result": result_data
        }).eq("job_id", job_id).execute()
        
        if response.data:
            print(f"✅ Supabase 업데이트 성공 (job_id: {job_id})")
            return True
        else:
            print(f"❌ job_id {job_id}에 해당하는 행을 찾을 수 없습니다.")
            return False
            
    except Exception as e:
        print(f"❌ Supabase 업데이트 중 오류 발생: {str(e)}")
        return False

@app.get("/")
async def root():
    """API 상태 확인"""
    return {"message": "이미지 묘사 API가 정상 작동중입니다.", "status": "healthy"}

@app.post("/describe", response_model=ImageDescribeResponse)
async def describe_image(request: ImageDescribeRequest):
    """
    이미지 URL과 캐릭터 ID, 사용자 정의 프롬프트를 받아서 Gemini API로 영어 묘사를 반환합니다.
    
    Args:
        request: 이미지 URL, 캐릭터 ID, 사용자 정의 프롬프트가 포함된 요청 객체
        
    Returns:
        ImageDescribeResponse: 성공/실패 상태와 묘사 결과
    """
    # 시작 시간 기록
    start_time = time.time()
    
    try:
        # 환경변수 확인
        if not os.getenv("GEMINI_API_KEY"):
            raise HTTPException(
                status_code=500, 
                detail="GEMINI_API_KEY 환경변수가 설정되지 않았습니다."
            )
        
        # character_id가 제공된 경우 로그에 기록
        character_image_url = None
        if request.character_id:
            print(f"캐릭터 ID {request.character_id}에 대한 이미지 묘사 요청")
            print("📥 캐릭터 이미지 URL 가져오는 중...")
            # 캐릭터 이미지 URL 가져오기
            character_image_url = get_random_character_image(request.character_id)
        
        # 이미지 묘사 수행
        print("🔍 이미지 묘사 생성 중...")
        description = describe_face_simple(str(request.image_url), request.custom_prompt)
        
        # 총 소요시간 계산
        processing_time = round(time.time() - start_time, 2)
        print(f"✅ 이미지 묘사 완료 (총 소요시간: {processing_time}초)")
        
        if description:
            response_data = ImageDescribeResponse(
                success=True,
                description=description,
                character_id=request.character_id,
                character_image_url=character_image_url,
                processing_time=processing_time,
                job_id=request.job_id
            )
            
            # Supabase에 결과 업데이트
            if request.job_id:
                update_image_result_in_supabase(request.job_id, response_data.dict())
            
            return response_data
        else:
            response_data = ImageDescribeResponse(
                success=False,
                character_id=request.character_id,
                character_image_url=character_image_url,
                processing_time=processing_time,
                job_id=request.job_id,
                error="이미지 묘사를 생성할 수 없습니다. 이미지 URL을 확인해주세요."
            )
            
            # Supabase에 결과 업데이트 (실패한 경우에도)
            if request.job_id:
                update_image_result_in_supabase(request.job_id, response_data.dict())
            
            return response_data
            
    except Exception as e:
        # 에러 발생 시에도 소요시간 포함
        processing_time = round(time.time() - start_time, 2)
        raise HTTPException(
            status_code=500,
            detail=f"서버 오류가 발생했습니다: {str(e)} (처리시간: {processing_time}초)"
        )

@app.post("/cartoonize", response_model=CartoonizeResponse)
async def cartoonize_image(request: CartoonizeRequest):
    """
    이미지 URL, 캐릭터 ID, 커스텀 프롬프트를 받아서 캐릭터 이미지와 결합한 카툰화 이미지를 생성합니다.
    
    Args:
        request: 이미지 URL, 캐릭터 ID, 커스텀 프롬프트가 포함된 요청 객체
        
    Returns:
        CartoonizeResponse: 성공/실패 상태와 생성된 이미지 결과
    """
    # 전체 시작 시간 기록
    start_time = time.time()
    timing = TimingInfo()
    
    try:
        # 환경변수 확인 및 유효성 검증
        gemini_key = os.getenv("GEMINI_API_KEY")
        replicate_token = os.getenv("REPLICATE_API_TOKEN")
        
        if not gemini_key:
            raise HTTPException(
                status_code=500, 
                detail="GEMINI_API_KEY 환경변수가 설정되지 않았습니다."
            )
        
        if not replicate_token:
            raise HTTPException(
                status_code=500,
                detail="REPLICATE_API_TOKEN 환경변수가 설정되지 않았습니다."
            )
        
        # API 키 길이 및 형식 간단 검증
        if len(gemini_key) < 20:
            raise HTTPException(
                status_code=500,
                detail="GEMINI_API_KEY가 올바르지 않은 형식입니다."
            )
        
        if len(replicate_token) < 20:
            raise HTTPException(
                status_code=500,
                detail="REPLICATE_API_TOKEN이 올바르지 않은 형식입니다."
            )
        
        print(f"✅ 환경변수 검증 완료 - Gemini 키: {len(gemini_key)}자, Replicate 토큰: {len(replicate_token)}자")
        
        print(f"캐릭터 ID {request.character_id}에 대한 카툰화 요청")
        
        # 1. 캐릭터 이미지 URL 가져오기
        step_start = time.time()
        print("📥 1단계: 캐릭터 이미지 URL 가져오는 중...")
        character_image_url = get_random_character_image(request.character_id)
        timing.character_image_fetch = round(time.time() - step_start, 2)
        print(f"✅ 1단계 완료 (소요시간: {timing.character_image_fetch}초)")
        
        if not character_image_url:
            timing.total_time = round(time.time() - start_time, 2)
            response_data = CartoonizeResponse(
                success=False,
                character_id=request.character_id,
                timing=timing,
                job_id=request.job_id,
                error=f"캐릭터 ID {request.character_id}에 해당하는 이미지를 찾을 수 없습니다."
            )
            
            # Supabase에 결과 업데이트 (실패한 경우에도)
            if request.job_id:
                update_image_result_in_supabase(request.job_id, response_data.dict())
            
            return response_data
        
        # 2. 입력 이미지의 얼굴 묘사 생성
        step_start = time.time()
        print("🔍 2단계: 입력 이미지의 얼굴 묘사 생성 중...")
        face_description = describe_face_simple(str(request.image_url))
        timing.face_description = round(time.time() - step_start, 2)
        print(f"✅ 2단계 완료 (소요시간: {timing.face_description}초)")
        
        if not face_description:
            timing.total_time = round(time.time() - start_time, 2)
            response_data = CartoonizeResponse(
                success=False,
                character_id=request.character_id,
                character_image_url=character_image_url,
                timing=timing,
                job_id=request.job_id,
                error="입력 이미지의 얼굴 묘사를 생성할 수 없습니다."
            )
            
            # Supabase에 결과 업데이트 (실패한 경우에도)
            if request.job_id:
                update_image_result_in_supabase(request.job_id, response_data.dict())
            
            return response_data
        
        # 3. 커스텀 프롬프트를 영어로 번역
        step_start = time.time()
        print("🔄 3단계: 커스텀 프롬프트를 영어로 번역 중...")
        translated_prompt = translate_to_english(request.custom_prompt)
        timing.prompt_translation = round(time.time() - step_start, 2)
        print(f"✅ 3단계 완료 (소요시간: {timing.prompt_translation}초)")
        
        if not translated_prompt:
            timing.total_time = round(time.time() - start_time, 2)
            response_data = CartoonizeResponse(
                success=False,
                character_id=request.character_id,
                character_image_url=character_image_url,
                face_description=face_description,
                timing=timing,
                job_id=request.job_id,
                error="커스텀 프롬프트를 번역할 수 없습니다."
            )
            
            # Supabase에 결과 업데이트 (실패한 경우에도)
            if request.job_id:
                update_image_result_in_supabase(request.job_id, response_data.dict())
            
            return response_data
        
        # 4. Replicate API로 이미지 생성
        step_start = time.time()
        print("🎨 4단계: Replicate API로 이미지 생성 중...")
        print(f"👤 얼굴 묘사: {face_description[:100]}...")
        print(f"🎬 번역된 프롬프트: {translated_prompt}")
        
        result_image_url = generate_cartoon_with_replicate(
            character_image_url, 
            face_description, 
            translated_prompt
        )
        timing.image_generation = round(time.time() - step_start, 2)
        print(f"✅ 4단계 완료 (소요시간: {timing.image_generation}초)")
        
        if result_image_url:
            print(f"✅ 이미지 생성 성공: {result_image_url}")
            
            # 5. 생성된 이미지에서 배경 제거
            step_start = time.time()
            print("🎭 5단계: 생성된 이미지에서 배경 제거 중...")
            background_removed_data = remove_background_from_url(result_image_url)
            timing.background_removal = round(time.time() - step_start, 2)
            print(f"✅ 5단계 완료 (소요시간: {timing.background_removal}초)")
            
            background_removed_url = None
            if background_removed_data:
                # 6. 배경 제거된 이미지를 Supabase에 업로드
                step_start = time.time()
                print("📤 6단계: 배경 제거된 이미지를 Supabase에 업로드 중...")
                bg_removed_filename = f"cartoon_bg_removed_{uuid.uuid4().hex}.png"
                background_removed_url = upload_image_to_supabase(background_removed_data, bg_removed_filename)
                timing.image_upload = round(time.time() - step_start, 2)
                print(f"✅ 6단계 완료 (소요시간: {timing.image_upload}초)")
                
                if background_removed_url:
                    print(f"✅ 배경 제거된 이미지 업로드 성공: {background_removed_url}")
                else:
                    print("❌ 배경 제거된 이미지 업로드 실패")
            else:
                print("❌ 배경 제거 실패")
            
            # 전체 소요시간 계산
            timing.total_time = round(time.time() - start_time, 2)
            
            print(f"🎉 모든 단계 완료! 전체 소요시간: {timing.total_time}초")
            print(f"📊 단계별 소요시간:")
            print(f"  - 캐릭터 이미지 가져오기: {timing.character_image_fetch}초")
            print(f"  - 얼굴 묘사 생성: {timing.face_description}초")
            print(f"  - 프롬프트 번역: {timing.prompt_translation}초")
            print(f"  - 이미지 생성: {timing.image_generation}초")
            print(f"  - 배경 제거: {timing.background_removal}초")
            if timing.image_upload:
                print(f"  - 이미지 업로드: {timing.image_upload}초")
            
            response_data = CartoonizeResponse(
                success=True,
                result_image_url=result_image_url,
                background_removed_image_url=background_removed_url,
                character_id=request.character_id,
                character_image_url=character_image_url,
                translated_prompt=translated_prompt,
                face_description=face_description,
                timing=timing,
                job_id=request.job_id
            )
            
            # Supabase에 결과 업데이트
            if request.job_id:
                update_image_result_in_supabase(request.job_id, response_data.dict())
            
            return response_data
        else:
            print("❌ 이미지 생성 실패 - generate_cartoon_with_replicate가 None 반환")
            
            # 전체 소요시간 계산
            timing.total_time = round(time.time() - start_time, 2)
            
            # 더 구체적인 에러 메시지 제공
            error_message = """이미지 생성에 실패했습니다. 가능한 원인:
1. Replicate API 서버 문제
2. 입력 이미지 형식 문제
3. API 토큰 문제
4. 네트워크 연결 문제
서버 로그를 확인해주세요."""
            
            response_data = CartoonizeResponse(
                success=False,
                character_id=request.character_id,
                character_image_url=character_image_url,
                translated_prompt=translated_prompt,
                face_description=face_description,
                timing=timing,
                job_id=request.job_id,
                error=error_message
            )
            
            # Supabase에 결과 업데이트 (실패한 경우에도)
            if request.job_id:
                update_image_result_in_supabase(request.job_id, response_data.dict())
            
            return response_data
            
    except Exception as e:
        # 전체 소요시간 계산
        timing.total_time = round(time.time() - start_time, 2)
        raise HTTPException(
            status_code=500,
            detail=f"서버 오류가 발생했습니다: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    try:
        # Gemini API 키 확인
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {"status": "unhealthy", "error": "GEMINI_API_KEY가 설정되지 않음"}
        
        # Supabase 연결 확인
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_ACCESS_KEY")
        if not supabase_url or not supabase_key:
            return {"status": "unhealthy", "error": "SUPABASE_URL 또는 SUPABASE_ACCESS_KEY가 설정되지 않음"}
        
        # Replicate API 키 확인
        replicate_token = os.getenv("REPLICATE_API_TOKEN")
        if not replicate_token:
            return {"status": "unhealthy", "error": "REPLICATE_API_TOKEN이 설정되지 않음"}
        
        # RapidAPI 키 확인
        rapidapi_key = os.getenv("RAPIDAPI_KEY")
        if not rapidapi_key:
            return {"status": "unhealthy", "error": "RAPIDAPI_KEY가 설정되지 않음"}
        
        return {
            "status": "healthy", 
            "gemini_api": "configured",
            "supabase": "configured",
            "replicate_api": "configured",
            "rapidapi": "configured"
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(
        "fastapi_image_describe:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True
    )
