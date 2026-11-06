import telebot
import gspread
import json
import os
from datetime import datetime
from flask import Flask, request
from threading import Thread
from groq import Groq

# 1. BLINDAGEM DAS VARIÁVEIS DE AMBIENTE
CHAVE_TELEGRAM = str(os.environ.get("CHAVE_TELEGRAM")).strip()
CHAVE_GROQ = str(os.environ.get("CHAVE_GROQ")).strip()
URL_PLANILHA = str(os.environ.get("URL_PLANILHA")).strip()
CREDENCIAIS_JSON = str(os.environ.get("CREDENCIAIS_GOOGLE")).strip()
URL_RENDER = str(os.environ.get("RENDER_EXTERNAL_URL")).strip().rstrip('/')

app = Flask(__name__)
bot = telebot.TeleBot(CHAVE_TELEGRAM)

# 2. CONEXÃO COM GOOGLE SHEETS E GROQ
credenciais_dict = json.loads(CREDENCIAIS_JSON)
gc = gspread.service_account_from_dict(credenciais_dict)
planilha = gc.open_by_url(URL_PLANILHA)
aba = planilha.sheet1

client_groq = Groq(api_key=CHAVE_GROQ)

# 3. EXTRAÇÃO DE DADOS (MOTOR LLAMA 3 - GROQ)
def extrair_dados(mensagem):
    prompt = f"""Analise este gasto: "{mensagem}"
    Responda EXCLUSIVAMENTE em formato JSON com:
    "descricao", "valor" (com ponto decimal) e "categoria" (Alimentação, Transporte, Lazer, Educação, Moradia, Saúde ou Outros).
    Sem markdown."""
    
    resposta = client_groq.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        temperature=0,
        response_format={"type": "json_object"}
    )
    
    texto_json = resposta.choices[0].message.content
    return json.loads(texto_json)

# 4. COMANDOS DO TELEGRAM
@bot.message_handler(commands=['resumo'])
def mostrar_resumo(mensagem):
    msg_espera = bot.reply_to(mensagem, "📊 Calculando...")
    try:
        dados = aba.get_all_values()
        if len(dados) <= 1:
            bot.edit_message_text("Nenhum gasto registrado ainda.", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)
            return
            
        resumo_categorias = {}
        total_geral = 0.0
        for linha in dados[1:]:
            if len(linha) >= 4:
                valor_str = str(linha[2]).replace('R$', '').replace(',', '.').strip()
                try:
                    valor = float(valor_str)
                except ValueError:
                    continue
                categoria = linha[3]
                resumo_categorias[categoria] = resumo_categorias.get(categoria, 0) + valor
                total_geral += valor

        texto_resposta = "📊 **Resumo de Gastos**\n\n"
        for cat, val in resumo_categorias.items():
            texto_resposta += f"📂 {cat}: R$ {val:.2f}\n"
        texto_resposta += f"\n💰 **Total Geral: R$ {total_geral:.2f}**"
        
        bot.delete_message(mensagem.chat.id, msg_espera.message_id)
        bot.send_message(mensagem.chat.id, texto_resposta, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Erro: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)

@bot.message_handler(commands=['desfazer'])
def apagar_ultima_linha(mensagem):
    msg_espera = bot.reply_to(mensagem, "🗑️ Apagando o último registro...")
    try:
        dados = aba.get_all_values()
        total_linhas = len(dados)
        
        if total_linhas <= 1:
            bot.edit_message_text("A planilha já está vazia.", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)
            return
        
        ultima_linha = dados[-1]
        item_apagado = ultima_linha[1] if len(ultima_linha) > 1 else "Item"
        valor_apagado = ultima_linha[2] if len(ultima_linha) > 2 else "0"
        
        aba.delete_rows(total_linhas)
        
        mensagem_sucesso = f"✅ **Desfeito!**\n\n'{item_apagado}' (R$ {valor_apagado}) removido."
        bot.edit_message_text(mensagem_sucesso, chat_id=mensagem.chat.id, message_id=msg_espera.message_id, parse_mode='Markdown')
        
    except Exception as e:
        bot.edit_message_text(f"❌ Erro ao apagar: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)

@bot.message_handler(func=lambda message: True)
def receber_gasto(mensagem):
    msg_espera = bot.reply_to(mensagem, "⏳ Processando...")
    try:
        dados = extrair_dados(mensagem.text)
        nova_linha = [datetime.now().strftime("%d/%m/%Y"), dados['descricao'], dados['valor'], dados['categoria']]
        aba.append_row(nova_linha)
        bot.delete_message(mensagem.chat.id, msg_espera.message_id)
        resposta_final = f"✅ **Salvo!**\n🛒 Item: {dados['descricao']}\n💰 Valor: R$ {dados['valor']}\n📂 Categoria: {dados['categoria']}"
        bot.send_message(mensagem.chat.id, resposta_final, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Erro: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)

# 5. ROTAS DO WEBHOOK (FLASK)
@app.route('/')
def home():
    return "Bot online via Webhook com motor Groq!"

@app.route('/' + CHAVE_TELEGRAM, methods=['POST'])
def webhook():
    try:
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        Thread(target=bot.process_new_updates, args=([update],)).start()
        return "OK", 200
    except Exception as e:
        print(f"Erro no webhook: {e}")
        return "Erro", 500

if __name__ == "__main__":
    webhook_final = f"{URL_RENDER}/{CHAVE_TELEGRAM}"
    print(f"🔗 URL do Webhook ativada: {webhook_final}")
    
    bot.remove_webhook()
    bot.set_webhook(url=webhook_final)
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
