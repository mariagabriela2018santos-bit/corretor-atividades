import streamlit as st
import pandas as pd
import sqlite3
import fitz  # PyMuPDF
from PIL import Image
import os
import smtplib
import hashlib
import secrets
import io
import zipfile
import shutil
import tempfile
from email.message import EmailMessage
from datetime import datetime


# =========================================================
# CONFIGURAÇÃO
# =========================================================

st.set_page_config(
    page_title="Corretor de Atividades",
    layout="wide"
)

DB_PATH = "app.db"
IMAGENS_DIR = "imagens"


# =========================================================
# 📁 PASTA DE IMAGENS
# =========================================================

os.makedirs(IMAGENS_DIR, exist_ok=True)


# =========================================================
# 🔐 SEGURANÇA DE SENHAS
# =========================================================

def gerar_hash_senha(senha):
    """
    Gera hash seguro usando PBKDF2 + SHA-256.
    """
    salt = secrets.token_bytes(16)

    hash_senha = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt,
        200_000
    )

    return (
        salt.hex()
        + "$"
        + hash_senha.hex()
    )


def verificar_senha(senha, senha_salva):
    """
    Verifica senha nova (hash) ou senha antiga
    armazenada em texto simples.
    """

    if not senha_salva:
        return False

    # Senha nova
    if "$" in senha_salva:

        try:
            salt_hex, hash_hex = senha_salva.split("$", 1)

            salt = bytes.fromhex(salt_hex)

            hash_calculado = hashlib.pbkdf2_hmac(
                "sha256",
                senha.encode("utf-8"),
                salt,
                200_000
            )

            return secrets.compare_digest(
                hash_calculado.hex(),
                hash_hex
            )

        except Exception:
            return False

    # Compatibilidade com usuários antigos
    return secrets.compare_digest(
        senha,
        senha_salva
    )


def obter_codigo_recuperacao():
    """
    Código de recuperação configurado no Streamlit Secrets.
    """

    try:
        return st.secrets["RECOVERY_CODE"]
    except Exception:
        return ""


# =========================================================
# 📧 EMAIL
# =========================================================

def enviar_email(
    destinatario,
    nome,
    feedback,
    caminhos_imagens,
    assunto,
    email_remetente,
    senha_app,
    assinatura,
    pdf_bytes=None,
    pdf_nome="material_apoio.pdf"
):

    msg = EmailMessage()

    msg["Subject"] = assunto
    msg["From"] = email_remetente
    msg["To"] = destinatario

    corpo = f"""
Olá, {nome}!

{feedback}

{assinatura}
"""

    msg.set_content(corpo)

    # -----------------------------------------------------
    # Imagens
    # -----------------------------------------------------

    for caminho in caminhos_imagens:

        if os.path.exists(caminho):

            with open(caminho, "rb") as f:

                msg.add_attachment(
                    f.read(),
                    maintype="image",
                    subtype="png",
                    filename=os.path.basename(caminho)
                )

    # -----------------------------------------------------
    # PDF
    # -----------------------------------------------------

    if pdf_bytes:

        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=pdf_nome
        )

    # -----------------------------------------------------
    # Gmail
    # -----------------------------------------------------

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465
    ) as smtp:

        smtp.login(
            email_remetente,
            senha_app
        )

        smtp.send_message(msg)


# =========================================================
# 🔙 VOLTAR
# =========================================================

def voltar(destino):

    if st.button("🔙 Voltar"):

        st.session_state.tela = destino

        st.rerun()


# =========================================================
# 🗄️ BANCO
# =========================================================

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False
)

c = conn.cursor()


# =========================================================
# CRIAÇÃO DAS TABELAS
# =========================================================

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT
)
""")


c.execute("""
CREATE TABLE IF NOT EXISTS cursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    user_id INTEGER,
    turma TEXT
)
""")


c.execute("""
CREATE TABLE IF NOT EXISTS alunos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    email TEXT,
    turma TEXT,
    curso_id INTEGER
)
""")


c.execute("""
CREATE TABLE IF NOT EXISTS atividades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    curso_id INTEGER
)
""")


c.execute("""
CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atividade_id INTEGER,
    nome TEXT,
    email TEXT,
    turma TEXT,
    feedback TEXT,
    imagens TEXT,
    enviado INTEGER DEFAULT 0
)
""")


c.execute("""
CREATE TABLE IF NOT EXISTS rascunho_correcao (
    curso_id INTEGER,
    nome_atividade TEXT,
    indice INTEGER,
    aluno TEXT,
    email TEXT,
    feedback TEXT,
    PRIMARY KEY (
        curso_id,
        nome_atividade,
        indice
    )
)
""")


conn.commit()


# =========================================================
# 🔄 COMPATIBILIDADE COM BANCO ANTIGO
# =========================================================

def adicionar_coluna_se_nao_existir(
    tabela,
    coluna,
    definicao
):

    try:

        colunas = c.execute(
            f"PRAGMA table_info({tabela})"
        ).fetchall()

        nomes = [
            coluna_info[1]
            for coluna_info in colunas
        ]

        if coluna not in nomes:

            c.execute(
                f"""
                ALTER TABLE {tabela}
                ADD COLUMN {coluna}
                {definicao}
                """
            )

            conn.commit()

    except Exception:
        pass


adicionar_coluna_se_nao_existir(
    "resultados",
    "imagens",
    "TEXT"
)

adicionar_coluna_se_nao_existir(
    "resultados",
    "enviado",
    "INTEGER DEFAULT 0"
)

adicionar_coluna_se_nao_existir(
    "cursos",
    "turma",
    "TEXT"
)


# =========================================================
# 🔐 MIGRAÇÃO AUTOMÁTICA DE SENHAS ANTIGAS
# =========================================================

def migrar_senhas_antigas():

    usuarios = c.execute(
        "SELECT id, password FROM users"
    ).fetchall()

    alterados = False

    for user_id, senha in usuarios:

        if senha and "$" not in senha:

            novo_hash = gerar_hash_senha(
                senha
            )

            c.execute(
                """
                UPDATE users
                SET password=?
                WHERE id=?
                """,
                (
                    novo_hash,
                    user_id
                )
            )

            alterados = True

    if alterados:
        conn.commit()


migrar_senhas_antigas()


# =========================================================
# 📝 RASCUNHOS
# =========================================================

def carregar_rascunhos(
    curso_id,
    nome_atividade
):

    conn_local = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    cur = conn_local.cursor()

    rows = cur.execute(
        """
        SELECT
            indice,
            aluno,
            email,
            feedback

        FROM rascunho_correcao

        WHERE curso_id=?
        AND nome_atividade=?

        ORDER BY indice
        """,
        (
            curso_id,
            nome_atividade
        )
    ).fetchall()

    conn_local.close()

    respostas = {}
    ultimo = 0

    for indice, aluno, email, feedback in rows:

        respostas[indice] = {
            "aluno": aluno,
            "email": email,
            "feedback": feedback or ""
        }

        if indice > ultimo:
            ultimo = indice

    return respostas, ultimo


def salvar_rascunho(
    curso_id,
    nome_atividade,
    indice,
    resposta
):

    conn_local = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    cur = conn_local.cursor()

    cur.execute(
        """
        INSERT OR REPLACE INTO
        rascunho_correcao

        (
            curso_id,
            nome_atividade,
            indice,
            aluno,
            email,
            feedback
        )

        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            curso_id,
            nome_atividade,
            indice,
            resposta.get("aluno"),
            resposta.get("email"),
            resposta.get("feedback", "")
        )
    )

    conn_local.commit()

    conn_local.close()


