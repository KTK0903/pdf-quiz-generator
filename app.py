import streamlit as st
from google import genai
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError
import json
import sys
import io
import os

# 시스템 인코딩 UTF-8 강제 설정 (Streamlit Cloud 환경 최적화)
os.environ["PYTHONIOENCODING"] = "utf-8"

# 1. API 키 설정 (Streamlit Cloud Secrets 보안 권장 방식)
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
except KeyError:
    st.error("❌ 'GOOGLE_API_KEY'가 Streamlit 설정에 등록되지 않았습니다. Secrets 설정을 확인해주세요.")
    st.stop()

# 최신 구글 GenAI SDK 클라이언트 초기화
client = genai.Client(api_key=GOOGLE_API_KEY)

# 2026년 기준 대용량 처리 및 유료 결제 환경에서 가장 빠르고 안정적인 모델 선정
FAST_ACCEL_MODEL = 'gemini-2.5-flash-lite'

# 웹ページ 기본 설정
st.set_page_config(page_title="PDF AI クイズ生成器", layout="centered")
st.title("📚 PDFベース AIクイズ生成器 (高速・高精度版)")

# 📢 디스클레이머(Disclaimer) 및 이용 안내 섹션
st.info("""
### 📢 ご利用に関する注意事項 (Disclaimer)
* **データの取り扱い:** アップロードされたPDFファイルは、クイズ生成の目的のみに一時的に使用され、サーバーに永久保存されることはありません。
* **AI出力の特性:** AIの性質上、クイズの解説や正解に極稀に誤りが含まれる場合があります。重要な学習の際は、必ず元のPDF教材と照らし合わせてご確認ください。
* **対応ファイル:** テキストデータが含まれるPDFに対応しています。文字が画像化されているスキャンPDFの場合、正常にテキストを読み取れないことがあります。
""")

st.write("PDFファイルをアップロードすると、AIが内容を分析して各重要テーマごとに2問ずつクイズを自動生成します。")

# 2. PDFファイルのアップロード
uploaded_file = st.file_uploader("クイズを生成するPDFファイルを選択してください", type=["pdf"])

pdf_password = ""

if uploaded_file:
    try:
        # 🔒 [모바일 에러 방지] 커서를 건드리지 않는 getvalue()를 사용하여 가상 메모리에 복사
        copied_file_check = io.BytesIO(uploaded_file.getvalue())
        reader = PdfReader(copied_file_check)
        
        if reader.is_encrypted:
            st.warning("🔒 このPDFファイルは暗号化されています。パスワードを入力してください。")
            pdf_password = st.text_input("PDFパスワード入力", type="password")
    except Exception:
        pass

# 3. クイズ生成関数
def generate_quiz_from_pdf(pdf_file, password=""):
    try:
        # 🔒 [모바일 안전장치] 원본 데이터를 안전하게 가상 메모리로 가져와 가로채기 방지
        copied_file = io.BytesIO(pdf_file.getvalue())
        reader = PdfReader(copied_file)
        
        if reader.is_encrypted:
            if not password:
                st.error("❌ パスワードが必要です。入力欄にパスワードを入力してください。")
                return None
            
            decrypt_result = reader.decrypt(password)
            if decrypt_result == 0:
                st.error("❌ パスワードが間違っています。再確認してください。")
                return None

        # STEP 1: 전체 PDF에서 텍스트 추출
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("📖 PDFからテキストを抽出しています...")
        full_text = ""
        total_pages = len(reader.pages)
        
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                full_text += text + "\n"
            progress_bar.progress(int((i + 1) / total_pages * 100))
            
        if not full_text.strip():
            st.error("❌ PDFからテキストを抽出できませんでした。スキャンされた画像PDFの可能性があります。")
            return None

        # STEP 2: Gemini API를 사용하여 테마 분석 및 테마별 2문항씩 퀴즈 생성
        status_text.text("🧠 AIが重要テーマを自動分析し、各テーマ2問ずつクイズを構築しています...")
        progress_bar.progress(50)

        prompt = f"""
        以下のテキスト内容を徹底的に分析し、まず重要なコアテーマ（トピック）を複数抽出してください。
        その後、抽出した【各重要テーマごとに必ず2問ずつ】の客観的な4択クイズを作成してください。
        出力は必ず指定されたJSONフォーマットの構造のみにしてください。他の説明文やバッククォート(```)は一切含めないでください。

        【テキスト内容】:
        {full_text}
        """

        # JSON 출력을 강제하고 동적 테마별 문제를 받아내는 구조화 설정
        response = client.models.generate_content(
            model=FAST_ACCEL_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "system_instruction": """
                あなたは優秀な教育専門家です。提供されたテキストから重要なテーマを自動で抽出し、
                それぞれのテーマごとに異なる角度から2問ずつ問題を出題してください（例：テーマが3つなら計6問、5つなら計10問）。
                
                必ず以下のJSONフォーマットの構造に従って出力してください。
                
                {
                  "quizzes": [
                    {
                      "theme": "抽出した重要テーマ名",
                      "number": 1,
                      "question": "問題文",
                      "options": ["選択肢1", "選択肢2", "選択肢3", "選択肢4"],
                      "answer": "正解の選択肢(optionsの中の文字列と完全一致するもの)",
                      "explanation": "解説文"
                    }
                  ]
                }
                """
            }
        )

        progress_bar.progress(100)
        status_text.empty()
        
        # 결과 JSON 파싱
        quiz_data = json.loads(response.text)
        return quiz_data.get("quizzes", [])

    except json.JSONDecodeError:
        st.error("❌ AIの出力データをパースできませんでした。もう一度お試しください。")
        return None
    except Exception as e:
        st.error(f"❌ クイズ生成中にエラーが発生しました: {e}")
        return None

# 4. 화면 UI 및 실행 로직
if uploaded_file:
    if st.button("✨ AIクイズを生成する", type="primary"):
        with st.spinner("생성 중..."):
            # 이전 퀴즈 기록 초기화
            if "generated_quizzes" in st.session_state:
                del st.session_state["generated_quizzes"]
                
            quizzes = generate_quiz_from_pdf(uploaded_file, pdf_password)
            
            if quizzes:
                st.session_state["generated_quizzes"] = quizzes
                st.success(f"✅ クイズが正常に生成されました！(計 {len(quizzes)} 問)")

# 5. 생성된 퀴즈 화면에 출력
if "generated_quizzes" in st.session_state:
    st.write("---")
    st.header("📝 生成されたクイズ")
    
    current_theme = ""
    for idx, q in enumerate(st.session_state["generated_quizzes"]):
        # 테마가 바뀔 때마다 화면에 테마 헤더 출력
        quiz_theme = q.get('theme', '一般')
        if quiz_theme != current_theme:
            current_theme = quiz_theme
            st.markdown(f"### 📌 テーマ: {current_theme}")
            
        st.subheader(f"Q{idx+1}. {q.get('question')}")
        
        # 라디오 버튼을 이용한 문제 출제
        options = q.get("options", [])
        user_ans = st.radio(f"選択肢を選んでください (Q{idx+1})", options, key=f"q_{idx}")
        
        # 정답 확인 확장 레이아웃
        with st.expander("👁️ 正解と解説を確認する"):
            correct_ans = q.get("answer")
            st.write(f"**💡 正解:** {correct_ans}")
            st.write(f"**📖 解説:** {q.get('explanation')}")
            
            if user_ans == correct_ans:
                st.success("🎯 正解です！")
            else:
                st.info("✍️ もう一度考えてみましょう。")
        st.write("")
