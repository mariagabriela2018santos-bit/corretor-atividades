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
# 📧 FUNÇÃO EMAIL (ATUALIZADA)
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

Em anexo está a atividade realizada e um texto de apoio caso queira se aprofundar mais no assunto.
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

# adicionar colunas novas
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
# 📂 CURSOS
# =========================
elif st.session_state.tela == "cursos":

    st.title("📂 Cursos")

    cursos = c.execute(
        "SELECT * FROM cursos WHERE user_id=?",
        (st.session_state.user_id,)
    ).fetchall()

    for curso in cursos:

        col1, col2, col3 = st.columns([4, 1, 1])

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

        # confirmação
        if "confirm_del_curso" in st.session_state:
            st.warning("⚠️ Tem certeza que deseja excluir este curso e todos os dados vinculados?")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("✅ Sim, excluir", key="confirm_curso"):
                    cid = st.session_state.confirm_del_curso
                    c.execute("DELETE FROM cursos WHERE id=?", (cid,))
                    c.execute("DELETE FROM alunos WHERE curso_id=?", (cid,))
                    c.execute("DELETE FROM atividades WHERE curso_id=?", (cid,))
                    conn.commit()
                    del st.session_state.confirm_del_curso
                    st.rerun()

            with col2:
                if st.button("❌ Cancelar", key="cancel_curso"):
                    del st.session_state.confirm_del_curso
                    st.rerun()

        if st.button("➕ Novo curso"):
            st.session_state.tela = "novo_curso"
            st.rerun()

# =========================
# 👥 NOVO CURSO
# =========================
elif st.session_state.tela == "novo_curso":

    voltar("cursos")

    st.title("Novo curso")

    nome_curso = st.text_input("Nome do curso")

    if "lista_alunos" not in st.session_state:
        st.session_state.lista_alunos = []

    nome = st.text_input("Nome do aluno")
    email = st.text_input("Email")
    turma = st.text_input("Turma")

    if st.button("Adicionar aluno"):
        if nome and email and turma:
            st.session_state.lista_alunos.append((nome, email, turma))
            st.rerun()

    if st.session_state.lista_alunos:
        st.dataframe(pd.DataFrame(
            st.session_state.lista_alunos,
            columns=["Nome", "Email", "Turma"]
        ))

    if st.button("Salvar curso"):
        if nome_curso:
            c.execute(
                "INSERT INTO cursos (nome,user_id) VALUES (?,?)",
                (nome_curso, st.session_state.user_id)
            )
            curso_id = c.lastrowid

            for aluno in st.session_state.lista_alunos:
                c.execute(
                    "INSERT INTO alunos (nome,email,turma,curso_id) VALUES (?,?,?,?)",
                    aluno + (curso_id,)
                )

            conn.commit()
            st.session_state.lista_alunos = []
            st.session_state.tela = "cursos"
            st.rerun()

# =========================
# ✏️ EDITAR ALUNOS
# =========================
elif st.session_state.tela == "editar_alunos":

    voltar("cursos")

    st.title("Editar alunos")

    alunos_df = pd.read_sql_query(
        "SELECT * FROM alunos WHERE curso_id=?",
        conn,
        params=(st.session_state.curso_id,)
    )

    st.dataframe(alunos_df)

    nome = st.text_input("Nome")
    email = st.text_input("Email")
    turma = st.text_input("Turma")

    if st.button("Adicionar"):
        if nome and email and turma:
            c.execute(
                "INSERT INTO alunos (nome,email,turma,curso_id) VALUES (?,?,?,?)",
                (nome, email, turma, st.session_state.curso_id)
            )
            conn.commit()
            st.rerun()

    if not alunos_df.empty:
        aluno_del = st.selectbox("Remover aluno", alunos_df["nome"])

        if st.button("Remover"):
            c.execute(
                "DELETE FROM alunos WHERE nome=? AND curso_id=?",
                (aluno_del, st.session_state.curso_id)
            )
            conn.commit()
            st.rerun()

# =========================
# 📄 ATIVIDADES
# =========================
elif st.session_state.tela == "atividades":

    voltar("cursos")

    st.title("Atividades")

    atividades = c.execute(
        "SELECT * FROM atividades WHERE curso_id=?",
        (st.session_state.curso_id,)
    ).fetchall()

    for atv in atividades:

        col1, col2 = st.columns([4, 1])

        with col1:
            if st.button(atv[1], key=f"open_{atv[0]}"):
                st.session_state.atividade_id = atv[0]
                st.session_state.tela = "resultado"
                st.rerun()

        with col2:
            if st.button("🗑️", key=f"del_{atv[0]}"):
                st.session_state.confirm_del_atividade = atv[0]

    # 🔥 CONFIRMAÇÃO (fora do loop!)
    if "confirm_del_atividade" in st.session_state:
        st.warning("⚠️ Tem certeza que deseja excluir esta atividade?")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("✅ Sim, excluir"):
                aid = st.session_state.confirm_del_atividade
                c.execute("DELETE FROM atividades WHERE id=?", (aid,))
                c.execute("DELETE FROM resultados WHERE atividade_id=?", (aid,))
                conn.commit()
                del st.session_state.confirm_del_atividade
                st.rerun()

        with col2:
            if st.button("❌ Cancelar"):
                del st.session_state.confirm_del_atividade
                st.rerun()

    # 🔥 BOTÃO NOVO (AGORA NO LUGAR CERTO)
    if st.button("➕ Nova atividade"):
        st.session_state.tela = "nova_atividade"
        st.rerun()
