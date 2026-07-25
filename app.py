# ============================================================================
# RIGELSLM - Interface Web
# Versão: 1.0.0
# ============================================================================
# 
# Esta é a interface web para testar o modelo RigelSLM.
# Utiliza Gradio para criar uma interface simples e responsiva.
#
# Funcionalidades:
#   - Chat interativo (digite uma pergunta, receba resposta)
#   - Ajuste de temperatura, top-k e penalidade de repetição
#   - Carregar prompts de arquivo .txt
#   - Exibir informações do modelo
#   - Download de respostas geradas (via botão de cópia)
# ============================================================================
NOME_MODELO = "RigelSLM"
VERSAO = "1.0.0"

import os
import torch
import gradio as gr
from tokenizers import Tokenizer
from treino import RigelSLM, VOCAB_SIZE, EMBED_DIM, DISPOSITIVO ##, NOME_MODELO, VERSAO

# ============================================================================
# 1. CONFIGURAÇÕES
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKENIZER_PATH = os.path.join(BASE_DIR, "tokenizer", "tokenizer.json")
MODEL_PATH = os.path.join(BASE_DIR, "modelo", "modelo_melhor.pt")  # Prioriza o melhor modelo
MODEL_FALLBACK = os.path.join(BASE_DIR, "modelo", "modelo.pt")

# Parâmetros padrão de geração
TEMPERATURE = 0.7
TOP_K = 40
REPETITION_PENALTY = 1.15
MAX_NEW_TOKENS = 60
MAX_CONTEXT = 256

# ============================================================================
# 2. DETECÇÃO DE VERSÃO DO GRADIO
# ============================================================================

GRADIO_VERSION = gr.__version__
GRADIO_MAJOR = int(GRADIO_VERSION.split('.')[0])
print(f"   📦 Gradio versão {GRADIO_VERSION} (major {GRADIO_MAJOR})")

# ============================================================================
# 3. CARREGAR O MODELO
# ============================================================================

def carregar_modelo():
    """Carrega o tokenizador e o modelo treinado."""
    print("📦 Carregando RigelSLM...")
    
    # Tokenizador
    try:
        tokenizer = Tokenizer.from_file(TOKENIZER_PATH)
        print("   ✅ Tokenizador carregado")
    except Exception as e:
        print(f"   ❌ Erro ao carregar tokenizador: {e}")
        raise
    
    # Modelo
    model = RigelSLM().to(DISPOSITIVO)
    
    # Tenta carregar o melhor modelo, senão o final
    if os.path.exists(MODEL_PATH):
        checkpoint = torch.load(MODEL_PATH, map_location=DISPOSITIVO)
        model.load_state_dict(checkpoint)
        print(f"   ✅ Modelo carregado de {MODEL_PATH}")
    elif os.path.exists(MODEL_FALLBACK):
        checkpoint = torch.load(MODEL_FALLBACK, map_location=DISPOSITIVO)
        model.load_state_dict(checkpoint)
        print(f"   ✅ Modelo carregado de {MODEL_FALLBACK}")
    else:
        print("   ⚠️ Nenhum modelo encontrado! Use os pesos iniciais.")
    
    model.eval()
    print(f"   💻 Dispositivo: {DISPOSITIVO}")
    print(f"   📊 Parâmetros: {sum(p.numel() for p in model.parameters()):,}")
    
    return tokenizer, model

tokenizer, model = carregar_modelo()

# ============================================================================
# 4. FUNÇÃO DE GERAÇÃO (com penalidade de repetição)
# ============================================================================

