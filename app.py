import streamlit as st
import pandas as pd
import sqlite3
import cv2
import numpy as np
import fitz
from PIL import Image
import os
import smtplib
from email.message import EmailMessage

st.set_page_config(layout="wide")

# =========================
# 📁 PASTA IMAGENS
# =========================
if not os.path.exists("imagens"):
    os.makedirs("imagens")

# =========================
# 📧 FUNÇÃO EMAIL
# =========================
def enviar_email(destinatario, nome, feedback, caminhos_imagens, assunto, email_remetente, senha_app, assinatura):
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = email_remetente
    msg["To"] = destinatario

    corpo = f"""
Olá, {nome}!

Segue o feedback da sua atividade:

{feedback}

{assinatura}
"""
    msg.set_content(corpo)

    for caminho in caminhos_imagens:
        if os.path.exists(caminho):
            with open(caminho, "rb") as f:
                msg.add_attachment(f.read(), maintype="image", subtype="png", filename=os.path.basename(caminho))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(email_remetente, senha_app)
        smtp.send_message(msg)

# =========================
# 🔙 VOLTAR
# =========================
def voltar(destino):
    if st.button("🔙 Voltar"):
        st.session_state.tela = destino
        st.rerun()

# =========================
# 🧠 QR
# =========================
def detectar_qr(img):
    img_np = np.array(img)
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img_np)
    return data.strip().upper() if data else None

# =========================
# 🗄️ BANCO
# =========================
conn = sqlite3.connect("app.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)""")
c.execute("""CREATE TABLE IF NOT EXISTS cursos (id INTEGER PRIMARY KEY, nome TEXT, user_id INTEGER)""")
c.execute("""CREATE TABLE IF NOT EXISTS alunos (id INTEGER PRIMARY KEY, nome TEXT, email TEXT, turma TEXT, curso_id INTEGER)""")
c.execute("""CREATE TABLE IF NOT EXISTS atividades (id INTEGER PRIMARY KEY, nome TEXT, curso_id INTEGER)""")
c.execute("""CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY,
    atividade_id INTEGER,
    nome TEXT,
    email TEXT,
    turma TEXT,
    feedback TEXT
)""")

try:
    c.execute("ALTER TABLE resultados ADD COLUMN imagens TEXT")
except:
    pass

try:
    c.execute("ALTER TABLE resultados ADD COLUMN enviado INTEGER DEFAULT 0")
except:
    pass

conn.commit()

# =========================
# 🧠 ESTADO
# =========================
if "tela" not in st.session_state:
    st.session_state.tela = "login"

# =========================
# 🔐 LOGIN
# =========================
if st.session_state.tela == "login":
    st.title("🔐 Login")

    user = st.text_input("Usuário")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        u = c.execute("SELECT * FROM users WHERE username=? AND password=?", (user, senha)).fetchone()
        if u:
            st.session_state.user_id = u[0]
            st.session_state.tela = "cursos"
            st.rerun()
        else:
            st.error("Erro no login")

# =========================
# 📂 CURSOS
# =========================
elif st.session_state.tela == "cursos":
    st.title("📂 Cursos")

    cursos = c.execute("SELECT * FROM cursos WHERE user_id=?", (st.session_state.user_id,)).fetchall()

    for curso in cursos:
        col1, col2, col3 = st.columns([4,1,1])

        with col1:
            if st.button(curso[1], key=f"open_{curso[0]}"):
                st.session_state.curso_id = curso[0]
                st.session_state.tela = "atividades"
                st.rerun()

        with col2:
            if st.button("✏️", key=f"edit_{curso[0]}"):
                st.session_state.curso_id = curso[0]
                st.session_state.tela = "editar_alunos"
                st.rerun()

        with col3:
            if st.button("🗑️", key=f"del_{curso[0]}"):
                st.session_state.confirm_del_curso = curso[0]

    if "confirm_del_curso" in st.session_state:
        st.warning("⚠️ Tem certeza que deseja excluir o curso?")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Sim", key="conf_curso"):
                cid = st.session_state.confirm_del_curso
                c.execute("DELETE FROM cursos WHERE id=?", (cid,))
                c.execute("DELETE FROM alunos WHERE curso_id=?", (cid,))
                c.execute("DELETE FROM atividades WHERE curso_id=?", (cid,))
                conn.commit()
                del st.session_state.confirm_del_curso
                st.rerun()

        with col2:
            if st.button("Cancelar", key="cancel_curso"):
                del st.session_state.confirm_del_curso
                st.rerun()

    if st.button("➕ Novo curso"):
        st.session_state.tela = "novo_curso"
        st.rerun()

# =========================
# 📄 ATIVIDADES
# =========================
elif st.session_state.tela == "atividades":
    voltar("cursos")
    st.title("Atividades")

    atividades = c.execute("SELECT * FROM atividades WHERE curso_id=?", (st.session_state.curso_id,)).fetchall()

    for atv in atividades:
        col1, col2 = st.columns([4,1])

        with col1:
            if st.button(atv[1], key=f"open_{atv[0]}"):
                st.session_state.atividade_id = atv[0]
                st.session_state.tela = "resultado"
                st.rerun()

        with col2:
            if st.button("🗑️", key=f"del_{atv[0]}"):
                st.session_state.confirm_del_atividade = atv[0]

    if "confirm_del_atividade" in st.session_state:
        st.warning("⚠️ Tem certeza que deseja excluir a atividade?")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Sim", key="conf_atv"):
                aid = st.session_state.confirm_del_atividade
                c.execute("DELETE FROM atividades WHERE id=?", (aid,))
                c.execute("DELETE FROM resultados WHERE atividade_id=?", (aid,))
                conn.commit()
                del st.session_state.confirm_del_atividade
                st.rerun()

        with col2:
            if st.button("Cancelar", key="cancel_atv"):
                del st.session_state.confirm_del_atividade
                st.rerun()

    if st.button("➕ Nova atividade"):
        st.session_state.tela = "nova_atividade"
        st.rerun()

# =========================
# 📊 RESULTADO
# =========================
elif st.session_state.tela == "resultado":

    voltar("atividades")
    st.title("📊 Planilha da Atividade")

    df = pd.read_sql_query(
        "SELECT nome, turma, email, feedback, imagens, enviado FROM resultados WHERE atividade_id=?",
        conn,
        params=(st.session_state.atividade_id,)
    )

    assunto = st.text_input("Assunto", "Feedback da atividade")
    email_remetente = st.text_input("Seu e-mail")
    senha_app = st.text_input("Senha app", type="password")
    assinatura = st.text_area("Assinatura", "Att,\nProfessor(a)")

    if not df.empty:

        if st.button("📤 Enviar todos", key="env_all"):
            for _, row in df.iterrows():
                if int(row["enviado"]) == 0:
                    caminhos = row["imagens"].split(";") if row["imagens"] else []
                    enviar_email(row["email"], row["nome"], row["feedback"], caminhos,
                                 assunto, email_remetente, senha_app, assinatura)

        for idx, row in df.iterrows():
            st.write(row["nome"], "-", row["turma"])

            if int(row["enviado"]) == 0:
                if st.button("Enviar", key=f"send_{idx}"):
                    caminhos = row["imagens"].split(";") if row["imagens"] else []
                    enviar_email(row["email"], row["nome"], row["feedback"], caminhos,
                                 assunto, email_remetente, senha_app, assinatura)
                    st.rerun()