# =========================================================
# 💾 BACKUP
# =========================================================

def criar_backup():

    memoria = io.BytesIO()

    with zipfile.ZipFile(
        memoria,
        "w",
        zipfile.ZIP_DEFLATED
    ) as zipf:

        # -----------------------------------------------
        # Banco
        # -----------------------------------------------

        if os.path.exists(DB_PATH):

            zipf.write(
                DB_PATH,
                arcname="app.db"
            )

        # -----------------------------------------------
        # Imagens
        # -----------------------------------------------

        if os.path.exists(IMAGENS_DIR):

            for raiz, diretorios, arquivos in os.walk(
                IMAGENS_DIR
            ):

                for arquivo in arquivos:

                    caminho = os.path.join(
                        raiz,
                        arquivo
                    )

                    arcname = os.path.relpath(
                        caminho,
                        "."
                    )

                    zipf.write(
                        caminho,
                        arcname=arcname
                    )

    memoria.seek(0)

    return memoria.getvalue()


def restaurar_backup(
    arquivo_backup
):

    temp_dir = tempfile.mkdtemp()

    try:

        # -----------------------------------------------
        # Extrair
        # -----------------------------------------------

        with zipfile.ZipFile(
            arquivo_backup,
            "r"
        ) as zipf:

            zipf.extractall(
                temp_dir
            )

        banco_backup = os.path.join(
            temp_dir,
            "app.db"
        )

        if not os.path.exists(
            banco_backup
        ):

            return False, "O backup não contém app.db."

        # -----------------------------------------------
        # Fecha banco atual
        # -----------------------------------------------

        conn.close()

        # -----------------------------------------------
        # Substitui banco
        # -----------------------------------------------

        shutil.copy2(
            banco_backup,
            DB_PATH
        )

        # -----------------------------------------------
        # Restaura imagens
        # -----------------------------------------------

        imagens_backup = os.path.join(
            temp_dir,
            IMAGENS_DIR
        )

        if os.path.exists(
            imagens_backup
        ):

            if os.path.exists(
                IMAGENS_DIR
            ):

                shutil.rmtree(
                    IMAGENS_DIR
                )

            shutil.copytree(
                imagens_backup,
                IMAGENS_DIR
            )

        return True, "Backup restaurado com sucesso."

    except Exception as e:

        return False, str(e)

    finally:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )


# =========================================================
# 🧠 ESTADO
# =========================================================

if "tela" not in st.session_state:

    st.session_state.tela = "login"


# =========================================================
# 🔐 LOGIN
# =========================================================