def gerar_resposta(prompt, 
                   max_new_tokens=MAX_NEW_TOKENS,
                   temperature=TEMPERATURE,
                   top_k=TOP_K,
                   repetition_penalty=REPETITION_PENALTY):
    """
    Gera uma resposta a partir de um prompt.
    Usa temperatura para controlar criatividade e penalidade para evitar repetições.
    """
    # Tokeniza o prompt
    ids = tokenizer.encode(prompt).ids
    tokens = torch.tensor(ids, dtype=torch.long).to(DISPOSITIVO)
    generated = tokens.tolist()
    token_counts = {}

    for _ in range(max_new_tokens):
        # Mantém apenas os últimos MAX_CONTEXT tokens
        if len(generated) > MAX_CONTEXT:
            context = generated[-MAX_CONTEXT:]
        else:
            context = generated

        input_tensor = torch.tensor(context, dtype=torch.long).to(DISPOSITIVO).unsqueeze(0)

        with torch.no_grad():
            output = model(input_tensor)
            logits = output[0, -1, :]  # Pega o último token

        # Aplica penalidade de repetição
        if repetition_penalty != 1.0 and len(generated) > 1:
            for token in set(generated):
                if token in token_counts:
                    if logits[token] > 0:
                        logits[token] /= repetition_penalty
                    else:
                        logits[token] *= repetition_penalty

        # Atualiza contagens
        for token in context:
            token_counts[token] = token_counts.get(token, 0) + 1

        # Aplica temperatura
        if temperature > 0:
            logits = logits / temperature
        else:
            next_token = torch.argmax(logits).item()
            generated.append(next_token)
            break

        # Top-k
        if top_k > 0:
            top_k_vals, top_k_indices = torch.topk(logits, min(top_k, logits.size(-1)))
            mask = torch.ones_like(logits) * float('-inf')
            mask[top_k_indices] = top_k_vals
            logits = mask

        # Amostragem
        probs = torch.softmax(logits, dim=-1)
        next_token = torch.multinomial(probs, num_samples=1).item()
        generated.append(next_token)

    return tokenizer.decode(generated)

# ============================================================================
# 5. FUNÇÃO DE CHAT (chamada pela interface)
# ============================================================================

def chat_resposta(mensagem, historico, temperature, top_k, rep_penalty, max_tokens):
    """
    Função chamada quando o usuário envia uma mensagem.
    Retorna o histórico atualizado no formato de dicionários (role/content).
    """
    # Se não houver histórico, inicia uma lista vazia
    if historico is None:
        historico = []
    
    # Adiciona a mensagem do usuário (formato dicionário)
    historico.append({"role": "user", "content": mensagem})
    
    # Monta o prompt com o histórico (pega as últimas 6 interações)
    prompt_contexto = ""
    for msg in historico[-6:]:
        if msg["role"] == "user":
            prompt_contexto += f"Usuário: {msg['content']}\n"
        else:
            prompt_contexto += f"Assistente: {msg['content']}\n"
    
    prompt = prompt_contexto + "Assistente: "
    
    # Gera a resposta
    try:
        resposta_completa = gerar_resposta(
            prompt,
            max_new_tokens=int(max_tokens),
            temperature=float(temperature),
            top_k=int(top_k),
            repetition_penalty=float(rep_penalty)
        )
        # Extrai apenas a parte gerada
        if "Assistente:" in resposta_completa:
            gerado = resposta_completa.split("Assistente:", 1)[-1].strip()
        else:
            gerado = resposta_completa.strip()
        
        # Adiciona a resposta do assistente
        historico.append({"role": "assistant", "content": gerado})
        return historico, historico
    except Exception as e:
        historico.append({"role": "assistant", "content": f"❌ Erro: {e}"})
        return historico, historico

# ============================================================================
# 6. FUNÇÃO DE CARREGAR PROMPTS
# ============================================================================

def carregar_prompts(arquivo):
    """
    Lê prompts de um arquivo .txt (um por linha) e retorna uma lista.
    """
    if arquivo is None:
        return "Nenhum arquivo selecionado."
    
    try:
        with open(arquivo.name, 'r', encoding='utf-8') as f:
            prompts = [linha.strip() for linha in f if linha.strip()]
        return "\n".join(prompts)
    except Exception as e:
        return f"❌ Erro ao ler arquivo: {e}"

