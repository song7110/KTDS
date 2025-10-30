# streamlit run fairSample.py

import os
from dotenv import load_dotenv
import json
import streamlit as st
from openai import AzureOpenAI

load_dotenv()

# OpenAI API 키 입력
# openai.api_key = os.getenv("OPENAI_API_KEY")
# openai.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
# openai.api_type = os.getenv("OPENAI_API_TYPE")
# openai.api_version = os.getenv("OPENAI_API_VERSION")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_AI_SEARCH_ENDPOINT = os.getenv("AZURE_AI_SEARCH_ENDPOINT")
AZURE_AI_SEARCH_API_KEY = os.getenv("AZURE_AI_SEARCH_API_KEY")
DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME")
DEPLOYMENT_EMBEDDING_NAME = os.getenv("DEPLOYMENT_EMBEDDING_NAME")
INDEX_NAME = "unfair"

chat_client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version="2024-12-01-preview",
)

prompt =[
    {"role": "assistant", 
     "content": "공정경쟁 시스템 사전심의 심사자로, 관련 법령과 유사 사례를 바탕으로 심의처리"},
]

# Azure AI Search parameters
rag_params = {
    "data_sources": [
        {
            # he following params are used to search the index
            "type": "azure_search",
            "parameters": {
                "endpoint": AZURE_AI_SEARCH_ENDPOINT,
                "index_name": INDEX_NAME,
                "authentication": {
                    "type": "api_key",
                    "key": AZURE_AI_SEARCH_API_KEY,
                },
                # The following params are used to vectorize the query
                "query_type": "simple",
                "embedding_dependency": {
                    "type": "deployment_name",
                    "deployment_name": DEPLOYMENT_EMBEDDING_NAME,
                },
            }
        }
    ],
}

class RAGFairEngine:
    def __init__(self, data_dir):
        self.laws = self._load_json(os.path.join(data_dir, "laws.json"))
        self.cases = self._load_json(os.path.join(data_dir, "cases.json"))

    def _load_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    
    def retrieve(self, text, category=None):
        tokens = text.lower().split()
        matched_laws = [law for law in self.laws if any(t in law["text"].lower() for t in tokens)]
        if category:
            matched_cases = [
                case for case in self.cases
                if category in case.get("tags", []) and any(t in case["summary"].lower() for t in tokens)
            ]
        else:
            matched_cases = [case for case in self.cases if any(t in case["summary"].lower() for t in tokens)]
        return matched_laws, matched_cases

    def generate(self, text, matched_laws, matched_cases):
        law_str = "\n".join([f"- {law['title']}: {law['text']}" for law in matched_laws])
        case_str = "\n".join([f"- {case['title']}: {case['summary']} (결과: {case['outcome']})" for case in matched_cases])
        prompt =[
                    {"role": "assistant",
                     "content": "공정경쟁 시스템 사전심의 심사자로, 관련 법령과 유사 사례를 바탕으로 심의처리"},
                    {"role": "user",
                     "content": f"다음은 공정경쟁 사전심의 요청입니다.\n"
                                f"심의 내용: {text}\n\n"
                                f"관련 법령:\n{law_str if law_str else '없음'}\n\n"
                                f"유사 판례:\n{case_str if case_str else '없음'}\n\n"
                                f"위 정보를 바탕으로 구체적인 법령을 명시해서 심사 결과를 알려주세요."}
                ]

        response = chat_client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=prompt,
            extra_body=rag_params
        )
        return response.choices[0].message.content

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

st.set_page_config(page_title="사전심의 입력 및 결과", layout="wide")
st.title("공정경쟁 사전심의 등록")

if "submission" not in st.session_state:
    st.session_state.submission = {}

engine = RAGFairEngine(data_dir=DATA_DIR)

category_options = [
    "선택",
    "요금제/부가서비스 출시",
    "표시광고",
    "신규사업 추진",
    "계열사 거래",
    "사업 합리화",
    "기타"
]
service_options = [
    "선택",
    "모바일",
    "인터넷",
    "IPTV",
    "SOIP(인터넷전화)",
    "PSTN(유선전화)",
    "WIBRO",
    "전용회선",
    "기타"
]


st.subheader("사전심의 등록")

with st.form("심의입력폼"):
    title = st.text_input("제목", value=st.session_state.submission.get("title", ""))
    category = st.selectbox("카테고리", category_options, index=category_options.index(st.session_state.submission.get("category", category_options[0])) if st.session_state.submission.get("category") else 0)
    service = st.selectbox(
        "서비스명",
        service_options,
        index=service_options.index(st.session_state.submission.get("service", service_options[0])) if st.session_state.submission.get("service") else 0
    )
    default_content = "○ 의뢰배경\n\n\n○ 의뢰내용\n\n\n○ 서비스/시장현황(경쟁사, 관련업체 현황 등)\n"
    content = st.text_area(
        "내용",
        value=st.session_state.submission.get("content", default_content),
        height=300
    )
    attachments = st.file_uploader(
        "첨부파일 등록", 
        type=["pdf", "doc", "docx", "hwp", "xlsx", "ppt", "pptx", "txt", "zip", "jpg", "jpeg", "png"],
        accept_multiple_files=True
    )
    submitted = st.form_submit_button("등록 및 결과 확인")

if submitted:
    if not title.strip():
        st.warning("제목을 입력하세요.")
    elif category == "선택":
        st.warning("카테고리를 선택하세요.")
    elif service == "선택":
        st.warning("서비스명을 선택하세요.")
    elif not content.strip():
        st.warning("내용을 입력하세요.")
    else:
        st.session_state.submission = {
            "title": title,
            "category": category,
            "service": service,
            "content": content,
            "attachments": attachments if attachments else []
        }

if st.session_state.submission.get("title") and st.session_state.submission.get("content"):
    st.success("심의가 등록되었습니다. 아래는 심의 결과입니다.")
    sub = st.session_state.submission
    if sub.get("attachments"):
        for f in sub["attachments"]:
            if f.type in ["image/png", "image/jpeg", "image/jpg"]:
                st.image(f, caption=f.name, width=200)
            else:
                st.download_button(label=f"{f.name}", data=f.read(), file_name=f.name)
    
    ### RAG
    with st.spinner("관련 법령/사례 검색 중..."):
        matched_laws, matched_cases = engine.retrieve(content, category)
    with st.spinner("AI 답변 생성 중..."):
        answer = engine.generate(content, matched_laws, matched_cases)
    st.markdown("---")
    st.subheader("RAG 기반 심의 결과")
    st.markdown(answer)
    # if matched_laws:
    #     st.markdown("**관련 법령**")
    #     for law in matched_laws:
    #         st.write(f"- {law['title']}: {law.get('text','')}")
    # if matched_cases:
    #     st.markdown("**유사 판례**")
    #     for case in matched_cases:
    #         st.write(f"- {case['title']}: {case.get('summary','')} (결과: {case.get('outcome','')})")
    ### RAG END ###

if st.button("새로 등록하기"): 
    st.session_state.clear()