# =========================
# ✏️ NOVA ATIVIDADE (FLUXO CONTÍNUO)
# =========================
elif st.session_state.tela == "nova_atividade":

    voltar("atividades")

    st.title("Nova atividade")

    nome_atv = st.text_input("Nome")
    uploaded = st.file_uploader("PDF", type=["pdf"])

    if uploaded and nome_atv:

        # =========================
        # 📄 CARREGAR PDF
        # =========================
        if "imagens" not in st.session_state:

            pdf_bytes = uploaded.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            imagens = []
            for page in doc:
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                imagens.append(img)

            st.session_state.imagens = imagens
            st.session_state.pagina_atual = 0
            st.session_state.inicio_grupo = 0
            st.session_state.grupos = []

        imagens = st.session_state.imagens

        # =========================
        # 📄 VISUALIZAÇÃO (2 páginas)
        # =========================
        col1, col2 = st.columns(2)

        if st.session_state.pagina_atual < len(imagens):
            col1.image(imagens[st.session_state.pagina_atual], use_column_width=True)

        if st.session_state.pagina_atual + 1 < len(imagens):
            col2.image(imagens[st.session_state.pagina_atual + 1], use_column_width=True)

        # =========================
        # 🔁 NAVEGAÇÃO
        # =========================
        col_prev, col_next = st.columns(2)

        if col_prev.button("⬅️ Página anterior", disabled=(st.session_state.pagina_atual == 0)):
            st.session_state.pagina_atual = max(0, st.session_state.pagina_atual - 2)
            st.rerun()

        if col_next.button("➡️ Próxima página"):
            if st.session_state.pagina_atual + 2 < len(imagens):
                st.session_state.pagina_atual += 2
                st.rerun()

        st.divider()

        # =========================
        # 👤 SELEÇÃO DE ALUNO (MANTIDA)
        # =========================
        alunos_df = pd.read_sql_query(
            "SELECT * FROM alunos WHERE curso_id=?",
            conn,
            params=(st.session_state.curso_id,)
        )

        alunos_lista = alunos_df["nome"].tolist()

        aluno_escolhido = st.selectbox(
            "🔍 Buscar e selecionar aluno",
            [""] + alunos_lista,
            key="aluno_atual"
        )

        feedback = st.text_area("Feedback", key="feedback_atual")

        # =========================
        # ➡️ SALVAR ALUNO E IR PRO PRÓXIMO
        # =========================
        if st.button("➡️ Próximo aluno (salvar este)"):

            if aluno_escolhido:

                aluno_data = alunos_df[
                    alunos_df["nome"] == aluno_escolhido
                ].iloc[0]

                inicio = st.session_state.inicio_grupo
                fim = st.session_state.pagina_atual + 2

                grupo_paginas = imagens[inicio:fim]

                st.session_state.grupos.append({
                    "paginas": grupo_paginas,
                    "aluno": aluno_data["nome"],
                    "email": aluno_data["email"],
                    "feedback": feedback,
                    "turma": aluno_data["turma"]
                })

                st.session_state.inicio_grupo = fim

                # limpa campos
                st.session_state.aluno_atual = ""
                st.session_state.feedback_atual = ""

                st.success("Aluno salvo!")

                st.rerun()

            else:
                st.warning("Selecione um aluno")

        # =========================
        # 💾 SALVAR ATIVIDADE FINAL
        # =========================
        if st.button("💾 Finalizar atividade"):

            conn2 = sqlite3.connect("app.db", timeout=10)
            c2 = conn2.cursor()

            c2.execute(
                "INSERT INTO atividades (nome, curso_id) VALUES (?,?)",
                (nome_atv, st.session_state.curso_id)
            )
            atv_id = c2.lastrowid

            for i, grupo in enumerate(st.session_state.grupos):

                caminhos = []

                for j, img in enumerate(grupo["paginas"]):
                    caminho = f"imagens/atv_{atv_id}_{i}_{j}.png"
                    img.save(caminho)
                    caminhos.append(caminho)

                c2.execute("""
                INSERT INTO resultados
                (atividade_id,nome,email,turma,feedback,imagens)
                VALUES (?,?,?,?,?,?)
                """, (
                    atv_id,
                    grupo["aluno"],
                    grupo["email"],
                    grupo["turma"],
                    grupo["feedback"],
                    ";".join(caminhos)
                ))

            conn2.commit()
            conn2.close()

            # limpar estado
            for k in ["imagens", "pagina_atual", "inicio_grupo", "grupos"]:
                if k in st.session_state:
                    del st.session_state[k]

            st.session_state.tela = "atividades"
            st.rerun()
# =========================
# 📊 RESULTADO (COM EMAIL)
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

        # ✅ KEY adicionada
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

            # ✅ FIX PRINCIPAL: key única por botão
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
