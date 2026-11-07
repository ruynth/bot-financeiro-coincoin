import telebot
import gspread
import json
import os
import io
import csv
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
    data_hoje = datetime.now().strftime("%d/%m/%Y")
    
    prompt = f"""Analise os gastos descritos aqui: "{mensagem}"
    Considere que hoje é dia {data_hoje}.
    Pode haver um ou mais gastos na mesma mensagem.
    Responda EXCLUSIVAMENTE em formato JSON contendo uma lista chamada "gastos", onde cada item tem as chaves:
    "data" (formato DD/MM/YYYY. Se não citar quando foi, use a data de hoje),
    "descricao", 
    "valor" (apenas números com ponto decimal), 
    "categoria" (Alimentação, Transporte, Lazer, Educação, Moradia, Saúde ou Outros),
    "pagamento" (Cartão de Débito, Cartão de Crédito, Pix ou Dinheiro).
    
    Exemplo de estrutura de resposta esperada:
    {{"gastos": [
        {{"data": "...", "descricao": "...", "valor": 10.5, "categoria": "...", "pagamento": "..."}},
        {{"data": "...", "descricao": "...", "valor": 50.0, "categoria": "...", "pagamento": "..."}}
    ]}}"""
    
    resposta = client_groq.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="qwen/qwen3.8-27b",
 # Mantenha o modelo que funcionou para você
        temperature=0,
        response_format={"type": "json_object"}
    )
    
    texto_json = resposta.choices[0].message.content
    # Retorna apenas a lista de gastos que está dentro do JSON
    return json.loads(texto_json)["gastos"]

    
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

@bot.message_handler(commands=['zerar'])
@bot.message_handler(commands=['zerar'])

@bot.message_handler(commands=['mes'])
def resumo_mes(mensagem):
    msg_espera = bot.reply_to(mensagem, "📊 Calculando o mês...")
    try:
        # Pega o mês digitado (ex: /mes 11/2026) ou usa o mês atual por padrão
        comando = mensagem.text.split()
        if len(comando) > 1:
            mes_ano_alvo = comando[1]
        else:
            mes_ano_alvo = datetime.now().strftime("%m/%Y")
            
        dados = aba.get_all_values()
        if len(dados) <= 1:
            bot.edit_message_text("Planilha vazia.", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)
            return
            
        resumo_categorias = {}
        total_geral = 0.0
        
        for linha in dados[1:]:
            if len(linha) >= 5:
                data_gasto = linha[0] # Pega a coluna Data (DD/MM/YYYY)
                # Verifica se a data do gasto termina com o mês/ano que queremos
                if data_gasto.endswith(mes_ano_alvo):
                    valor_str = str(linha[2]).replace('R$', '').replace(',', '.').strip()
                    try:
                        valor = float(valor_str)
                    except ValueError:
                        continue
                    categoria = linha[3]
                    resumo_categorias[categoria] = resumo_categorias.get(categoria, 0) + valor
                    total_geral += valor

        if total_geral == 0:
            bot.edit_message_text(f"Nenhum gasto encontrado para {mes_ano_alvo}.", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)
            return

        texto_resposta = f"📊 **Resumo de {mes_ano_alvo}**\n\n"
        for cat, val in resumo_categorias.items():
            texto_resposta += f"📂 {cat}: R$ {val:.2f}\n"
        texto_resposta += f"\n💰 **Total do Mês: R$ {total_geral:.2f}**"
        
        bot.edit_message_text(texto_resposta, chat_id=mensagem.chat.id, message_id=msg_espera.message_id, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Erro: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)

@bot.message_handler(commands=['exportar'])
def exportar_planilha(mensagem):
    msg_espera = bot.reply_to(mensagem, "📁 Gerando arquivo CSV...")
    try:
        comando = mensagem.text.split()
        mes_ano_alvo = comando[1] if len(comando) > 1 else None

        dados = aba.get_all_values()
        if len(dados) <= 1:
            bot.edit_message_text("A planilha está vazia.", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)
            return
            
        # Cria um arquivo CSV na memória do Render
        output = io.StringIO()
        # delimiter=';' ajuda o Excel brasileiro a ler as colunas automaticamente
        writer = csv.writer(output, delimiter=';') 
        writer.writerow(dados[0]) # Escreve o cabeçalho
        
        linhas_exportadas = 0
        for linha in dados[1:]:
            # Se pediu um mês específico, filtra. Se não, salva tudo.
            if mes_ano_alvo:
                if len(linha) > 0 and linha[0].endswith(mes_ano_alvo):
                    writer.writerow(linha)
                    linhas_exportadas += 1
            else:
                writer.writerow(linha)
                linhas_exportadas += 1
                
        if linhas_exportadas == 0:
            bot.edit_message_text("Nenhum dado encontrado para exportar neste filtro.", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)
            return
            
        # Converte o arquivo para um formato que o Telegram aceita enviar
        arquivo_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))
        nome_arquivo = f"gastos_{mes_ano_alvo.replace('/', '_')}.csv" if mes_ano_alvo else "todos_os_gastos.csv"
        arquivo_bytes.name = nome_arquivo
        
        bot.delete_message(mensagem.chat.id, msg_espera.message_id)
        bot.send_document(mensagem.chat.id, arquivo_bytes, caption=f"✅ Relatório gerado com {linhas_exportadas} registros!")
        
    except Exception as e:
        bot.edit_message_text(f"❌ Erro ao exportar: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)




def zerar_planilha(mensagem):
    msg_espera = bot.reply_to(mensagem, "⚠️ Apagando TODOS os registros...")
    try:
        aba.clear()
        # Cabeçalho atualizado com 5 colunas
        aba.append_row(["Data", "Descrição", "Valor", "Categoria", "Pagamento"])
        
        bot.edit_message_text("✅ **Planilha resetada!** Cabeçalho novo criado com sucesso.", chat_id=mensagem.chat.id, message_id=msg_espera.message_id, parse_mode='Markdown')
        
    except Exception as e:
        bot.edit_message_text(f"❌ Erro ao tentar zerar: {e}", chat_id=mensagem.chat.id, message_id=msg_espera.message_id)
        
@bot.message_handler(func=lambda message: True)
@bot.message_handler(func=lambda message: True)

@bot.message_handler(func=lambda message: True)
def receber_gasto(mensagem):
    msg_espera = bot.reply_to(mensagem, "⏳ Processando lançamentos...")
    try:
        # Agora a extração devolve uma lista de gastos
        lista_gastos = extrair_dados(mensagem.text)
        
        linhas_para_inserir = []
        resposta_final = f"✅ **{len(lista_gastos)} lançamento(s) salvo(s)!**\n\n"
        
        for dados in lista_gastos:
            # Puxa os dados de cada gasto individual
            nova_linha = [dados['data'], dados['descricao'], dados['valor'], dados['categoria'], dados['pagamento']]
            linhas_para_inserir.append(nova_linha)
            
            # Monta o texto de confirmação para o Telegram
            resposta_final += f"🛒 {dados['descricao']} | 💰 R$ {dados['valor']}\n"
            resposta_final += f"📅 {dados['data']} | 📂 {dados['categoria']} | 💳 {dados['pagamento']}\n\n"
        
        # O método append_rows (no plural) envia todas as linhas para o Sheets de uma vez só!
        aba.append_rows(linhas_para_inserir)
        
        bot.delete_message(mensagem.chat.id, msg_espera.message_id)
        bot.send_message(mensagem.chat.id, resposta_final.strip(), parse_mode='Markdown')
        
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
