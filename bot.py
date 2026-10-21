import telebot
import gspread
from google import genai
import json
from datetime import datetime

# ==========================================
# 1. CONFIGURAÇÕES E CHAVES
# ==========================================
CHAVE_TELEGRAM = "8768735507:AAHr7TIqdTHgV8sR3CvqTIFkaMVECRQ2aUA"
CHAVE_GEMINI = "AQ.Ab8RN6IyNZsCdSxawTqt_1Y55-_bI3npS7CbNhdZvfRv2gRoog"
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1vby4hY_ULVIsl3Ury0JAeHeriECma3iH2s9oPkC9ULA/edit?usp=sharing"

print("Iniciando conexões...")
# Conecta no Telegram
bot = telebot.TeleBot(CHAVE_TELEGRAM)

# Conecta na Planilha
gc = gspread.service_account(filename="credenciais.json")
planilha = gc.open_by_url(URL_PLANILHA)
aba = planilha.sheet1

# Conecta na IA
client_gemini = genai.Client(api_key=CHAVE_GEMINI)

# ==========================================
# 2. FUNÇÃO DA IA
# ==========================================
def extrair_dados(mensagem):
    prompt = f"""Analise este gasto: "{mensagem}"
    Responda EXCLUSIVAMENTE em formato JSON com:
    "descricao", "valor" (com ponto decimal) e "categoria" (Alimentação, Transporte, Lazer, Educação, Moradia, Saúde ou Outros).
    Sem markdown, apenas o JSON puro.
    """
    # Mantido o modelo que funcionou para a sua cota
    resposta = client_gemini.models.generate_content(model='gemini-3.8-flash', contents=prompt)
    texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
    return json.loads(texto_limpo)

# ==========================================
# 3. OUVINDO AS MENSAGENS NO TELEGRAM
# ==========================================
@bot.message_handler(func=lambda message: True)
def receber_gasto(mensagem):
    # Avisa que está pensando
    msg_espera = bot.reply_to(mensagem, "⏳ Processando...")
    
    try:
        # Extrai os dados e salva na planilha
        dados = extrair_dados(mensagem.text)
        nova_linha = [datetime.now().strftime("%d/%m/%Y"), dados['descricao'], dados['valor'], dados['categoria']]
        aba.append_row(nova_linha)
        
        # Apaga a mensagem de "Processando" e manda a confirmação final
        bot.delete_message(mensagem.chat.id, msg_espera.message_id)
        resposta_final = f"✅ **Salvo na Planilha!**\n\n🛒 Item: {dados['descricao']}\n💰 Valor: R$ {dados['valor']}\n📂 Categoria: {dados['categoria']}"
        bot.send_message(mensagem.chat.id, resposta_final, parse_mode='Markdown')
        
    except Exception as e:
        bot.edit_message_text(f"❌ Erro ao salvar: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)

# ==========================================
# INICIA O BOT
# ==========================================
print("🤖 Bot rodando! Vá no Telegram e mande uma mensagem para ele.")
bot.infinity_polling()