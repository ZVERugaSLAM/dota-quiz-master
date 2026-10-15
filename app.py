import streamlit as st
import requests
import json
import os
import random
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN") or st.secrets.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID") or st.secrets.get("CHAT_ID", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD") or st.secrets.get("APP_PASSWORD", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", "")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID") or st.secrets.get("SPREADSHEET_ID", "")

GLOBAL_MECHANICS = [
    "Рошан та Аегіс",
    "Руни (Баунті, Води, Підсилення)",
    "Кріпи (Лінійні, Нейтрали, Стаки)",
    "Терзачі (Tormentors)",
    "Аванпости (Outposts) та Ставки лотосів",
    "Нейтральні артефакти",
    "Економіка та таймінги збірок за рангами MMR",
    "Ландшафт, дерева та віжн (Wards)"
]

MECHANICS_IMAGES = {
    "Рошан та Аегіс": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/aegis.png",
    "Руни (Баунті, Води, Підсилення)": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/bottle.png",
    "Кріпи (Лінійні, Нейтрали, Стаки)": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/quelling_blade.png",
    "Терзачі (Tormentors)": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/aghanims_shard.png",
    "Аванпости (Outposts) та Ставки лотосів": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/flask.png",
    "Нейтральні артефакти": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/trusty_shovel.png",
    "Економіка та таймінги збірок за рангами MMR": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/hand_of_midas.png",
    "Ландшафт, дерева та віжн (Wards)": "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/ward_observer.png"
}

st.set_page_config(page_title="Dota 2 Quiz Master", page_icon="🕹️", layout="wide")

if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = {
        "question": "",
        "options": ["", "", "", ""],
        "correct_index": 0,
        "explanation": ""
    }

@st.cache_resource
def init_gsheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    try:
        if os.path.exists("credentials.json"):
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        else:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID).sheet1
    except Exception as e:
        st.error(f"Помилка підключення до Google Sheets: {e}")
        return None

sheet = init_gsheets()

def get_topic_history(topic_name):
    if sheet is None: return []
    try:
        values = sheet.get_all_values()
        return [row[1] for row in values if len(row) > 1 and row[0] == topic_name]
    except Exception:
        return []

def save_to_history(topic_name, question, options, correct_index, explanation):
    if sheet is None: return
    try:
        sheet.append_row([topic_name, question, json.dumps(options), correct_index, explanation])
    except Exception as e:
        st.error(f"Помилка збереження в історію: {e}")

def clear_topic_history(topic_name):
    if sheet is None: return False
    try:
        cells = sheet.findall(topic_name, in_column=1)
        if not cells:
            return True
        rows_to_delete = sorted([cell.row for cell in cells], reverse=True)
        for row in rows_to_delete:
            sheet.delete_rows(row)
        return True
    except Exception as e:
        st.error(f"Помилка видалення: {e}")
        return False

@st.cache_data(ttl=3600)
def fetch_dota_heroes():
    try:
        response = requests.get("https://api.opendota.com/api/heroStats")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Помилка завантаження героїв: {e}")
    return []

