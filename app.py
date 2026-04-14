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
def enviar_email(destinatario, nome, feedback, caminhos_imagens, assunto, email_remetente, senha_app, assinatura, pdf_bytes=None, pdf_nome="material_apoio.pdf"):

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = email_remetente
    msg["To"] = destinatario

    corpo = f"""
Olá, {nome}!

Segue o feedback da sua atividade:

{feedback}

Em anexo, você encontrará a atividade realizada e um material de apoio que pode te ajudar a revisar e aprofundar o conteúdo trabalhado.
{assinatura}
"""
    msg.set_content(corpo)

    # imagens
    for caminho in caminhos_imagens:
        if os.path.exists(caminho):
            with open(caminho, "rb") as f:
                msg.add_attachment(
                    f.read(),
                    maintype="image",
                    subtype="png",
                    filename=os.path.basename(caminho)
                )

    # 🔥 PDF ANEXO (NOVO)
    if pdf_bytes:
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=pdf_nome
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

try:
    c.execute("ALTER TABLE cursos ADD COLUMN turma TEXT")
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

    # 🔥 BOTÃO SEMPRE VISÍVEL (ANTES DO LOOP)
    if st.button("➕ Novo curso"):
        st.session_state.tela = "novo_curso"
        st.rerun()

    if not cursos:
        st.info("Nenhum curso cadastrado ainda.")
    else:
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

        # confirmação fora do loop
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
# =========================
# 👥 NOVO CURSO
# =========================
elif st.session_state.tela == "novo_curso":

    voltar("cursos")

    st.title("Novo curso")

    nome_curso = st.text_input("Nome do curso")
    turma_curso = st.text_input("Turma (ex: A)")

    if "lista_alunos" not in st.session_state:
        st.session_state.lista_alunos = []

    nome = st.text_input("Nome do aluno")
    email = st.text_input("Email")

    if st.button("Adicionar aluno"):
        if nome and email:
            st.session_state.lista_alunos.append((nome, email))
            st.rerun()

    if st.session_state.lista_alunos:
        st.dataframe(pd.DataFrame(
            st.session_state.lista_alunos,
            columns=["Nome", "Email"]
        ))

    if st.button("Salvar curso"):
        if nome_curso:
            c.execute(
                "INSERT INTO cursos (nome,user_id,turma) VALUES (?,?,?)",
                (nome_curso, st.session_state.user_id, turma_curso)
            )
            
            curso_id = c.lastrowid

            for aluno in st.session_state.lista_alunos:
                c.execute(
                    "INSERT INTO alunos (nome,email,curso_id) VALUES (?,?,?)",
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

    if st.button("Adicionar"):
        if nome and email:
            c.execute(
                "INSERT INTO alunos (nome,email,curso_id) VALUES (?,?,?)",
                (nome, email, st.session_state.curso_id)
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
# ✏️ NOVA ATIVIDADE (VERSÃO AUTOMÁTICA)
# =========================
elif st.session_state.tela == "nova_atividade":

    voltar("atividades")

    st.title("Nova atividade")

    nome_atv = st.text_input("Nome")
    paginas_por_aluno = st.number_input("📄 Páginas por aluno", min_value=1, value=2)
    uploaded = st.file_uploader("PDF", type=["pdf"])

    if uploaded and nome_atv:

        # =========================
        # 📄 PROCESSAR PDF UMA VEZ
        # =========================
        if "imagens" not in st.session_state:

            pdf_bytes = uploaded.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            imagens = []
            for page in doc:
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                imagens.append(img)

            # dividir automaticamente
            grupos = []
            for i in range(0, len(imagens), paginas_por_aluno):
                grupos.append({
                    "paginas": imagens[i:i + paginas_por_aluno]
                })

            st.session_state.grupos = grupos
            st.session_state.indice = 0
            st.session_state.respostas = {}
            st.session_state.imagens = imagens

        # =========================
        # 🧠 CORREÇÃO DIRETA
        # =========================
        grupos = st.session_state.grupos
        i = st.session_state.indice
        grupo = grupos[i]

        alunos_df = pd.read_sql_query(
            "SELECT * FROM alunos WHERE curso_id=?",
            conn,
            params=(st.session_state.curso_id,)
        )

        col1, col2 = st.columns([3, 1])

        # 📄 IMAGENS
        with col1:
            paginas = grupo["paginas"]
            for j in range(0, len(paginas), 2):
                c1, c2 = st.columns(2)
                if j < len(paginas):
                    c1.image(paginas[j], use_column_width=True)
                if j + 1 < len(paginas):
                    c2.image(paginas[j + 1], use_column_width=True)

        # 🧠 LATERAL
        with col2:

            st.subheader(f"Aluno {i+1} de {len(grupos)}")

            resposta_atual = st.session_state.respostas.get(i, {})

            # seleção de aluno
            alunos_lista = alunos_df["nome"].tolist()

            aluno_escolhido = st.selectbox(
                "Selecionar aluno",
                [""] + alunos_lista,
                index=0 if not resposta_atual.get("aluno") else alunos_lista.index(resposta_atual["aluno"]) + 1,
                key=f"select_{i}"
            )

            if aluno_escolhido:
                aluno_data = alunos_df[
                    alunos_df["nome"] == aluno_escolhido
                ].iloc[0]

                st.session_state.respostas[i] = {
                    "aluno": aluno_data["nome"],
                    "email": aluno_data["email"],
                    "feedback": resposta_atual.get("feedback", "")
                }

            # feedback
            feedback = st.text_area(
                "Feedback",
                value=resposta_atual.get("feedback", ""),
                key=f"fb_{i}"
            )

            if i not in st.session_state.respostas:
                st.session_state.respostas[i] = {}

            st.session_state.respostas[i]["feedback"] = feedback

            # navegação
            col_prev, col_next = st.columns(2)

            if col_prev.button("⬅️ Anterior", disabled=(i == 0)):
                st.session_state.indice -= 1
                st.rerun()

            if col_next.button("➡️ Próximo", disabled=(i >= len(grupos) - 1)):
                st.session_state.indice += 1
                st.rerun()
        
        # 💾 SALVAR
        if st.button("💾 Salvar atividade"):

            # 🔥 pegar turma do curso (AQUI é o lugar certo)
            curso = c.execute(
                "SELECT turma FROM cursos WHERE id=?",
                (st.session_state.curso_id,)
            ).fetchone()

            turma_curso = curso[0] if curso and curso[0] else "SEM TURMA"

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
                        turma_curso,
                        r["feedback"],
                        ";".join(caminhos)
                    ))

            conn2.commit()
            conn2.close()

            # limpar estado
            for k in ["grupos", "indice", "respostas", "imagens"]:
                if k in st.session_state:
                    del st.session_state[k]

            st.success("Atividade salva!")
            st.session_state.tela = "atividades"
            st.rerun()