if st.session_state.tela == "login":

    st.title("🔐 Corretor de Atividades")

    st.subheader("Entrar")

    user = st.text_input(
        "Usuário",
        key="login_user"
    )

    senha = st.text_input(
        "Senha",
        type="password",
        key="login_senha"
    )

    if st.button(
        "Entrar",
        type="primary"
    ):

        u = c.execute(
            """
            SELECT id, username, password
            FROM users
            WHERE username=?
            """,
            (user.strip(),)
        ).fetchone()

        if u and verificar_senha(
            senha,
            u[2]
        ):

            st.session_state.user_id = u[0]

            st.session_state.username = u[1]

            st.session_state.tela = "cursos"

            st.rerun()

        else:

            st.error(
                "Usuário ou senha incorretos."
            )

    st.divider()

    # =====================================================
    # CRIAR CONTA
    # =====================================================

    st.subheader("Criar conta")

    new_user = st.text_input(
        "Novo usuário",
        key="novo_usuario"
    )

    new_pass = st.text_input(
        "Nova senha",
        type="password",
        key="nova_senha"
    )

    confirmar_pass = st.text_input(
        "Confirmar senha",
        type="password",
        key="confirmar_senha"
    )

    if st.button(
        "Cadastrar"
    ):

        if not new_user.strip():

            st.error(
                "Digite um nome de usuário."
            )

        elif len(new_pass) < 6:

            st.error(
                "A senha deve ter pelo menos 6 caracteres."
            )

        elif new_pass != confirmar_pass:

            st.error(
                "As senhas não coincidem."
            )

        else:

            try:

                hash_senha = gerar_hash_senha(
                    new_pass
                )

                c.execute(
                    """
                    INSERT INTO users
                    (username, password)
                    VALUES (?, ?)
                    """,
                    (
                        new_user.strip(),
                        hash_senha
                    )
                )

                conn.commit()

                st.success(
                    "Conta criada com sucesso! "
                    "Agora você pode entrar."
                )

            except sqlite3.IntegrityError:

                st.error(
                    "Esse usuário já existe."
                )

    # =====================================================
    # RECUPERAÇÃO DE SENHA
    # =====================================================

    st.divider()

    st.subheader(
        "🔑 Esqueci minha senha"
    )

    st.info(
        "Para redefinir a senha, use o código "
        "de recuperação configurado nos Secrets "
        "do Streamlit."
    )

    usuario_recuperacao = st.text_input(
        "Usuário",
        key="usuario_recuperacao"
    )

    codigo_recuperacao = st.text_input(
        "Código de recuperação",
        type="password",
        key="codigo_recuperacao"
    )

    nova_senha_rec = st.text_input(
        "Nova senha",
        type="password",
        key="nova_senha_rec"
    )

    confirmar_senha_rec = st.text_input(
        "Confirmar nova senha",
        type="password",
        key="confirmar_senha_rec"
    )

    if st.button(
        "Redefinir senha"
    ):

        codigo_correto = obter_codigo_recuperacao()

        if not codigo_correto:

            st.error(
                "O código de recuperação ainda "
                "não foi configurado nos Secrets."
            )

        elif codigo_recuperacao != codigo_correto:

            st.error(
                "Código de recuperação incorreto."
            )

        elif len(nova_senha_rec) < 6:

            st.error(
                "A nova senha deve ter pelo menos "
                "6 caracteres."
            )

        elif nova_senha_rec != confirmar_senha_rec:

            st.error(
                "As senhas não coincidem."
            )

        else:

            usuario = c.execute(
                """
                SELECT id
                FROM users
                WHERE username=?
                """,
                (
                    usuario_recuperacao.strip(),
                )
            ).fetchone()

            if not usuario:

                st.error(
                    "Usuário não encontrado."
                )

            else:

                novo_hash = gerar_hash_senha(
                    nova_senha_rec
                )

                c.execute(
                    """
                    UPDATE users
                    SET password=?
                    WHERE id=?
                    """,
                    (
                        novo_hash,
                        usuario[0]
                    )
                )

                conn.commit()

                st.success(
                    "Senha redefinida com sucesso!"
                )


# =========================================================
# 📂 CURSOS
# =========================================================

