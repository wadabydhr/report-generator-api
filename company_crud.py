import os
import streamlit as st
from pymongo import MongoClient
from bson.objectid import ObjectId

# Use Render.com environment variable for the Mongo URI
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://hirokiwada:BYNDHR19hiw@byndhr-cluster.1zn6ljk.mongodb.net/?retryWrites=true&w=majority&appName=BYNDHR-CLUSTER"
)
MONGO_DB = os.getenv("MONGODB_DB", "report_generator")
MONGO_COLLECTION = os.getenv("MONGODB_COMPANIES_COLLECTION", "companies")

def get_mongo_collection():
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    return db[MONGO_COLLECTION]

def get_all_companies():
    collection = get_mongo_collection()
    companies = list(collection.find({}, {"_id": 1, "company_name": 1}))
    return companies

def add_company(company_name):
    collection = get_mongo_collection()
    if collection.find_one({"company_name": {"$regex": f"^{company_name}$", "$options": "i"}}):
        return False, "Empresa já existe."
    result = collection.insert_one({"company_name": company_name})
    return True, f"Empresa adicionada com id {result.inserted_id}"

def update_company(company_id, new_name):
    collection = get_mongo_collection()
    result = collection.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": {"company_name": new_name}}
    )
    return result.modified_count > 0

def delete_company(company_id):
    collection = get_mongo_collection()
    result = collection.delete_one({"_id": ObjectId(company_id)})
    return result.deleted_count > 0

st.set_page_config(page_title="CRUD Empresas (MongoDB)", layout="centered")

# --- Simple Navigation ---
st.markdown(
    """
    <style>
    .nav-link {
        background-color: #f0f2f6;
        color: #262730;
        padding: 0.5em 1em;
        border-radius: 8px;
        text-decoration: none;
        margin-right: 10px;
        font-weight: 500;
        border: 1px solid #e6e6e6;
    }
    .nav-link:hover {
        background-color: #e6e6e6;
    }
    </style>
    <div>
        <a class="nav-link" href="/unified_report_generator" target="_self">Ir para Gerador de Relatórios</a>
    </div>
    """,
    unsafe_allow_html=True
)

st.title("🗃️ CRUD de Empresas (COMPANY) - MongoDB")

st.subheader("Adicionar nova empresa")
with st.form("adicionar_empresa"):
    new_company = st.text_input("Nome da empresa", key="add_company")
    submitted = st.form_submit_button("Adicionar")
    if submitted and new_company.strip():
        ok, msg = add_company(new_company.strip())
        if ok:
            st.success(msg)
        else:
            st.warning(msg)

st.divider()
st.subheader("Empresas cadastradas")

companies = get_all_companies()
if not companies:
    st.info("Nenhuma empresa cadastrada.")
else:
    for company in companies:
        col1, col2, col3 = st.columns([6,2,2])
        with col1:
            st.text_input(
                f"Empresa (ID: {company['_id']})", 
                value=company['company_name'], 
                key=f"name_{company['_id']}", 
                disabled=True
            )
        with col2:
            if st.button("Editar", key=f"edit_{company['_id']}"):
                st.session_state[f"editing_{company['_id']}"] = True
        with col3:
            if st.button("Excluir", key=f"delete_{company['_id']}"):
                deleted = delete_company(company['_id'])
                if deleted:
                    st.success("Empresa excluída.")
                    st.experimental_rerun()
                else:
                    st.error("Erro ao excluir empresa.")

        if st.session_state.get(f"editing_{company['_id']}", False):
            new_name = st.text_input(
                f"Novo nome para empresa (ID: {company['_id']})", 
                value=company['company_name'], 
                key=f"edit_name_{company['_id']}"
            )
            if st.button("Salvar", key=f"save_{company['_id']}"):
                updated = update_company(company['_id'], new_name.strip())
                if updated:
                    st.success("Nome da empresa atualizado.")
                else:
                    st.error("Não foi possível atualizar o nome.")
                st.session_state[f"editing_{company['_id']}"] = False
                st.experimental_rerun()
            if st.button("Cancelar", key=f"cancel_{company['_id']}"):
                st.session_state[f"editing_{company['_id']}"] = False
                st.experimental_rerun()

st.caption("Desenvolvido para gerenciar facilmente a lista de empresas no MongoDB para o campo COMPANY.")
