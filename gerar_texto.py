import torch
from tokenizers import Tokenizer
from treino import MiniGPT, VOCAB_SIZE

TOKENIZER_PATH = "tokenizer/tokenizer.json"
MODEL_PATH = "modelo/modelo.pt"

# carregar
tokenizer = Tokenizer.from_file(TOKENIZER_PATH)

model = MiniGPT()
model.load_state_dict(torch.load(MODEL_PATH))
model.eval()

def gerar_resposta(prompt, max_tokens=20):

    tokens = tokenizer.encode(prompt).ids
    tokens = torch.tensor(tokens)

    for _ in range(max_tokens):
        with torch.no_grad():
            output = model(tokens)

        next_token = torch.argmax(output[-1]).item()
        tokens = torch.cat([tokens, torch.tensor([next_token])])

    return tokenizer.decode(tokens.tolist())

# loop de conversa
while True:
    user = input("Você: ")

    entrada = f"Usuário: {user}\nChatbot:"
    resposta = gerar_resposta(entrada)

    print("Chatbot:", resposta.replace(entrada, "").strip())