# ============================================================================
# 7. FUNÇÃO PARA GERAR RESPOSTAS EM LOTE
# ============================================================================

def gerar_respostas_lote(prompts_texto, temperature, top_k, rep_penalty, max_tokens):
    """
    Gera respostas para múltiplos prompts.
    """
    if not prompts_texto or prompts_texto.strip() == "":
        return "⚠️ Nenhum prompt para processar."
    
    prompts = [p.strip() for p in prompts_texto.split('\n') if p.strip()]
    resultados = []
    
    for i, prompt in enumerate(prompts, 1):
        try:
            resposta = gerar_resposta(
                prompt,
                max_new_tokens=int(max_tokens),
                temperature=float(temperature),
                top_k=int(top_k),
                repetition_penalty=float(rep_penalty)
            )
            # Extrai a parte gerada
            if prompt in resposta:
                gerado = resposta.split(prompt, 1)[-1].strip()
            else:
                gerado = resposta.strip()
            resultados.append(f"[{i}] {prompt}\n   → {gerado}\n")
        except Exception as e:
            resultados.append(f"[{i}] {prompt}\n   → ❌ Erro: {e}\n")
    
    return "\n".join(resultados)

# ============================================================================
# 8. INTERFACE GRADIO (compatível com múltiplas versões)
# ============================================================================