# =========================
# 📊 RESULTADO (COM EDIÇÃO DE FEEDBACK)
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

    pdf_file = st.file_uploader("📎 Anexar material de apoio (PDF)", type=["pdf"])

    if pdf_file:
        st.session_state.pdf_bytes = pdf_file.read()
        st.session_state.pdf_nome = pdf_file.name

    pdf_bytes = st.session_state.get("pdf_bytes", None)
    pdf_nome = st.session_state.get("pdf_nome", "material_apoio.pdf")

    if df.empty:
        st.warning("Nenhum dado encontrado")
    else:
        st.dataframe(df[["nome", "turma", "email", "feedback"]])

        # =========================
        # 📤 ENVIAR TODOS
        # =========================
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
                            assinatura,
                            pdf_bytes,
                            pdf_nome
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

        # =========================
        # 👤 LOOP DOS ALUNOS
        # =========================
        for idx, row in df.iterrows():

            st.markdown(f"### {row['nome']} - {row['turma']}")

            # =========================
            # 🖼️ IMAGENS
            # =========================
            if row["imagens"]:
                caminhos = row["imagens"].split(";")

                for i in range(0, len(caminhos), 2):
                    col1, col2 = st.columns(2)

                    if i < len(caminhos) and os.path.exists(caminhos[i]):
                        col1.image(caminhos[i], use_column_width=True)

                    if i + 1 < len(caminhos) and os.path.exists(caminhos[i + 1]):
                        col2.image(caminhos[i + 1], use_column_width=True)

            # =========================
            # ✏️ FEEDBACK EDITÁVEL
            # =========================
            edit_key = f"editando_{idx}"

            if edit_key not in st.session_state:
                st.session_state[edit_key] = False

            col_fb, col_btn = st.columns([8, 1])

            with col_fb:
                if not st.session_state[edit_key]:
                    st.markdown(f"**Feedback:** {row['feedback']}")
                else:
                    novo_feedback = st.text_area(
                        "Editar feedback",
                        value=row["feedback"],
                        key=f"edit_text_{idx}"
                    )

            with col_btn:
                if not st.session_state[edit_key]:
                    if st.button("✏️", key=f"editar_{idx}"):
                        st.session_state[edit_key] = True
                        st.rerun()
                else:
                    if st.button("💾", key=f"salvar_{idx}"):

                        conn_edit = sqlite3.connect("app.db")
                        c_edit = conn_edit.cursor()

                        c_edit.execute("""
                            UPDATE resultados
                            SET feedback=?
                            WHERE atividade_id=? AND email=?
                        """, (
                            st.session_state[f"edit_text_{idx}"],
                            st.session_state.atividade_id,
                            row["email"]
                        ))

                        conn_edit.commit()
                        conn_edit.close()

                        st.session_state[edit_key] = False
                        st.success("Feedback atualizado!")
                        st.rerun()

            # =========================
            # 📌 STATUS
            # =========================
            status = "✅ Enviado" if int(row["enviado"]) == 1 else "⏳ Não enviado"
            st.write(f"Status: {status}")

            # =========================
            # 📧 REENVIO INDIVIDUAL (CORRIGIDO)
            # =========================
            if st.button(
                f"🔁 Reenviar para {row['nome']}",
                key=f"send_{row['email']}_{idx}"
            ):

                caminhos = row["imagens"].split(";") if row["imagens"] else []

                try:
                    # 🔥 BUSCAR FEEDBACK ATUALIZADO DO BANCO
                    conn_temp = sqlite3.connect("app.db")
                    c_temp = conn_temp.cursor()

                    resultado = c_temp.execute("""
                        SELECT feedback FROM resultados
                        WHERE atividade_id=? AND email=?
                    """, (st.session_state.atividade_id, row["email"])).fetchone()

                    feedback_atual = resultado[0] if resultado else ""

                    conn_temp.close()

                    # 🔥 ENVIO COM FEEDBACK CORRETO
                    enviar_email(
                        row["email"],
                        row["nome"],
                        feedback_atual,
                        caminhos,
                        assunto_email,
                        email_remetente,
                        senha_app,
                        assinatura,
                        pdf_bytes,
                        pdf_nome
                    )

                    # 🔥 MARCAR COMO ENVIADO
                    conn4 = sqlite3.connect("app.db")
                    c4 = conn4.cursor()
                    c4.execute("""
                        UPDATE resultados
                        SET enviado=1
                        WHERE atividade_id=? AND email=?
                    """, (st.session_state.atividade_id, row["email"]))
                    conn4.commit()
                    conn4.close()

                    st.success("Email reenviado!")
                    st.rerun()
  
                except Exception as e:
                    st.error(f"Erro ao enviar: {e}")
                
             st.divider()      


