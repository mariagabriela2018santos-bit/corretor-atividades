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

        # confirmação
        if "confirm_del_atividade" in st.session_state:
            st.warning("⚠️ Tem certeza que deseja excluir esta atividade?")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("✅ Sim, excluir", key="confirm_atv"):
                    aid = st.session_state.confirm_del_atividade
                    c.execute("DELETE FROM atividades WHERE id=?", (aid,))
                    c.execute("DELETE FROM resultados WHERE atividade_id=?", (aid,))
                    conn.commit()
                    del st.session_state.confirm_del_atividade
                    st.rerun()

            with col2:
                if st.button("❌ Cancelar", key="cancel_atv"):
                    del st.session_state.confirm_del_atividade
                    st.rerun()

# =========================
# ✏️ NOVA ATIVIDADE
# =========================
elif st.session_state.tela == "nova_atividade":

    voltar("atividades")

    st.title("Nova atividade")

    nome_atv = st.text_input("Nome")
    uploaded = st.file_uploader("PDF", type=["pdf"])

    if uploaded and nome_atv:

        if "grupos" not in st.session_state:

            pdf_bytes = uploaded.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            imagens = []
            for page in doc:
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                imagens.append(img)

            grupos = []
            paginas = []
            turma_atual = None

            for img in imagens:
                qr = detectar_qr(img)

                if qr:
                    if paginas:
                        grupos.append({"turma": turma_atual, "paginas": paginas})
                    turma_atual = qr
                    paginas = [img]
                else:
                    paginas.append(img)

            if paginas:
                grupos.append({"turma": turma_atual, "paginas": paginas})

            st.session_state.grupos = grupos
            st.session_state.indice = 0
            st.session_state.respostas = {}

        grupos = st.session_state.grupos
        i = st.session_state.indice
        grupo = grupos[i]

        alunos_df = pd.read_sql_query(
            "SELECT * FROM alunos WHERE curso_id=?",
            conn,
            params=(st.session_state.curso_id,)
        )

        col1, col2 = st.columns([3, 1])

        with col1:
            paginas = grupo["paginas"]
            for j in range(0, len(paginas), 2):
                c1, c2 = st.columns(2)
                if j < len(paginas):
                    c1.image(paginas[j], use_column_width=True)
                if j + 1 < len(paginas):
                    c2.image(paginas[j + 1], use_column_width=True)

        with col2:

            turma_qr = grupo["turma"]

            alunos_filtrados = alunos_df[
                alunos_df["turma"].str.upper() == turma_qr
            ]

            st.subheader(f"Turma: {turma_qr}")

            resposta_atual = st.session_state.respostas.get(i, {})

            if resposta_atual.get("aluno"):

                st.success(f"Aluno: {resposta_atual['aluno']}")

                if st.button("Trocar aluno", key=f"trocar_{i}"):
                    st.session_state.respostas[i]["aluno"] = ""
                    st.rerun()

            else:
                # 🔥 NOVO CAMPO COM AUTOCOMPLETE
                alunos_lista = alunos_filtrados["nome"].tolist()

                aluno_escolhido = st.selectbox(
                    "🔍 Buscar e selecionar aluno",
                    [""] + alunos_lista,
                    key=f"select_{i}"
                )

                if aluno_escolhido:
                    aluno_data = alunos_filtrados[
                        alunos_filtrados["nome"] == aluno_escolhido
                    ].iloc[0]

                    st.session_state.respostas[i] = {
                        "aluno": aluno_data["nome"],
                        "email": aluno_data["email"],
                        "feedback": ""
                    }
                    st.rerun()

            feedback = st.text_area(
                "Feedback",
                value=resposta_atual.get("feedback", ""),
                key=f"fb_{i}"
            )

            if i not in st.session_state.respostas:
                st.session_state.respostas[i] = {}

            st.session_state.respostas[i]["feedback"] = feedback

            col_prev, col_next = st.columns(2)

            if col_prev.button("⬅️", disabled=(i == 0)):
                st.session_state.indice -= 1
                st.rerun()

            if col_next.button("➡️", disabled=(i >= len(grupos) - 1)):
                st.session_state.indice += 1
                st.rerun()

        if st.button("💾 Salvar"):

            conn2 = sqlite3.connect("app.db", timeout=10)
            c2 = conn2.cursor()

            c2.execute(
                "INSERT INTO atividades (nome, curso_id) VALUES (?,?)",
                (nome_atv, st.session_state.curso_id)
            )
            atv_id = c2.lastrowid

            for i, grupo in enumerate(grupos):
                r = st.session_state.respostas.get(i, {})
                if r.get("aluno"):

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
                        r["aluno"],
                        r["email"],
                        grupo["turma"],
                        r["feedback"],
                        ";".join(caminhos)
                    ))

            conn2.commit()
            conn2.close()

            for k in ["grupos", "indice", "respostas"]:
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