elif st.session_state.tela == "cursos":

    st.title("📂 Cursos")

    cursos = c.execute(
        """
        SELECT id, nome, user_id, turma
        FROM cursos
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (
            st.session_state.user_id,
        )
    ).fetchall()

    col_top1, col_top2 = st.columns(2)

    with col_top1:

        if st.button(
            "➕ Novo curso"
        ):

            st.session_state.tela = "novo_curso"

            st.rerun()

    with col_top2:

        if st.button(
            "⚙️ Segurança e Backup"
        ):

            st.session_state.tela = "backup"

            st.rerun()

    st.divider()

    if not cursos:

        st.info(
            "Nenhum curso cadastrado ainda."
        )

    else:

        for curso in cursos:

            col1, col2, col3 = st.columns(
                [4, 1, 1]
            )

            with col1:

                nome_exibicao = curso[1]

                if curso[3]:

                    nome_exibicao += (
                        f" — Turma {curso[3]}"
                    )

                if st.button(
                    nome_exibicao,
                    key=f"open_{curso[0]}"
                ):

                    st.session_state.curso_id = (
                        curso[0]
                    )

                    st.session_state.tela = (
                        "atividades"
                    )

                    st.rerun()

            with col2:

                if st.button(
                    "✏️",
                    key=f"edit_{curso[0]}"
                ):

                    st.session_state.curso_id = (
                        curso[0]
                    )

                    st.session_state.tela = (
                        "editar_alunos"
                    )

                    st.rerun()

            with col3:

                if st.button(
                    "🗑️",
                    key=f"del_{curso[0]}"
                ):

                    st.session_state.confirm_del_curso = (
                        curso[0]
                    )

    # =====================================================
    # CONFIRMAÇÃO DE EXCLUSÃO
    # =====================================================

    if (
        "confirm_del_curso"
        in st.session_state
    ):

        st.warning(
            "⚠️ Tem certeza que deseja excluir "
            "este curso e todos os dados vinculados?"
        )

        col1, col2 = st.columns(2)

        with col1:

            if st.button(
                "✅ Sim, excluir",
                key="confirm_curso"
            ):

                cid = (
                    st.session_state
                    .confirm_del_curso
                )

                # Segurança: somente curso do usuário
                c.execute(
                    """
                    DELETE FROM cursos
                    WHERE id=?
                    AND user_id=?
                    """,
                    (
                        cid,
                        st.session_state.user_id
                    )
                )

                c.execute(
                    """
                    DELETE FROM alunos
                    WHERE curso_id=?
                    """,
                    (cid,)
                )

                atividades_excluidas = c.execute(
                    """
                    SELECT id
                    FROM atividades
                    WHERE curso_id=?
                    """,
                    (cid,)
                ).fetchall()

                for atividade in atividades_excluidas:

                    c.execute(
                        """
                        DELETE FROM resultados
                        WHERE atividade_id=?
                        """,
                        (atividade[0],)
                    )

                c.execute(
                    """
                    DELETE FROM atividades
                    WHERE curso_id=?
                    """,
                    (cid,)
                )

                c.execute(
                    """
                    DELETE FROM rascunho_correcao
                    WHERE curso_id=?
                    """,
                    (cid,)
                )

                conn.commit()

                del st.session_state[
                    "confirm_del_curso"
                ]

                st.rerun()

        with col2:

            if st.button(
                "❌ Cancelar",
                key="cancel_curso"
            ):

                del st.session_state[
                    "confirm_del_curso"
                ]

                st.rerun()


# =========================================================
# 💾 BACKUP E SEGURANÇA
# =========================================================

elif st.session_state.tela == "backup":

    voltar("cursos")

    st.title(
        "⚙️ Segurança e Backup"
    )

    st.info(
        "Esta área permite salvar uma cópia completa "
        "dos seus dados. O backup contém o banco de dados "
        "e as imagens das atividades."
    )

    st.subheader(
        "💾 Fazer backup"
    )

    backup_data = criar_backup()

    nome_backup = (
        "backup_corretor_"
        + datetime.now().strftime(
            "%Y-%m-%d_%H-%M"
        )
        + ".zip"
    )

    st.download_button(
        label="⬇️ Baixar backup completo",
        data=backup_data,
        file_name=nome_backup,
        mime="application/zip"
    )

    st.success(
        "Recomendo baixar um backup ao final de cada "
        "período de correção ou sempre que terminar "
        "um curso importante."
    )

    st.divider()

    st.subheader(
        "♻️ Restaurar backup"
    )

    st.warning(
        "⚠️ Restaurar um backup substituirá os dados "
        "atuais do aplicativo. Faça um backup dos dados "
        "atuais antes de restaurar."
    )

    backup_upload = st.file_uploader(
        "Selecione um backup .zip",
        type=["zip"],
        key="backup_upload"
    )

    if st.button(
        "♻️ Restaurar backup"
    ):

        if backup_upload is None:

            st.error(
                "Selecione primeiro um arquivo de backup."
            )

        else:

            ok, mensagem = restaurar_backup(
                backup_upload
            )

            if ok:

                st.success(
                    mensagem
                )

                st.session_state.clear()

                st.rerun()

            else:

                st.error(
                    f"Não foi possível restaurar: {mensagem}"
                )

    st.divider()

    st.subheader(
        "🔐 Recuperação de senha"
    )

    st.write(
        "O código de recuperação deve ser configurado "
        "nos Secrets do Streamlit."
    )

    st.code(
        "RECOVERY_CODE = \"SEU-CODIGO-DE-RECUPERACAO\""
    )

    st.warning(
        "Não coloque esse código diretamente no app.py "
        "nem no GitHub."
    )


# =========================================================
# 👥 NOVO CURSO
# =========================================================

elif st.session_state.tela == "novo_curso":

    voltar("cursos")

    st.title("Novo curso")

    nome_curso = st.text_input(
        "Nome do curso"
    )

    turma_curso = st.text_input(
        "Turma (ex: A)"
    )

    if "lista_alunos" not in st.session_state:

        st.session_state.lista_alunos = []

    aba_individual, aba_massa = st.tabs(
        [
            "👤 Adicionar Um a Um",
            "📋 Adicionar em Massa"
        ]
    )

    # =====================================================
    # INDIVIDUAL
    # =====================================================

    with aba_individual:

        c1, c2 = st.columns(2)

        with c1:

            nome = st.text_input(
                "Nome do aluno",
                key="nome_ind"
            )

        with c2:

            email = st.text_input(
                "Email",
                key="email_ind"
            )

        if st.button(
            "➕ Adicionar aluno",
            key="btn_add_ind"
        ):

            if nome and email:

                st.session_state.lista_alunos.append(
                    (
                        nome.strip(),
                        email.strip()
                    )
                )

                st.rerun()

            else:

                st.error(
                    "Preencha nome e email."
                )

    # =====================================================
    # MASSA
    # =====================================================

    with aba_massa:

        st.info(
            "Cole no formato Nome, Email ou "
            "Nome;Email. Um aluno por linha."
        )

        texto_massa = st.text_area(
            "Lista de Alunos",
            height=150,
            placeholder=(
                "João Silva, joao@email.com\n"
                "Maria Santos; maria@email.com"
            )
        )

        if st.button(
            "📥 Processar e Adicionar Lista"
        ):

            if texto_massa:

                linhas = (
                    texto_massa
                    .strip()
                    .split("\n")
                )

                adicionados = 0

                for linha in linhas:

                    delimitador = (
                        ","
                        if "," in linha
                        else (
                            ";"
                            if ";" in linha
                            else "\t"
                        )
                    )

                    partes = linha.split(
                        delimitador
                    )

                    if len(partes) >= 2:

                        n = partes[0].strip()
                        e = partes[1].strip()

                        if n and e:

                            st.session_state.lista_alunos.append(
                                (n, e)
                            )

                            adicionados += 1

                st.success(
                    f"{adicionados} alunos adicionados."
                )

                st.rerun()

    st.divider()

    st.subheader(
        "📋 Lista Atual"
    )

    if st.session_state.lista_alunos:

        df_temp = pd.DataFrame(
            st.session_state.lista_alunos,
            columns=[
                "Nome",
                "Email"
            ]
        )

        edited_df = st.data_editor(
            df_temp,
            num_rows="dynamic",
            use_container_width=True,
            key="editor_novos_alunos"
        )

        st.session_state.lista_alunos = list(
            edited_df.itertuples(
                index=False,
                name=None
            )
        )

        if st.button(
            "🗑️ Limpar toda a lista"
        ):

            st.session_state.lista_alunos = []

            st.rerun()

    if st.button(
        "💾 Salvar curso",
        type="primary"
    ):

        if not nome_curso:

            st.error(
                "Preencha o nome do curso."
            )

        else:

            c.execute(
                """
                INSERT INTO cursos
                (nome, user_id, turma)
                VALUES (?, ?, ?)
                """,
                (
                    nome_curso.strip(),
                    st.session_state.user_id,
                    turma_curso.strip()
                )
            )

            curso_id = c.lastrowid

            for aluno in (
                st.session_state.lista_alunos
            ):

                c.execute(
                    """
                    INSERT INTO alunos
                    (nome, email, curso_id)
                    VALUES (?, ?, ?)
                    """,
                    (
                        aluno[0],
                        aluno[1],
                        curso_id
                    )
                )

            conn.commit()

            st.session_state.lista_alunos = []

            st.session_state.tela = "cursos"

            st.rerun()


# =========================================================
# ✏️ EDITAR ALUNOS
# =========================================================

elif st.session_state.tela == "editar_alunos":

    voltar("cursos")

    st.title(
        "Editar alunos do curso"
    )

    curso_existe = c.execute(
        """
        SELECT id
        FROM cursos
        WHERE id=?
        AND user_id=?
        """,
        (
            st.session_state.curso_id,
            st.session_state.user_id
        )
    ).fetchone()

    if not curso_existe:

        st.error(
            "Curso não encontrado."
        )

        st.stop()

    alunos_df = pd.read_sql_query(
        """
        SELECT id, nome, email
        FROM alunos
        WHERE curso_id=?
        """,
        conn,
        params=(
            st.session_state.curso_id,
        )
    )

    st.subheader(
        "Alunos Cadastrados"
    )

    if not alunos_df.empty:

        df_editado = st.data_editor(
            alunos_df,
            column_config={
                "id": None
            },
            disabled=["id"],
            use_container_width=True,
            key="edicao_tabela_alunos"
        )

        if st.button(
            "💾 Salvar Alterações"
        ):

            for _, row in df_editado.iterrows():

                c.execute(
                    """
                    UPDATE alunos
                    SET nome=?, email=?
                    WHERE id=?
                    AND curso_id=?
                    """,
                    (
                        row["nome"],
                        row["email"],
                        row["id"],
                        st.session_state.curso_id
                    )
                )

            conn.commit()

            st.success(
                "Dados atualizados."
            )

            st.rerun()

    else:

        st.info(
            "Nenhum aluno cadastrado."
        )

    st.divider()

    st.subheader(
        "Adicionar Novos Alunos"
    )

    aba_ind, aba_massa = st.tabs(
        [
            "👤 Um por Um",
            "📋 Em Massa"
        ]
    )

    with aba_ind:

        c1, c2 = st.columns(2)

        with c1:

            nome = st.text_input(
                "Nome",
                key="edit_nome_ind"
            )

        with c2:

            email = st.text_input(
                "Email",
                key="edit_email_ind"
            )

        if st.button(
            "➕ Adicionar Aluno",
            key="btn_add_edit"
        ):

            if nome and email:

                c.execute(
                    """
                    INSERT INTO alunos
                    (nome, email, curso_id)
                    VALUES (?, ?, ?)
                    """,
                    (
                        nome.strip(),
                        email.strip(),
                        st.session_state.curso_id
                    )
                )

                conn.commit()

                st.success(
                    "Aluno adicionado!"
                )

                st.rerun()

    with aba_massa:

        st.info(
            "Nome, Email ou Nome;Email."
        )

        texto_massa_edit = st.text_area(
            "Lista para colar",
            height=120,
            key="txt_massa_edit"
        )

        if st.button(
            "📥 Processar e Inserir Todos"
        ):

            if texto_massa_edit:

                linhas = (
                    texto_massa_edit
                    .strip()
                    .split("\n")
                )

                adicionados = 0

                for linha in linhas:

                    delimitador = (
                        ","
                        if "," in linha
                        else (
                            ";"
                            if ";" in linha
                            else "\t"
                        )
                    )

                    partes = linha.split(
                        delimitador
                    )

                    if len(partes) >= 2:

                        n = partes[0].strip()
                        e = partes[1].strip()

                        if n and e:

                            c.execute(
                                """
                                INSERT INTO alunos
                                (nome, email, curso_id)
                                VALUES (?, ?, ?)
                                """,
                                (
                                    n,
                                    e,
                                    st.session_state.curso_id
                                )
                            )

                            adicionados += 1

                conn.commit()

                st.success(
                    f"{adicionados} alunos adicionados."
                )

                st.rerun()

    st.divider()

    if not alunos_df.empty:

        st.subheader(
            "🗑️ Remover Aluno"
        )

        aluno_del = st.selectbox(
            "Selecione o aluno",
            alunos_df["nome"]
        )

        if st.button(
            "Remover Aluno Selecionado",
            type="primary"
        ):

            c.execute(
                """
                DELETE FROM alunos
                WHERE nome=?
                AND curso_id=?
                """,
                (
                    aluno_del,
                    st.session_state.curso_id
                )
            )

            conn.commit()

            st.success(
                "Aluno removido!"
            )

            st.rerun()


# =========================================================
# 📄 ATIVIDADES
# =========================================================

elif st.session_state.tela == "atividades":

    voltar("cursos")

    st.title("Atividades")

    curso_id = st.session_state.curso_id

    curso = c.execute(
        """
        SELECT id, nome, turma
        FROM cursos
        WHERE id=?
        AND user_id=?
        """,
        (
            curso_id,
            st.session_state.user_id
        )
    ).fetchone()

    if not curso:

        st.error(
            "Curso não encontrado."
        )

        st.stop()

    atividades = c.execute(
        """
        SELECT id, nome
        FROM atividades
        WHERE curso_id=?
        ORDER BY id DESC
        """,
        (
            curso_id,
        )
    ).fetchall()

    if atividades:

        for atv in atividades:

            col1, col2 = st.columns(
                [4, 1]
            )

            with col1:

                if st.button(
                    atv[1],
                    key=f"open_{atv[0]}"
                ):

                    st.session_state.atividade_id = (
                        atv[0]
                    )

                    st.session_state.tela = (
                        "resultado"
                    )

                    st.rerun()

            with col2:

                if st.button(
                    "🗑️",
                    key=f"del_{atv[0]}"
                ):

                    st.session_state.confirm_del_atividade = (
                        atv[0]
                    )

    else:

        st.info(
            "Nenhuma atividade cadastrada."
        )

    if (
        "confirm_del_atividade"
        in st.session_state
    ):

        st.warning(
            "⚠️ Tem certeza que deseja excluir "
            "esta atividade?"
        )

        col1, col2 = st.columns(2)

        with col1:

            if st.button(
                "✅ Sim, excluir",
                key="confirm_atv"
            ):

                aid = (
                    st.session_state
                    .confirm_del_atividade
                )

                atividade = c.execute(
                    """
                    SELECT a.id
                    FROM atividades a
                    JOIN cursos cu
                    ON a.curso_id=cu.id
                    WHERE a.id=?
                    AND cu.user_id=?
                    """,
                    (
                        aid,
                        st.session_state.user_id
                    )
                ).fetchone()

                if atividade:

                    c.execute(
                        """
                        DELETE FROM resultados
                        WHERE atividade_id=?
                        """,
                        (aid,)
                    )

                    c.execute(
                        """
                        DELETE FROM atividades
                        WHERE id=?
                        """,
                        (aid,)
                    )

                    conn.commit()

                del st.session_state[
                    "confirm_del_atividade"
                ]

                st.rerun()

        with col2:

            if st.button(
                "❌ Cancelar",
                key="cancel_atv"
            ):

                del st.session_state[
                    "confirm_del_atividade"
                ]

                st.rerun()

    st.divider()

    if st.button(
        "➕ Nova atividade"
    ):

        st.session_state.tela = (
            "nova_atividade"
        )

        st.rerun()


# =========================================================
# ✏️ NOVA ATIVIDADE
# =========================================================

elif st.session_state.tela == "nova_atividade":

    voltar("atividades")

    st.title("Nova atividade")

    nome_atv = st.text_input(
        "Nome"
    )

    paginas_por_aluno = st.number_input(
        "📄 Páginas por aluno",
        min_value=1,
        value=2
    )

    uploaded = st.file_uploader(
        "PDF",
        type=["pdf"]
    )

    if "correcao_iniciada" not in st.session_state:

        st.session_state.correcao_iniciada = False

    # =====================================================
    # PROCESSAMENTO
    # =====================================================

    if (
        uploaded
        and nome_atv
        and not st.session_state.correcao_iniciada
    ):

        pdf_bytes = uploaded.read()

        st.session_state.pdf_bytes = (
            pdf_bytes
        )

        st.session_state.pdf_nome = (
            uploaded.name
        )

        doc = fitz.open(
            stream=pdf_bytes,
            filetype="pdf"
        )

        imagens = []

        for page in doc:

            pix = page.get_pixmap(
                matrix=fitz.Matrix(
                    1.5,
                    1.5
                ),
                alpha=False
            )

            img = Image.frombytes(
                "RGB",
                [
                    pix.width,
                    pix.height
                ],
                pix.samples
            )

            imagens.append(
                img.copy()
            )

        doc.close()

        grupos = []

        for i in range(
            0,
            len(imagens),
            paginas_por_aluno
        ):

            grupos.append(
                {
                    "paginas": imagens[
                        i:i + paginas_por_aluno
                    ]
                }
            )

        st.session_state.grupos = grupos

        respostas, ultimo = (
            carregar_rascunhos(
                st.session_state.curso_id,
                nome_atv
            )
        )

        st.session_state.respostas = (
            respostas
        )

        st.session_state.indice = ultimo

        st.session_state.correcao_iniciada = (
            True
        )

        st.rerun()

    # =====================================================
    # CORREÇÃO
    # =====================================================

    if st.session_state.correcao_iniciada:

        grupos = st.session_state.grupos

        i = st.session_state.indice

        if not grupos:

            st.error(
                "O PDF não possui páginas."
            )

            st.stop()

        if i >= len(grupos):

            i = len(grupos) - 1

            st.session_state.indice = i

        grupo = grupos[i]

        alunos_df = pd.read_sql_query(
            """
            SELECT *
            FROM alunos
            WHERE curso_id=?
            """,
            conn,
            params=(
                st.session_state.curso_id,
            )
        )

        col1, col2 = st.columns(
            [3, 1]
        )

        with col1:

            paginas = grupo["paginas"]

            for j in range(
                0,
                len(paginas),
                2
            ):

                c1, c2 = st.columns(2)

                if j < len(paginas):

                    c1.image(
                        paginas[j],
                        use_container_width=True
                    )

                if j + 1 < len(paginas):

                    c2.image(
                        paginas[j + 1],
                        use_container_width=True
                    )

        with col2:

            st.subheader(
                f"Aluno {i + 1} "
                f"de {len(grupos)}"
            )

            resposta = (
                st.session_state
                .respostas
                .get(i, {})
            )

            alunos_lista = (
                alunos_df["nome"]
                .tolist()
            )

            indice_select = 0

            if (
                resposta.get("aluno")
                in alunos_lista
            ):

                indice_select = (
                    alunos_lista.index(
                        resposta["aluno"]
                    ) + 1
                )

            aluno = st.selectbox(
                "Selecionar aluno",
                [""] + alunos_lista,
                index=indice_select,
                key=f"select_{i}"
            )

            if aluno:

                dados = alunos_df[
                    alunos_df["nome"] == aluno
                ].iloc[0]

                resposta["aluno"] = (
                    dados["nome"]
                )

                resposta["email"] = (
                    dados["email"]
                )

            feedback = st.text_area(
                "Feedback",
                value=resposta.get(
                    "feedback",
                    ""
                ),
                key=f"fb_{i}"
            )

            resposta["feedback"] = (
                feedback
            )

            st.session_state.respostas[i] = (
                resposta
            )

            # Auto-save
            salvar_rascunho(
                st.session_state.curso_id,
                nome_atv,
                i,
                resposta
            )

            prev, prox = st.columns(2)

            if prev.button(
                "⬅️ Anterior",
                disabled=(i == 0)
            ):

                st.session_state.indice -= 1

                st.rerun()

            if prox.button(
                "➡️ Próximo",
                disabled=(
                    i >= len(grupos) - 1
                )
            ):

                st.session_state.indice += 1

                st.rerun()

        st.divider()

        if st.button(
            "💾 Salvar atividade",
            type="primary"
        ):

            salvar_rascunho(
                st.session_state.curso_id,
                nome_atv,
                i,
                resposta
            )

            curso = c.execute(
                """
                SELECT turma
                FROM cursos
                WHERE id=?
                AND user_id=?
                """,
                (
                    st.session_state.curso_id,
                    st.session_state.user_id
                )
            ).fetchone()

            if not curso:

                st.error(
                    "Curso não encontrado."
                )

                st.stop()

            turma = (
                curso[0]
                if curso[0]
                else "SEM TURMA"
            )

            conn2 = sqlite3.connect(
                DB_PATH
            )

            c2 = conn2.cursor()

            c2.execute(
                """
                INSERT INTO atividades
                (nome, curso_id)
                VALUES (?, ?)
                """,
                (
                    nome_atv,
                    st.session_state.curso_id
                )
            )

            atv_id = c2.lastrowid

            for idx, grupo in enumerate(
                grupos
            ):

                r = (
                    st.session_state
                    .respostas
                    .get(idx, {})
                )

                if r.get("aluno"):

                    caminhos = []

                    for j, img in enumerate(
                        grupo["paginas"]
                    ):

                        caminho = (
                            f"{IMAGENS_DIR}/"
                            f"atv_{atv_id}_"
                            f"{idx}_{j}.png"
                        )

                        img.save(
                            caminho
                        )

                        caminhos.append(
                            caminho
                        )

                    c2.execute(
                        """
                        INSERT INTO resultados
                        (
                            atividade_id,
                            nome,
                            email,
                            turma,
                            feedback,
                            imagens,
                            enviado
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            atv_id,
                            r["aluno"],
                            r["email"],
                            turma,
                            r.get(
                                "feedback",
                                ""
                            ),
                            ";".join(
                                caminhos
                            ),
                            0
                        )
                    )

            conn2.commit()

            conn2.close()

            # Limpa rascunhos
            c.execute(
                """
                DELETE FROM rascunho_correcao
                WHERE curso_id=?
                AND nome_atividade=?
                """,
                (
                    st.session_state.curso_id,
                    nome_atv
                )
            )

            conn.commit()

            for chave in [
                "grupos",
                "indice",
                "respostas",
                "correcao_iniciada",
                "pdf_bytes",
                "pdf_nome"
            ]:

                if chave in st.session_state:

                    del st.session_state[
                        chave
                    ]

            st.success(
                "Atividade salva com sucesso!"
            )

            st.session_state.tela = (
                "atividades"
            )

            st.rerun()


