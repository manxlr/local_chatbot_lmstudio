import streamlit as st
import streamlit_authenticator as stauth
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime
import bcrypt
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

# Database setup
Base = declarative_base()
engine = create_engine('sqlite:///chatbot.db', echo=False)
SessionLocal = sessionmaker(bind=engine)

# Database models
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    chats = relationship('Chat', back_populates='user')

class Chat(Base):
    __tablename__ = 'chats'
    id = Column(Integer, primary_key=True)
    name = Column(String, default="New Chat")
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User', back_populates='chats')
    messages = relationship('Message', back_populates='chat')

class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.id'))
    sender = Column(String)
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    chat = relationship('Chat', back_populates='messages')

Base.metadata.create_all(bind=engine)

# Authentication setup
credentials = {
    'usernames': {
        'demo': {
            'name': 'Demo User',
            'password': bcrypt.hashpw('password'.encode(), bcrypt.gensalt()).decode()
        }
    }
}

authenticator = stauth.Authenticate(credentials, 'chat_cookie', 'chat_cookie_key', cookie_expiry_days=1)

st.title("🧑‍💻 Chatbot")

authenticator.login(location="main")
name = st.session_state.get("name")
username = st.session_state.get("username")
auth_status = st.session_state.get("authentication_status")

if auth_status:
    authenticator.logout("Logout", location="sidebar")
    st.sidebar.success(f"Welcome, {name}")

    db = SessionLocal()

    user = db.query(User).filter_by(username=username).first()
    if not user:
        user = User(username=username, password_hash="")
        db.add(user)
        db.commit()
        db.refresh(user)

    chat_names = [chat.name for chat in user.chats]
    selected_chat_name = st.sidebar.selectbox("Your Chats", ["➕ New Chat"] + chat_names)

    if selected_chat_name == "➕ New Chat":
        if st.sidebar.button("Create Chat"):
            new_chat = Chat(name=f"Chat {len(user.chats)+1}", user=user)
            db.add(new_chat)
            db.commit()
            st.session_state.selected_chat_id = new_chat.id
            st.rerun()
        selected_chat = None
    else:
        selected_chat = db.query(Chat).filter_by(name=selected_chat_name, user=user).first()
        st.session_state.selected_chat_id = selected_chat.id

    # Check if chat id is already stored (fixes issue on rerun)
    if 'selected_chat_id' in st.session_state:
        selected_chat = db.query(Chat).filter_by(id=st.session_state.selected_chat_id).first()
    else:
        selected_chat = None

    if selected_chat:
        st.header(f"💬 {selected_chat.name}")
        for msg in selected_chat.messages:
            with st.chat_message(msg.sender):
                st.markdown(msg.content)

    prompt = st.chat_input("Type your message")

    if prompt:
        if not selected_chat:
            selected_chat = Chat(name=f"Chat {len(user.chats)+1}", user=user)
            db.add(selected_chat)
            db.commit()
            db.refresh(selected_chat)
            st.session_state.selected_chat_id = selected_chat.id  # Remember the new chat id
            st.sidebar.success(f"Started new chat: {selected_chat.name}")

        user_message = Message(chat=selected_chat, sender='user', content=prompt)
        db.add(user_message)
        db.commit()

        with st.chat_message('user'):
            st.markdown(prompt)

        llm = ChatOpenAI(
            model="smollm-360m",
            temperature=0.7,
            openai_api_base='http://localhost:1234/v1',
            openai_api_key='dummy-key',
            streaming=True
        )

        chat_history = [SystemMessage("You are a helpful assistant. Keep responses short and simple.")]
        for message in selected_chat.messages:
            if message.sender == 'user':
                chat_history.append(HumanMessage(content=message.content))
            else:
                chat_history.append(AIMessage(content=message.content))

        with st.chat_message('assistant'):
            response_placeholder = st.empty()
            full_response = ""
            for chunk in llm.stream(chat_history):
                if chunk.content:
                    full_response += chunk.content
                    response_placeholder.markdown(full_response + "▌")
            response_placeholder.markdown(full_response)

        assistant_message = Message(chat=selected_chat, sender='assistant', content=full_response)
        db.add(assistant_message)
        db.commit()

    db.close()

elif auth_status is False:
    st.error('Incorrect username or password')

elif auth_status is None:
    st.warning('Please enter your username and password')
