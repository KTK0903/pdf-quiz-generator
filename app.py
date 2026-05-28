import streamlit as st
from google import genai
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError
import json
import sys
import io
import os

# 인코딩 관련 속도 저하 및 에러 방지

os.environ["PYTHONIOENCODING"] = "utf-8"

# Streamlit Cloud 비밀 금고에서 안전하게 API 키 로드
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

try:
    client = genai.Client(api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"APIキーの初期化に失敗しました。キーを確認してください: {e}")

st.set_page_config(page_title="AIクイズ生成器", page_icon="📚", layout="centered")
st.title("📚 PDFベース AIクイズ生成器 (高速・高精度版)")
st.write("30万字を超える長大なドキュメントも、**全ページを完全に解析**して漏れなくテーマを認識し、各テーマから最低2問ずつのクイズを生成します。")

# ⚠️ 저작권 및 보안 Disclaimer 경고창
st.warning("""
**⚠️ 【ご利用上の注意 / Disclaimer】**
1. **著作権の遵守:** アップロードするPDFファイルは、必ず**著作権法を侵害しないもの**（ご自身が所有する資料、パブリックドメイン、または利用許諾を得たもの）に限ります。著作権で保護された教科書や書籍、他人の論文などを無断でアップロードしないでください。
2. **データの保護:** 本システムに入力されたデータは、AIモデルの性能向上のために使用される場合があります。個人情報や機密情報が含まれるファイルはアップロードしないでください。
*※万が一、著作権侵害等のトラブルが発生した場合、開発者は一切の責任を負いかねます。*
""")

# 세션 상태 초기화
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}

# PDF 파일 업로드
uploaded_file = st.file_uploader("クイズを生成するPDFファイルを選択してください", type=["pdf"])

pdf_password = ""

if uploaded_file:
    try:
        reader = PdfReader(uploaded_file)
        if reader.is_encrypted:
            st.warning("🔒 このPDFファイルは暗号化されています。パスワードを入力してください。")
            pdf_password = st.text_input("PDFパスワード入力", type="password")
    except Exception:
        pass

