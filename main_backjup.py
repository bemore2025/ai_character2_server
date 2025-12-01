from openai import OpenAI
import base64
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 흰티를 빨강티로 바꾸는 프롬프트
prompt = """Please change him to crying"""

def encode_image(file_path):
    with open(file_path, "rb") as f:
        base64_image = base64.b64encode(f.read()).decode("utf-8")
    return base64_image

def create_file(file_path):
    with open(file_path, "rb") as file_content:
        result = client.files.create(
            file=file_content,
            purpose="vision",
        )
        return result.id

# woman.png 파일 처리
base64_image = encode_image("general.png")
file_id = create_file("general.png")

response = client.responses.create(
    model="gpt-4.1",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{base64_image}",
                },
                {
                    "type": "input_image",
                    "file_id": file_id,
                }
            ],
        }
    ],
    tools=[{"type": "image_generation"}],
)

image_generation_calls = [
    output
    for output in response.output
    if output.type == "image_generation_call"
]

image_data = [output.result for output in image_generation_calls]

if image_data:
    image_base64 = image_data[0]
    # 결과 이미지를 red_tshirt_woman.png로 저장
    with open("red_tshirt_woman.png", "wb") as f:
        f.write(base64.b64decode(image_base64))
    print("이미지 변환이 완료되었습니다. red_tshirt_woman.png 파일을 확인해주세요.")
else:
    print("이미지 생성에 실패했습니다:")
    print(response.output.content)