# =========================================================
# 📊 RESULTADO
# =========================================================

elif st.session_state.tela == "resultado":

    voltar("atividades")

    st.title(
        "📊 Planilha da Atividade"
    )

    # -----------------------------------------------------
    # Verifica se atividade pertence ao usuário
    # -----------------------------------------------------

    atividade = c.execute(
        """
        SELECT a.id, a.nome
        FROM atividades a
        JOIN cursos cu
        ON a.curso_id=cu.id
        WHERE a.id=?
        AND cu.user_id=?
        """,
        (
            st.session_state.atividade_id,
            st.session_state.user_id
        )
    ).fetchone()

    if not atividade:

        st.error(
            "Atividade não encontrada."
        )

        st.stop()

    conn3 = sqlite3.connect(
        DB_PATH
    )

    df = pd.read_sql_query(
        """
        SELECT
            id,
            nome,
            turma,
            email,
            feedback,
            imagens,
            enviado

        FROM resultados

        WHERE atividade_id=?
        """,
        conn3,
        params=(
            st.session_state.atividade_id,
        )
    )

    conn3.close()

    # =====================================================
    # EMAIL
    # =====================================================

    assunto_email = st.text_input(
        "Assunto do e-mail",
        value="Feedback da atividade"
    )

    st.subheader(
        "Configuração de envio"
    )

    email_remetente = st.text_input(
        "Seu e-mail (remetente)"
    )

    senha_app = st.text_input(
        "Senha de app",
        type="password"
    )

    assinatura = st.text_area(
        "Assinatura do e-mail",
        value="Att,\nProfessor(a)"
    )

    pdf_file = st.file_uploader(
        "📎 Anexar material de apoio (PDF)",
        type=["pdf"]
    )

    if pdf_file:

        st.session_state.pdf_bytes = (
            pdf_file.read()
        )

        st.session_state.pdf_nome = (
            pdf_file.name
        )

    pdf_bytes = st.session_state.get(
        "pdf_bytes",
        None
    )

    pdf_nome = st.session_state.get(
        "pdf_nome",
        "material_apoio.pdf"
    )

    # =====================================================
    # DADOS
    # =====================================================

    if df.empty:

        st.warning(
            "Nenhum dado encontrado."
        )

    else:

        st.dataframe(
            df[
                [
                    "nome",
                    "turma",
                    "email",
                    "feedback"
                ]
            ],
            use_container_width=True
        )

        # =================================================
        # ENVIAR TODOS
        # =================================================

        if st.button(
            "📤 Enviar para todos",
            key="enviar_todos"
        ):

            sucessos = 0

            for _, row in df.iterrows():

                if int(row["enviado"]) == 0:

                    caminhos = (
                        row["imagens"].split(";")
                        if row["imagens"]
                        else []
                    )

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

                        conn4 = sqlite3.connect(
                            DB_PATH
                        )

                        c4 = conn4.cursor()

                        c4.execute(
                            """
                            UPDATE resultados
                            SET enviado=1
                            WHERE id=?
                            """,
                            (
                                row["id"],
                            )
                        )

                        conn4.commit()

                        conn4.close()

                        sucessos += 1

                    except Exception as e:

                        st.error(
                            f"Erro com "
                            f"{row['nome']}: {e}"
                        )

            st.success(
                f"{sucessos} e-mails enviados."
            )

            st.rerun()

        # =================================================
        # LOOP ALUNOS
        # =================================================

        for idx, row in df.iterrows():

            st.markdown(
                f"### {row['nome']} - "
                f"{row['turma']}"
            )

            # ---------------------------------------------
            # IMAGENS
            # ---------------------------------------------

            if row["imagens"]:

                caminhos = (
                    row["imagens"]
                    .split(";")
                )

                for i in range(
                    0,
                    len(caminhos),
                    2
                ):

                    col1, col2 = st.columns(2)

                    if (
                        i < len(caminhos)
                        and os.path.exists(
                            caminhos[i]
                        )
                    ):

                        try:

                            img = Image.open(
                                caminhos[i]
                            ).copy()

                            col1.image(
                                img,
                                use_container_width=True
                            )

                        except Exception as e:

                            col1.error(
                                f"Erro ao abrir "
                                f"imagem: {e}"
                            )

                    if (
                        i + 1 < len(caminhos)
                        and os.path.exists(
                            caminhos[i + 1]
                        )
                    ):

                        try:

                            img = Image.open(
                                caminhos[i + 1]
                            ).copy()

                            col2.image(
                                img,
                                use_container_width=True
                            )

                        except Exception as e:

                            col2.error(
                                f"Erro ao abrir "
                                f"imagem: {e}"
                            )

            # ---------------------------------------------
            # FEEDBACK
            # ---------------------------------------------

            edit_key = (
                f"editando_{row['id']}"
            )

            if edit_key not in st.session_state:

                st.session_state[
                    edit_key
                ] = False

            col_fb, col_btn = st.columns(
                [8, 1]
            )

            with col_fb:

                if not st.session_state[
                    edit_key
                ]:

                    st.markdown(
                        f"**Feedback:** "
                        f"{row['feedback']}"
                    )

                else:

                    novo_feedback = st.text_area(
                        "Editar feedback",
                        value=row["feedback"],
                        key=(
                            f"edit_text_"
                            f"{row['id']}"
                        )
                    )

            with col_btn:

                if not st.session_state[
                    edit_key
                ]:

                    if st.button(
                        "✏️",
                        key=f"editar_{row['id']}"
                    ):

                        st.session_state[
                            edit_key
                        ] = True

                        st.rerun()

                else:

                    if st.button(
                        "💾",
                        key=f"salvar_{row['id']}"
                    ):

                        novo_feedback = (
                            st.session_state[
                                f"edit_text_{row['id']}"
                            ]
                        )

                        conn_edit = sqlite3.connect(
                            DB_PATH
                        )

                        c_edit = (
                            conn_edit.cursor()
                        )

                        c_edit.execute(
                            """
                            UPDATE resultados
                            SET feedback=?
                            WHERE id=?
                            """,
                            (
                                novo_feedback,
                                row["id"]
                            )
                        )

                        conn_edit.commit()

                        conn_edit.close()

                        st.session_state[
                            edit_key
                        ] = False

                        st.success(
                            "Feedback atualizado!"
                        )

                        st.rerun()

            # ---------------------------------------------
            # STATUS
            # ---------------------------------------------

            status = (
                "✅ Enviado"
                if int(row["enviado"]) == 1
                else "⏳ Não enviado"
            )

            st.write(
                f"Status: {status}"
            )

            # ---------------------------------------------
            # REENVIO
            # ---------------------------------------------

            if st.button(
                f"🔁 Reenviar para {row['nome']}",
                key=(
                    f"send_"
                    f"{row['id']}"
                )
            ):

                caminhos = (
                    row["imagens"].split(";")
                    if row["imagens"]
                    else []
                )

                try:

                    conn_temp = sqlite3.connect(
                        DB_PATH
                    )

                    c_temp = (
                        conn_temp.cursor()
                    )

                    resultado = c_temp.execute(
                        """
                        SELECT feedback
                        FROM resultados
                        WHERE id=?
                        """,
                        (
                            row["id"],
                        )
                    ).fetchone()

                    feedback_atual = (
                        resultado[0]
                        if resultado
                        else ""
                    )

                    conn_temp.close()

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

                    conn4 = sqlite3.connect(
                        DB_PATH
                    )

                    c4 = conn4.cursor()

                    c4.execute(
                        """
                        UPDATE resultados
                        SET enviado=1
                        WHERE id=?
                        """,
                        (
                            row["id"],
                        )
                    )

                    conn4.commit()

                    conn4.close()

                    st.success(
                        "E-mail reenviado!"
                    )

                    st.rerun()

                except Exception as e:

                    st.error(
                        f"Erro ao enviar: {e}"
                    )

            st.divider()
