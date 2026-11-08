import streamlit as st
import pandas as pd
import gspread
import json

# 1. Configuração da página para telemóvel
st.set_page_config(page_title="Meu Dashboard", page_icon="💰", layout="centered")
st.title("📊 Painel Financeiro")

# 2. Conectar ao Google Sheets (Usando os Segredos do Streamlit)
try:
    credenciais_dict = json.loads(st.secrets["CREDENCIAIS_GOOGLE"])
    gc = gspread.service_account_from_dict(credenciais_dict)
    planilha = gc.open_by_url(st.secrets["URL_PLANILHA"])
    aba = planilha.sheet1
    
    # 3. Carregar e tratar os dados
    dados = aba.get_all_records()
    
    if not dados:
        st.warning("A planilha está vazia. Registre algum gasto no Telegram!")
    else:
        df = pd.DataFrame(dados)
        
        # Limpar a coluna Valor para fazer contas matemáticas
        def limpar_valor(v):
            try:
                return float(str(v).replace('R$', '').replace('.', '').replace(',', '.').strip())
            except:
                return 0.0
                
        df['Valor'] = df['Valor'].apply(limpar_valor)
        
        # 4. Criar as métricas no topo do site
        receitas = df[df['Tipo'] == 'Receita']['Valor'].sum()
        despesas = df[df['Tipo'] == 'Despesa']['Valor'].sum()
        saldo = receitas - despesas
        
        col1, col2, col3 = st.columns(3)
        col1.metric("🟢 Receitas", f"R$ {receitas:.2f}")
        col2.metric("🔴 Despesas", f"R$ {despesas:.2f}")
        col3.metric("💰 Saldo", f"R$ {saldo:.2f}")
        
        # 5. Mostrar a tabela na ecrã
        st.subheader("🛒 Últimos Lançamentos")
        st.dataframe(df.tail(10)) # Mostra apenas as últimas 10 linhas

except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
