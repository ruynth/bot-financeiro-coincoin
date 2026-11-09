import telebot
import gspread
import json
import os
import csv
import io
from datetime import datetime
from flask import Flask, request
from threading import Thread
from groq import Groq

# 1. VARIÁVEIS DE AMBIENTE E TRAVA
CHAVE_TELEGRAM = str(os.environ.get("CHAVE_TELEGRAM")).strip()
CHAVE_GROQ = str(os.environ.get("CHAVE_GROQ")).strip()
URL_PLANILHA = str(os.environ.get("URL_PLANILHA")).strip()
CREDENCIAIS_JSON = str(os.environ.get("CREDENCIAIS_GOOGLE")).strip()
URL_RENDER = str(os.environ.get("RENDER_EXTERNAL_URL")).strip().rstrip('/')
# Separa os IDs autorizados por vírgula
IDS_PERMITIDOS = str(os.environ.get("IDS_PERMITIDOS", "")).split(',') 

app = Flask(__name__)
bot = telebot.TeleBot(CHAVE_TELEGRAM)

credenciais_dict = json.loads(CREDENCIAIS_JSON)
gc = gspread.service_account_from_dict(credenciais_dict)
planilha = gc.open_by_url(URL_PLANILHA)
aba = planilha.sheet1
client_groq = Groq(api_key=CHAVE_GROQ)

# 2. FUNÇÃO DE SEGURANÇA
def tem_permissao(mensagem):
    id_usuario = str(mensagem.chat.id)
    if id_usuario in IDS_PERMITIDOS:
        return True
    
    texto_bloqueio = f"⛔ **Acesso Negado.**\n\nSeu ID do Telegram é: `{id_usuario}`\n\nEnvie este número para o administrador liberar seu acesso."
    bot.reply_to(mensagem, texto_bloqueio, parse_mode='Markdown')
    return False

# 3. EXTRAÇÃO DE DADOS (AGORA COM REGRAS MAIS RÍGIDAS)
def extrair_dados(mensagem):
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    
    prompt = f"""Analise as movimentações: "{mensagem}"
    Hoje é dia {data_hoje}.
    Responda EXCLUSIVAMENTE em JSON contendo uma lista "movimentacoes". Cada item tem:
    "data" (DD/MM/YYYY),
    "tipo" ("Despesa" ou "Receita"),
    "descricao" (Apenas o nome do item/serviço limpo. NUNCA inclua o valor numérico, nem as palavras 'reais', 'dinheiro' ou a forma de pagamento nesta chave), 
    "valor" (apenas números com ponto), 
    "categoria" (Alimentação, Transporte, Lazer, Educação, Moradia, Saúde, Salário ou Outros),
    "pagamento" (Cartão de Débito, Cartão de Crédito, Pix ou Dinheiro)."""
    
    resposta = client_groq.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="qwen/qwen3.8-27b",
        temperature=0,
        response_format={"type": "json_object"}
    )
    return json.loads(resposta.choices[0].message.content)["movimentacoes"]


# 4. COMANDOS DO BOT
@bot.message_handler(commands=['zerar'])
def zerar_planilha(mensagem):
    if not tem_permissao(mensagem): return
    msg_espera = bot.reply_to(mensagem, "⚠️ Apagando TODOS os registros...")
    try:
        aba.clear()
        # Cabeçalho atualizado com Usuário e Tipo
        aba.append_row(["Data", "Usuário", "Tipo", "Descrição", "Valor", "Categoria", "Pagamento"])
        bot.edit_message_text("✅ **Planilha resetada!** Novo esquema de colunas criado.", chat_id=mensagem.chat.id, message_id=msg_espera.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Erro ao zerar: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)

@bot.message_handler(commands=['mes'])
def resumo_mes(mensagem):
    if not tem_permissao(mensagem): return
    msg_espera = bot.reply_to(mensagem, "📊 Calculando o saldo do mês...")
    try:
        comando = mensagem.text.split()
        mes_ano_alvo = comando[1] if len(comando) > 1 else datetime.now().strftime("%m/%Y")
            
        dados = aba.get_all_values()
        total_receitas = 0.0
        total_despesas = 0.0
        
        for linha in dados[1:]:
            if len(linha) >= 7 and linha[0].endswith(mes_ano_alvo):
                tipo = linha[2]
                try: valor = float(str(linha[4]).replace('R$', '').replace(',', '.').strip())
                except: continue
                
                if tipo == "Receita": total_receitas += valor
                else: total_despesas += valor

        saldo = total_receitas - total_despesas

        texto = f"📊 **Balanço de {mes_ano_alvo}**\n\n"
        texto += f"🟢 Receitas: R$ {total_receitas:.2f}\n"
        texto += f"🔴 Despesas: R$ {total_despesas:.2f}\n"
        texto += f"\n{'🔵' if saldo >= 0 else '⭕'} **Saldo Final: R$ {saldo:.2f}**"
        
        bot.edit_message_text(texto, chat_id=mensagem.chat.id, message_id=msg_espera.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Erro: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)

