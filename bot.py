import telebot
import gspread
from google import genai
import json
import os
from datetime import datetime
from flask import Flask, request
from threading import Thread

CHAVE_TELEGRAM = os.environ.get("CHAVE_TELEGRAM")
CHAVE_GEMINI = os.environ.get("CHAVE_GEMINI")
URL_PLANILHA = os.environ.get("URL_PLANILHA")
CREDENCIAIS_JSON = os.environ.get("CREDENCIAIS_GOOGLE")
URL_RENDER = os.environ.get("URL_RENDER") # Nova variável!

app = Flask(__name__)
bot = telebot.TeleBot(CHAVE_TELEGRAM)

credenciais_dict = json.loads(CREDENCIAIS_JSON)
gc = gspread.service_account_from_dict(credenciais_dict)
planilha = gc.open_by_url(URL_PLANILHA)
aba = planilha.sheet1

client_gemini = genai.Client(api_key=CHAVE_GEMINI)

def extrair_dados(mensagem):
    prompt = f"""Analise este gasto: "{mensagem}"
    Responda EXCLUSIVAMENTE em formato JSON com:
    "descricao", "valor" (com ponto decimal) e "categoria" (Alimentação, Transporte, Lazer, Educação, Moradia, Saúde ou Outros).
    Sem markdown.
    """
    resposta = client_gemini.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
    return json.loads(texto_limpo)

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

# ==========================================
# MOTOR DO WEBHOOK (O SEGREDO DA VELOCIDADE)
# ==========================================
@app.route('/')
def home():
    return "Bot online via Webhook!"

@app.route('/' + CHAVE_TELEGRAM, methods=['POST'])
def webhook():
    # Lê a mensagem do Telegram e processa em segundo plano
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    Thread(target=bot.process_new_updates, args=([update],)).start()
    return "OK", 200

if __name__ == "__main__":
    # Força a limpeza de espaços invisíveis e barras acidentais
    url_limpa = str(URL_RENDER).strip().rstrip('/')
    token_limpo = str(CHAVE_TELEGRAM).strip()
    
    webhook_final = f"{url_limpa}/{token_limpo}"
    print(f"🔗 URL do Webhook gerada: {webhook_final}") # Mostra no log para investigarmos
    
    bot.remove_webhook()
    bot.set_webhook(url=webhook_final)
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
