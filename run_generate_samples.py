import os
import torch
from tokenizers import Tokenizer
from treino import MiniGPT
from datetime import datetime

TOKENIZER_PATH = 'tokenizer/tokenizer.json'
MODEL_PATH = 'modelo/modelo.pt'
SAMPLES_PATH = os.path.join('logs', 'samples.txt')

def gerar_texto(model, tokenizer, prompt, max_tokens=60):
    ids = tokenizer.encode(prompt).ids
    tokens = torch.tensor(ids, dtype=torch.long)
    for _ in range(max_tokens):
        with torch.no_grad():
            out = model(tokens)
        logits = out[-1].float()
        # sampling: temperature + top-k
        temperature = 0.8
        top_k = 50

        if top_k and top_k > 0:
            topk_vals, topk_idx = torch.topk(logits, top_k)
            probs_topk = torch.softmax(topk_vals / temperature, dim=-1)
            next_id = int(topk_idx[torch.multinomial(probs_topk, 1)].item())
        else:
            probs = torch.softmax(logits / temperature, dim=-1)
            next_id = int(torch.multinomial(probs, 1).item())
        tokens = torch.cat([tokens, torch.tensor([next_id], dtype=torch.long)])
    return tokenizer.decode(tokens.tolist())

def main():
    if not os.path.exists(TOKENIZER_PATH):
        print('Tokenizer não encontrado:', TOKENIZER_PATH)
        return
    if not os.path.exists(MODEL_PATH):
        print('Modelo não encontrado:', MODEL_PATH)
        return

    tokenizer = Tokenizer.from_file(TOKENIZER_PATH)
    model = MiniGPT()
    # tentar carregar checkpoint; se incompatível, adaptar pesos parcialmente
    checkpoint = torch.load(MODEL_PATH)
    try:
        model.load_state_dict(checkpoint)
        print('Checkpoint carregado com sucesso (shapes compatíveis).')
    except RuntimeError as e:
        print('Aviso: checkpoint incompatível — adaptando pesos parcialmente:', e)
        new_state = model.state_dict()
        old_state = checkpoint
        for name, old_param in old_state.items():
            if name not in new_state:
                continue
            new_param = new_state[name]
            try:
                if old_param.shape == new_param.shape:
                    new_state[name] = old_param
                else:
                    # copiar a interseção de shapes
                    if old_param.ndim == 2 and new_param.ndim == 2:
                        r = min(old_param.shape[0], new_param.shape[0])
                        c = min(old_param.shape[1], new_param.shape[1])
                        tmp = new_param.clone()
                        tmp[:r, :c] = old_param[:r, :c]
                        new_state[name] = tmp
                    elif old_param.ndim == 1 and new_param.ndim == 1:
                        r = min(old_param.shape[0], new_param.shape[0])
                        tmp = new_param.clone()
                        tmp[:r] = old_param[:r]
                        new_state[name] = tmp
                    else:
                        # formatos não compatíveis — manter inicialização aleatória
                        print(f'  Não foi possível adaptar {name} (shapes {old_param.shape} -> {new_param.shape})')
            except Exception as ex:
                print(f'  Erro ao adaptar {name}: {ex}')

        model.load_state_dict(new_state)
        print('Checkpoint adaptado e carregado (parte dos pesos reutilizados).')

    model.eval()

    prompts = [
        'Hoje eu fui ao parque e',
        'O melhor cuidado para um cachorro é',
        'Como cuidar do pelo do meu pet:',
        'Dicas para alimentar um filhote:',
        'Rotina de banho para cães de pelo longo:',
        'Quais vacinas um cão adulto precisa?'
    ]

    with open(SAMPLES_PATH, 'a', encoding='utf-8') as sf:
        sf.write(f'=== Geração automática {datetime.now()} ===\n')
        for p in prompts:
            gen = gerar_texto(model, tokenizer, p, max_tokens=80)
            cont = gen.replace(p, '').strip()
            sf.write(f'Prompt: {p}\nGeração: {cont}\n\n')
            print('Prompt:', p)
            print('Geração:', cont)
        sf.write('\n')

if __name__ == "__main__":
    main()
