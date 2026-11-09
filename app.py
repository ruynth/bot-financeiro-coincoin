import streamlit as st
import pandas as pd
import gspread
import json

st.set_page_config(page_title="Meu Dashboard", page_icon="💰", layout="centered")

# Captura o parâmetro da URL enviado pelo botão do Telegram
usuario_url = st.query_params.get("usuario", None)

if usuario_url:
    st.title(f"📊 Painel Financeiro - {usuario_url}")
else:
    st.title("📊 Painel Financeiro")

try:
    credenciais_dict = json.loads(st.secrets["CREDENCIAIS_GOOGLE"])
    gc = gspread.service_account_from_dict(credenciais_dict)
    planilha = gc.open_by_url(st.secrets["URL_PLANILHA"])
    aba = planilha.sheet1
    
    dados = aba.get_all_records()
    
    if not dados:
        st.warning("A planilha está vazia.")
    else:
        df = pd.DataFrame(dados)
        
        # Filtra automaticamente se houver um usuário especificado no link
        if usuario_url and 'Usuário' in df.columns:
            df = df[df['Usuário'] == usuario_url]

        if df.empty:
            st.warning(f"Nenhum registro encontrado para {usuario_url}.")
        else:
            def limpar_valor(v):
                try:
                    return float(str(v).replace('R$', '').replace('.', '').replace(',', '.').strip())
                except:
                    return 0.0
                    
            df['Valor'] = df['Valor'].apply(limpar_valor)
            
            # Métricas calculadas exclusivamente para os dados filtrados
            receitas = df[df['Tipo'] == 'Receita']['Valor'].sum()
            despesas = df[df['Tipo'] == 'Despesa']['Valor'].sum()
            saldo = receitas - despesas
            
            col1, col2, col3 = st.columns(3)
            col1.metric("🟢 Receitas", f"R$ {receitas:.2f}")
            col2.metric("🔴 Despesas", f"R$ {despesas:.2f}")
            col3.metric("💰 Saldo", f"R$ {saldo:.2f}")
            
            st.subheader("🛒 Seus Últimos Lançamentos")
            st.dataframe(df.tail(10))

except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