def generate_llm_quiz_rest(topic_name, category_type, custom_prompt, history):
    if not GEMINI_API_KEY:
        st.error("API ключ Gemini не знайдено!")
        return None
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"
    
    history_str = "\n".join(f"- {q}" for q in history) if history else "Поки що немає."
    custom_str = f"ЗАПИТ ВІД КОРИСТУВАЧА: {custom_prompt}" if custom_prompt else ""
    
    if category_type == "hero":
        instruction = f"Створи одне складне, неочевидне питання для вікторини з фокусом на героя {topic_name}. ДОЗВОЛЕНІ ТЕМИ: глибока механіка здібностей, базова шкода/характеристики, взаємодія з предметами та іншими героями, таймінги. КАТЕГОРИЧНО ЗАБОРОНЕНО: лор."
    else:
        instruction = f"Створи одне складне, неочевидне питання для вікторини про ігрову об'єкт/механіку: {topic_name}. Фокус має бути на точних цифрах (таймінги появи, формули шкоди/золота, час дії ефектів) або на специфічних механіках взаємодії гравців з цим об'єктом. КАТЕГОРИЧНО ЗАБОРОНЕНО: лор."
    
    prompt = f"""
    Ти хардкорний експерт з Dota 2. 
    {instruction}
    
    ІСТОРІЯ ПОПЕРЕДНІХ ПИТАНЬ (не дублюй їхню суть):
    {history_str}
    
    {custom_str}
    
    Поверни результат СУВОРО у форматі JSON.
    {{
        "question": "текст питання (до 250 символів)",
        "options": ["варіант 1", "варіант 2", "варіант 3", "варіант 4"],
        "correct_index": 0,
        "explanation": "коротке пояснення (до 150 символів)"
    }}
    Зверни увагу: correct_index - це ціле число від 0 до 3. Відповіді мають бути українською мовою.
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        raw_text = data['candidates'][0]['content']['parts'][0]['text']
        return json.loads(raw_text)
    except Exception as e:
        st.error(f"Помилка генерації через API: {e}")
        return None

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form"):
                st.markdown("<h3 style='text-align: center;'>🔐 Авторизація доступу</h3>", unsafe_allow_html=True)
                pwd = st.text_input("Введіть пароль", type="password", label_visibility="collapsed", placeholder="Введіть пароль...")
                submitted = st.form_submit_button("Увійти", use_container_width=True)
                
                if submitted:
                    if pwd == APP_PASSWORD:
                        st.session_state["password_correct"] = True
                        st.rerun()
                    else:
                        st.error("Невірний пароль.")
        return False
    return True

def send_telegram_quiz(question, options, correct_index, explanation):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPoll"
    payload = {
        "chat_id": CHAT_ID,
        "question": question,
        "options": json.dumps(options),
        "is_anonymous": False,
        "type": "quiz",
        "correct_option_id": correct_index,
        "explanation": explanation
    }
    response = requests.post(url, data=payload)
    return response.json()

if check_password():
    heroes = fetch_dota_heroes()
    
    with st.sidebar:
        st.image("https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/global/dota2_logo_symbol.png", width=80)
        
        category = st.radio("Тематика вікторини:", ("🦸‍♂️ Герої", "🌍 Глобальні механіки"))
        st.divider()
        
        if category == "🦸‍♂️ Герої":
            if heroes:
                hero_names = [h["localized_name"] for h in heroes]
                selected_topic = st.selectbox("Обери героя:", hero_names)
                
                selected_hero_data = next(h for h in heroes if h["localized_name"] == selected_topic)
                img_url = "https://cdn.cloudflare.steamstatic.com" + selected_hero_data["img"]
                st.image(img_url, caption=selected_topic, use_column_width=True)
                st.markdown(f"**Атрибут:** {selected_hero_data['primary_attr'].upper()} | **Ролі:** {', '.join(selected_hero_data['roles'])}")
                cat_type = "hero"
            else:
                st.warning("Не вдалося завантажити героїв.")
                selected_topic = None
        else:
            selected_topic = st.selectbox("Обери механіку:", GLOBAL_MECHANICS)
            img_url = MECHANICS_IMAGES.get(selected_topic, "")
            if img_url:
                st.image(img_url, caption=selected_topic, use_column_width=True)
            cat_type = "mechanic"
            
        st.divider()
        st.markdown("🤖 **Автогенерація:**")
        custom_prompt_input = st.text_area("Кастомний запит (опціонально)", placeholder="Додаткові побажання до питання", max_chars=150)
        
        if selected_topic and st.button("✨ Згенерувати питання", use_container_width=True):
            with st.spinner("LLM аналізує дані..."):
                history = get_topic_history(selected_topic)
                llm_data = generate_llm_quiz_rest(selected_topic, cat_type, custom_prompt_input, history)
                if llm_data:
                    original_options = llm_data["options"]
                    original_correct_idx = llm_data.get("correct_index", 0)
                    
                    paired_options = [(text, i == original_correct_idx) for i, text in enumerate(original_options)]
                    random.shuffle(paired_options)
                    
                    llm_data["options"] = [pair[0] for pair in paired_options]
                    new_correct_idx = next(i for i, pair in enumerate(paired_options) if pair[1])
                    llm_data["correct_index"] = new_correct_idx
                    
                    st.session_state.quiz_data = llm_data
                    st.session_state.correct_radio = f"Варіант {new_correct_idx + 1}"
                    st.rerun()
                    
        st.divider()
        with st.expander("⚙️ Керування пам'яттю"):
            st.markdown(f"Очищення історії запитів для: **{selected_topic}**")
            confirm_delete = st.checkbox("Підтверджую видалення")
            if st.button("🗑️ Очистити історію", disabled=not confirm_delete, use_container_width=True):
                with st.spinner("Видалення з бази..."):
                    if clear_topic_history(selected_topic):
                        st.success("Історію очищено!")
                    else:
                        st.error("Помилка очищення.")

    st.title("🕹️ Dota 2 Quiz Master")
    st.caption("Панель керування вікторинами для чату")
    st.markdown("### 📝 Створення нової вікторини")
    
    qd = st.session_state.quiz_data
    question = st.text_input("Питання вікторини", value=qd["question"], max_chars=300)
    
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        opt1 = st.text_input("Варіант 1", value=qd["options"][0] if len(qd["options"]) > 0 else "")
        opt3 = st.text_input("Варіант 3", value=qd["options"][2] if len(qd["options"]) > 2 else "")
    with col_opt2:
        opt2 = st.text_input("Варіант 2", value=qd["options"][1] if len(qd["options"]) > 1 else "")
        opt4 = st.text_input("Варіант 4", value=qd["options"][3] if len(qd["options"]) > 3 else "")
        
    options_list = [opt1, opt2, opt3, opt4]
    
    st.radio(
        "Який варіант є правильним?",
        ("Варіант 1", "Варіант 2", "Варіант 3", "Варіант 4"),
        index=qd.get("correct_index", 0),
        horizontal=True,
        key="correct_radio"
    )
    correct_index = int(st.session_state.correct_radio.split()[1]) - 1
    
    explanation = st.text_input("Пояснення (з'явиться після відповіді)", value=qd["explanation"], max_chars=200)
    
    if st.button("🚀 Опублікувати в чат", type="primary", use_container_width=True):
        valid_options = [opt.strip() for opt in options_list if opt.strip()]
        actual_correct_index = valid_options.index(options_list[correct_index].strip()) if options_list[correct_index].strip() in valid_options else -1
        
        if not question.strip():
            st.error("Помилка: Питання не може бути порожнім.")
        elif len(valid_options) < 2:
            st.error("Помилка: Необхідно вказати мінімум 2 варіанти відповіді.")
        elif actual_correct_index == -1:
            st.error("Помилка: Правильним варіантом обрано порожнє поле.")
        else:
            with st.spinner("Відправка та збереження в базу..."):
                res = send_telegram_quiz(question, valid_options, actual_correct_index, explanation)
                if res.get("ok"):
                    save_to_history(selected_topic, question, valid_options, actual_correct_index, explanation)
                    st.success("✅ Вікторина успішно опублікована та збережена в історію!")
                    st.balloons()
                    st.session_state.quiz_data = {"question": "", "options": ["", "", "", ""], "correct_index": 0, "explanation": ""}
                    st.session_state.correct_radio = "Варіант 1"
                else:
                    st.error(f"Помилка Telegram API: {res.get('description')}")