@bot.message_handler(commands=['exportar'])
def exportar_planilha(mensagem):
    if not tem_permissao(mensagem): return
    msg_espera = bot.reply_to(mensagem, "📁 Gerando arquivo CSV...")
    try:
        comando = mensagem.text.split()
        mes_ano = comando[1] if len(comando) > 1 else None
        dados = aba.get_all_values()
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';') 
        writer.writerow(dados[0])
        
        linhas = 0
        for linha in dados[1:]:
            if mes_ano:
                if len(linha) > 0 and linha[0].endswith(mes_ano):
                    writer.writerow(linha)
                    linhas += 1
            else:
                writer.writerow(linha)
                linhas += 1
                
        arquivo_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))
        arquivo_bytes.name = f"relatorio_{mes_ano.replace('/', '_')}.csv" if mes_ano else "relatorio_completo.csv"
        
        bot.delete_message(mensagem.chat.id, msg_espera.message_id)
        bot.send_document(mensagem.chat.id, arquivo_bytes, caption=f"✅ Relatório com {linhas} registros!")
    except Exception as e:
        bot.edit_message_text(f"❌ Erro: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)

@bot.message_handler(commands=['painel', 'dashboard'])
def enviar_painel(mensagem):
    if not tem_permissao(mensagem): return
    
    link_do_site = "https://bot-financeiro-coincoin-9gylfgnzc6abvlj8vtix5m.streamlit.app/"
    
    texto = "📊 **O seu Painel Financeiro está online!**\n\n"
    texto += "Acesse o link abaixo para visualizar os seus gráficos de receitas, despesas e o balanço completo:\n\n"
    texto += f"🌐 {link_do_site}"
    
    bot.reply_to(mensagem, texto, parse_mode='Markdown')


@bot.message_handler(commands=['desfazer'])
def apagar_ultima_linha(mensagem):
    if not tem_permissao(mensagem): return
    msg_espera = bot.reply_to(mensagem, "🗑️ Apagando...")
    try:
        dados = aba.get_all_values()
        if len(dados) <= 1:
            bot.edit_message_text("Planilha vazia.", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)
            return
        aba.delete_rows(len(dados))
        bot.edit_message_text("✅ **Último registo desfeito!**", chat_id=mensagem.chat.id, message_id=msg_espera.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Erro: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)


@bot.message_handler(func=lambda message: True)
def receber_gasto(mensagem):
    if not tem_permissao(mensagem): return
    msg_espera = bot.reply_to(mensagem, "⏳ Registrando...")
    try:
        lista_gastos = extrair_dados(mensagem.text)
        linhas_para_inserir = []
        # Captura o nome da pessoa no Telegram
        nome_usuario = mensagem.from_user.first_name 
        
        # Cabeçalho mantendo a contagem e o nome de quem registrou
        resposta_final = f"✅ **{len(lista_gastos)} registro(s) de {nome_usuario} salvo(s)!**\n\n"
        
        for dados in lista_gastos:
            icone = "🟢" if dados['tipo'] == "Receita" else "🔴"
            
            # 1. Troca o ponto por vírgula para o Google Sheets entender que é número
            valor_planilha = str(dados['valor']).replace('.', ',')
            
            # Prepara a linha usando a nova variável 'valor_planilha'
            linhas_para_inserir.append([dados['data'], nome_usuario, dados['tipo'], dados['descricao'], valor_planilha, dados['categoria'], dados['pagamento']])
            
            # Monta a mensagem visual detalhada para o Telegram
            resposta_final += f"{icone} **{dados['tipo']}**\n"
            resposta_final += f"📅 Data: {dados['data']}\n"
            resposta_final += f"🛒 Item: {dados['descricao']}\n"
            resposta_final += f"💰 Valor: R$ {dados['valor']}\n"
            resposta_final += f"📂 Categoria: {dados['categoria']}\n"
            resposta_final += f"💳 Pagamento: {dados['pagamento']}\n\n"
            
        aba.append_rows(linhas_para_inserir, value_input_option="USER_ENTERED")

        bot.delete_message(mensagem.chat.id, msg_espera.message_id)
        
        # O strip() no final remove espaços em branco sobrando e deixa a mensagem alinhada
        bot.send_message(mensagem.chat.id, resposta_final.strip(), parse_mode='Markdown')
        
    except Exception as e:
        bot.edit_message_text(f"❌ Erro: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)



# 5. ROTAS DO WEBHOOK
@app.route('/')
def home():
    return "Bot online!"

@app.route('/' + CHAVE_TELEGRAM, methods=['POST'])
def webhook():
    try:
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        Thread(target=bot.process_new_updates, args=([update],)).start()
        return "OK", 200
    except:
        return "Erro", 500

if __name__ == "__main__":
    webhook_final = f"{URL_RENDER}/{CHAVE_TELEGRAM}"
    bot.remove_webhook()
    bot.set_webhook(url=webhook_final)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
