import streamlit as st
import pandas as pd
import sqlite3
import cv2
import numpy as np
import fitz  # PyMuPDF
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
                msg.add_attachment(
                    f.read(),
                    maintype="image",
                    subtype="png",
                    filename=os.path.basename(caminho)
                )

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
# 🧠 QR CODE
# =========================
def detectar_qr(img):
    img_np = np.array(img)
    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(img_np)

    if data:
        return data.strip().upper()
    return None

# =========================
# 🗄️ BANCO
# =========================
conn = sqlite3.connect("app.db", check_same_thread=False)
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS cursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    user_id INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS alunos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    email TEXT,
    turma TEXT,
    curso_id INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS atividades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    curso_id INTEGER
)""")

c.execute("""CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atividade_id INTEGER,
    nome TEXT,
    email TEXT,
    turma TEXT,
    feedback TEXT
)""")

try:
    c.execute("ALTER TABLE resultados ADD COLUMN imagens TEXT")
    conn.commit()
except:
    pass

try:
    c.execute("ALTER TABLE resultados ADD COLUMN enviado INTEGER DEFAULT 0")
    conn.commit()
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
        u = c.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (user, senha)
        ).fetchone()

        if u:
            st.session_state.user_id = u[0]
            st.session_state.tela = "cursos"
            st.rerun()
        else:
            st.error("Erro no login")

    st.subheader("Criar conta")

    new_user = st.text_input("Novo usuário")
    new_pass = st.text_input("Nova senha", type="password")

    if st.button("Cadastrar"):
        try:
            c.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (new_user, new_pass)
            )
            conn.commit()
            st.success("Conta criada")
        except:
            st.error("Usuário já existe")

# =========================
# 📊 RESULTADO (TRECHO CORRIGIDO)
# =========================
elif st.session_state.tela == "resultado":

    voltar("atividades")

    st.title("📊 Planilha da Atividade")

    conn3 = sqlite3.connect("app.db")
    df = pd.read_sql_query("""
        SELECT nome, turma, email, feedback, imagens, enviado
        FROM resultados
        WHERE atividade_id=?
    """, conn3, params=(st.session_state.atividade_id,))
    conn3.close()

    assunto_email = st.text_input("Assunto do e-mail", value="Feedback da atividade")

    st.subheader("Configuração de envio")
    email_remetente = st.text_input("Seu e-mail (remetente)")
    senha_app = st.text_input("Senha de app", type="password")
    assinatura = st.text_area("Assinatura do e-mail", value="Att,\nProfessor(a)")

    if df.empty:
        st.warning("Nenhum dado encontrado")
    else:
        st.dataframe(df[["nome", "turma", "email", "feedback"]])

        if st.button("📤 Enviar para todos", key="enviar_todos"):
            for _, row in df.iterrows():
                if int(row["enviado"]) == 0:
                    caminhos = row["imagens"].split(";") if row["imagens"] else []
                    try:
                        enviar_email(
                            row["email"],
                            row["nome"],
                            row["feedback"],
                            caminhos,
                            assunto_email,
                            email_remetente,
                            senha_app,
                            assinatura
                        )

                        conn4 = sqlite3.connect("app.db")
                        c4 = conn4.cursor()
                        c4.execute("""
                            UPDATE resultados
                            SET enviado=1
                            WHERE atividade_id=? AND email=?
                        """, (st.session_state.atividade_id, row["email"]))
                        conn4.commit()
                        conn4.close()

                    except Exception as e:
                        st.error(f"Erro com {row['nome']}: {e}")

            st.success("Envio finalizado!")
            st.rerun()

        for idx, row in df.iterrows():

            st.markdown(f"### {row['nome']} - {row['turma']}")

            if row["imagens"]:
                caminhos = row["imagens"].split(";")

                for i in range(0, len(caminhos), 2):
                    col1, col2 = st.columns(2)

                    if i < len(caminhos) and os.path.exists(caminhos[i]):
                        col1.image(caminhos[i], use_column_width=True)

                    if i + 1 < len(caminhos) and os.path.exists(caminhos[i + 1]):
                        col2.image(caminhos[i + 1], use_column_width=True)

            st.markdown(f"**Feedback:** {row['feedback']}")

            status = "✅ Enviado" if int(row["enviado"]) == 1 else "⏳ Não enviado"
            st.write(f"Status: {status}")

            if int(row["enviado"]) == 0:
                if st.button(
                    f"📧 Enviar para {row['nome']}",
                    key=f"send_{row['email']}_{idx}"
                ):
                    caminhos = row["imagens"].split(";") if row["imagens"] else []

                    try:
                        enviar_email(
                            row["email"],
                            row["nome"],
                            row["feedback"],
                            caminhos,
                            assunto_email,
                            email_remetente,
                            senha_app,
                            assinatura
                        )

                        conn4 = sqlite3.connect("app.db")
                        c4 = conn4.cursor()
                        c4.execute("""
                            UPDATE resultados
                            SET enviado=1
                            WHERE atividade_id=? AND email=?
                        """, (st.session_state.atividade_id, row["email"]))
                        conn4.commit()
                        conn4.close()

                        st.success("Email enviado!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Erro ao enviar: {e}")

            st.divider()
