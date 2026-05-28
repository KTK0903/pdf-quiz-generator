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
    st.error("❌ 'GOOGLE_API_KEY'가 Streamlit 설정に登録されていません。Secrets設定を確認してください。")
    st.stop()

# 최신 구글 GenAI SDK 클라이언트 초기화
client = genai.Client(api_key=GOOGLE_API_KEY)

# 👑 유료 결제 버프를 100% 활용하는 대용량 전용 오리지널 2.5 Flash 모델 고정
FAST_ACCEL_MODEL = 'gemini-2.5-flash'

# 웹페이지 기본 설정
st.set_page_config(page_title="PDF AI クイズ生成器", layout="centered")
st.title("📚 PDFベース AIクイズ生成器 (テーマ別大量生成版)")

# 📢 디스클레이머(Disclaimer) 및 이용 안내 섹션
st.info("""
### 📢 ご利用に関する注意事項 (Disclaimer)
* **データの取り扱い:** アップロードされたPDFファイルは、クイズ生成の目的のみに一時的に使用され、サーバーに永久保存されることはありません。
* **AI出力の特性:** AIの性質上、クイズの解説や正解に極稀に誤りが含まれる場合があります。重要な学習の際は、必ず元のPDF教材と照らし合わせてご確認ください。
* **対応ファイル:** テキストデータが含まれるPDFに対応しています。文字が画像化されているスキャンPDFの場合、正常にテキストを読み取れないことがあります。
""")

st.write("PDFファイルをアップロードすると、AIが内容から重要なテーマを網羅的に自動抽出し、各テーマごとに2問以上ずつクイズを限界まで自動生成します。")

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

        # STEP 2: 개수 제한 없는 오리지널 대용량 동적 테마별 생성 프롬프트
        status_text.text("🧠 AIが本文全体を網羅的に分析し、すべての重要テーマを抽出して各2問以上ずつクイズを生成しています...")
        progress_bar.progress(50)

        prompt = f"""
        提供されたテキスト内容全体を網羅的に分析し、重要なコアテーマ（章、トピック、概念）を【制限なく可能な限り多く】抽出してください。
        そして、抽出した【すべての重要テーマごとに、それぞれ異なる角度から必ず2問以上ずつ】客観的な4択クイズを作成してください。
        
        全体の総問題数に上限は設けません。テキストの量が多い場合は、テーマ数を増やして比例して全体のクイズ数が多くなるように（例：テーマが7つなら14問以上、10個なら20問以上）徹底的に出題してください。
        出力は必ず指定されたJSONフォーマットの構造のみにしてください。他の説明文やマークダウンのバッククォート(```)は一切含めないでください。

        【テキスト内容】:
        {full_text}
        """

        # JSON 출력을 강제하고 동적 테마별 다문항을 받아내는 구조화 설정
        response = client.models.generate_content(
            model=FAST_ACCEL_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "system_instruction": """
                あなたは妥協を許さない優秀な教育専門家です。提供されたテキストの全範囲を漏れなくカバーしてください。
                本文から抽出できる重要なテーマや概念をすべて洗い出し、それぞれのテーマ（theme）ごとに【必ず2問以上ずつ】の4択クイズを出力してください。
                問題数を意図的に間引いたり、10問程度に省略したりすることは絶対に許されません。見つかったすべての重要トピックについて、深い理解を問う問題を各2問以上網羅した膨大な問題セットを構築してください。
                
                必ず以下のJSONフォーマットの構造に従って出力してください。
                
                {
                  "quizzes": [
                    {
                      "theme": "抽出した重要テーマ・章の名前",
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
    if st.button("✨ AIクイズを自動生成する", type="primary"):
        with st.spinner("생성 중..."):
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
        quiz_theme = q.get('theme', '総合')
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