def criar_interface():
    """Cria a interface web com Gradio, ajustando parâmetros conforme a versão."""
    
    # Informações do modelo
    info_modelo = f"""
    ## 📊 RigelSLM v{VERSAO}
    
    | Característica | Valor |
    | :--- | :--- |
    | **Nome** | {NOME_MODELO} |
    | **Parâmetros** | {sum(p.numel() for p in model.parameters()):,} |
    | **Vocabulário** | {VOCAB_SIZE:,} |
    | **Embedding** | {EMBED_DIM} |
    | **Contexto** | {MAX_CONTEXT} tokens |
    | **Dispositivo** | {DISPOSITIVO} |
    | **Modelo** | {'✅ Carregado' if os.path.exists(MODEL_PATH) or os.path.exists(MODEL_FALLBACK) else '⚠️ Não encontrado'} |
    """
    
    # ===== Configuração do Blocks: theme só no launch() a partir da versão 6 =====
    blocks_kwargs = {"title": f"{NOME_MODELO} - Interface"}
    if GRADIO_MAJOR < 6:
        blocks_kwargs["theme"] = gr.themes.Soft()
    
    with gr.Blocks(**blocks_kwargs) as interface:
        
        gr.Markdown(f"# ⭐ {NOME_MODELO} - Chat")
        gr.Markdown("Modelo de linguagem pequeno treinado com dados brasileiros.")
        
        with gr.Row():
            # Coluna principal (chat)
            with gr.Column(scale=3):
                # Chatbot: tenta com parâmetros adicionais, se falhar, usa o básico
                try:
                    chatbot = gr.Chatbot(label="Conversa", height=450, bubble_full_width=False, show_copy_button=True)
                except TypeError:
                    try:
                        chatbot = gr.Chatbot(label="Conversa", height=450, show_copy_button=True)
                    except TypeError:
                        chatbot = gr.Chatbot(label="Conversa", height=450)
                
                with gr.Row():
                    msg = gr.Textbox(
                        label="Digite sua mensagem",
                        placeholder="Digite algo... (Enter para enviar)",
                        scale=4,
                        container=False
                    )
                    send_btn = gr.Button("Enviar", variant="primary", scale=1)
                
                with gr.Row():
                    clear_btn = gr.Button("🔄 Limpar conversa", variant="secondary")
                    reset_btn = gr.Button("🔁 Resetar parâmetros", variant="secondary")
            
            # Coluna de controles
            with gr.Column(scale=1):
                gr.Markdown(info_modelo)
                
                gr.Markdown("### ⚙️ Parâmetros")
                temp_slider = gr.Slider(
                    minimum=0.1, maximum=2.0, value=TEMPERATURE, step=0.05,
                    label="🌡️ Temperatura", info="Mais alta = mais criativo"
                )
                topk_slider = gr.Slider(
                    minimum=1, maximum=100, value=TOP_K, step=1,
                    label="🔝 Top-K", info="Filtra os K tokens mais prováveis"
                )
                rep_slider = gr.Slider(
                    minimum=1.0, maximum=2.0, value=REPETITION_PENALTY, step=0.05,
                    label="🔁 Penalidade de repetição", info="Evita loops"
                )
                max_tokens_input = gr.Number(
                    value=MAX_NEW_TOKENS, label="📏 Máx. novos tokens", precision=0
                )
                
                gr.Markdown("### 📂 Prompts em lote")
                with gr.Group():
                    file_input = gr.File(
                        label="Carregar .txt (um prompt por linha)",
                        file_types=[".txt"]
                    )
                    lote_btn = gr.Button("📤 Processar lote", variant="secondary")
                
                # Textbox do lote: tenta com show_copy_button, se falhar, usa o básico
                try:
                    lote_output = gr.Textbox(
                        label="Resultado do lote",
                        lines=8,
                        max_lines=12,
                        interactive=False,
                        show_copy_button=True
                    )
                except TypeError:
                    lote_output = gr.Textbox(
                        label="Resultado do lote",
                        lines=8,
                        max_lines=12,
                        interactive=False
                    )
        
        # ===== EVENTOS =====
        
        # Enviar mensagem
        def send_message(msg, hist, temp, topk, rep, max_tok):
            if not msg or not msg.strip():
                return hist, ""
            # hist é uma lista de dicionários (role/content)
            return chat_resposta(msg, hist, temp, topk, rep, max_tok)
        
        send_btn.click(
            send_message,
            inputs=[msg, chatbot, temp_slider, topk_slider, rep_slider, max_tokens_input],
            outputs=[chatbot, msg]
        )
        msg.submit(
            send_message,
            inputs=[msg, chatbot, temp_slider, topk_slider, rep_slider, max_tokens_input],
            outputs=[chatbot, msg]
        )
        
        # Limpar conversa: retorna lista vazia e limpa a caixa de texto
        clear_btn.click(
            lambda: ([], ""),
            outputs=[chatbot, msg]
        )
        
        # Resetar parâmetros
        reset_btn.click(
            lambda: (TEMPERATURE, TOP_K, REPETITION_PENALTY, MAX_NEW_TOKENS),
            outputs=[temp_slider, topk_slider, rep_slider, max_tokens_input]
        )
        
        # Carregar arquivo de prompts
        def carregar_e_exibir(arquivo):
            if arquivo is None:
                return "⚠️ Nenhum arquivo selecionado."
            try:
                with open(arquivo.name, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                return f"❌ Erro ao ler arquivo: {e}"
        
        file_input.change(
            carregar_e_exibir,
            inputs=file_input,
            outputs=lote_output
        )
        
        # Processar lote
        lote_btn.click(
            gerar_respostas_lote,
            inputs=[lote_output, temp_slider, topk_slider, rep_slider, max_tokens_input],
            outputs=lote_output
        )
    
    return interface

# ============================================================================
# 9. PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    interface = criar_interface()
    
    # Monta os parâmetros do launch
    launch_kwargs = {
        "server_name": "127.0.0.1",
        "server_port": 8001,
        "share": False,
        "debug": False,
        "css": ".gradio-container {max-width: 900px; margin: auto;}"
    }
    # Se for Gradio 6+, podemos passar theme no launch
    if GRADIO_MAJOR >= 6:
        launch_kwargs["theme"] = gr.themes.Soft()
    
    interface.launch(**launch_kwargs)