# 고속 퀴즈 생성 함수
def generate_quiz_from_pdf(pdf_file, password=""):
    try:
        reader = PdfReader(pdf_file)
        
        if reader.is_encrypted:
            if not password:
                st.error("❌ パスワードが必要です。入力欄にパスワードを入力してください。")
                return None
            
            decrypt_result = reader.decrypt(password)
            if decrypt_result == 0:
                st.error("❌ パスワードが間違っています。再確認してください。")
                return None

        # 텍스트 추출 가속화
        pages_text = [page.extract_text().strip() for page in reader.pages if page.extract_text() and page.extract_text().strip()]
        
        total_pages = len(pages_text)
        if total_pages == 0:
            st.error("❌ PDFからテキストを抽出できませんでした。")
            return None

        full_text = "\n\n".join(pages_text)
        total_chars = len(full_text)
        
        status_text = st.empty()
        status_text.info(f"📊 抽出完了: 全 {total_pages} ページ / 総文字数 約 {total_chars:,} 字。")

        # 🚀 고성능 차세대 고속 엔진 지정
        FAST_ACCEL_MODEL = 'gemini-2.0-flash'

        # STEP 1: 핵심 테마 고속 추출
        status_text.info("🔍 STEP 1: ドキュメント全体の独立したテーマ・概念を高速分析中...")
        
        theme_prompt = f"""
        あなたは非常に優秀なデータアナリストであり教育専門家です。
        提供されたテキストは、文字数が約30万字に及ぶ非常に長大で専門的なドキュメント全体です。
        データの最初から最後までを完全に読み込み、省略することなく、このドキュメントに存在する重要な【独立した主要テーマや核心概念】を漏れなくすべて抽出してください。
        後半に登場する重要な概念が無視されないよう、全体から均等かつ網羅的に抽出し、それぞれについて日本語で3文程度で要約・説明してください。数量制限はありません。すべて挙げてください。

        [超大容量テキスト内容]
        {full_text}
        """
        
        theme_response = client.models.generate_content(
            model=FAST_ACCEL_MODEL,
            contents=theme_prompt,
        )
        extracted_themes = theme_response.text
        
        # STEP 2: 추출된 테마를 기반으로 퀴즈 빌드
        status_text.info("📝 STEP 2: 各テーマから最低2問ずつ、深掘りクイズを高速構築中...")
        
        quiz_prompt = f"""
        あなたは教育の専門家です。以下の【分析された主要テーマ・概念】のリストをベースにクイズを作成してください。
        
        【重要指示】
        1. 提示された【すべてのテーマ】を一つも漏らすことなく対象にしてください。
        2. 【各テーマごとに必ず最低2問以上】の客観式4択クイズを作成してください。
        3. 必ず【日本語】で作成し、出力は以下のJSON形式のみを返してください。解説（explanation）も含めてください。マークダウン（```jsonなど）や他の説明は絶対に含めないでください。

        [形式]
        [
          {{
            "question": "問題文",
            "options": ["選択肢1", "選択肢2", "選択肢3", "選択肢4"],
            "answer": "正解의 문자열 (optionsにある文字列と完全に一致させること)",
            "explanation": "解説内容"
          }}
        ]

        [分析された主要テーマ・概念]
        {extracted_themes}
        """
        
        quiz_response = client.models.generate_content(
            model=FAST_ACCEL_MODEL,
            contents=quiz_prompt,
        )
        status_text.empty()
        
        # JSON 정제 및 로딩
        cleaned_text = quiz_response.text.strip().replace("```json", "").replace("```", "")
        quiz_json = json.loads(cleaned_text)
        
        st.success(f"📊 分析完了！計 {len(quiz_json)} 問の深掘りクイズが完成しました。")
        return quiz_json

    except FileNotDecryptedError:
        st.error("❌ PDFファイルがロックされています。正しいパスワードを入力してください。")
        return None
    except Exception as e:
        st.error(f"クイズ生成中にエラーが発生しました: {str(e)}")
        return None

# 퀴즈 생성 버튼 클릭 시
if uploaded_file:
    if st.button("✨ AIクイズを生成する"):
        with st.spinner("Geminiがドキュメント全体を高速網羅し、クイズを作成しています..."):
            st.session_state.quiz_data = generate_quiz_from_pdf(uploaded_file, pdf_password)
            st.session_state.user_answers = {}

# 4. 퀴즈 화면 출력
if st.session_state.quiz_data:
    st.write("---")
    st.header("📝 クイズに挑戦")
    
    for idx, item in enumerate(st.session_state.quiz_data):
        st.subheader(f"Q{idx+1}. {item['question']}")
        user_choice = st.radio(
            f"選択肢を選んでください (Q{idx+1})", 
            item['options'], 
            key=f"q_{idx}",
            index=None,
            label_visibility="collapsed"
        )
        st.session_state.user_answers[idx] = user_choice
        st.write("")

    if st.button("💯 採点する"):
        st.write("---")
        st.header("📊 採点結果")
        
        correct_count = 0
        for idx, item in enumerate(st.session_state.quiz_data):
            user_ans = st.session_state.user_answers.get(idx)
            actual_ans = item['answer']
            
            st.markdown(f"**Q{idx+1}. {item['question']}**")
            st.write(f"あなたの解答: {user_ans if user_ans else '未選択'}")
            
            if user_ans == actual_ans:
                st.success("🎉 正解です！")
                correct_count += 1
            else:
                st.error(f"❌ 不正解です。 (正解: {actual_ans})")
            
            st.info(f"💡 解説: {item['explanation']}")
            st.write("")
            
        st.metric(label="総合スコア", value=f"{correct_count} / {len(st.session_state.quiz_data)} 問正解")
