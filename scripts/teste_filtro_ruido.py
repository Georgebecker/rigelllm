# -*- coding: utf-8 -*-
"""teste_filtro_ruido.py — Testa o filtro de ruído de IA com exemplos reais."""
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from limpeza_leve_rigel_v2 import _tem_ruido_ia

com_ruido = (
    "answer: they asked to write article. But the last message from system: "
    "'Write a article...'. The user gave instructions: 'Write an article of "
    "high quality about...' So we need to output the article. Let's craft "
    "article about stereotype of ideal body."
)
sem_ruido = (
    "O Papel dos Tribunais de Almirantado no Combate ao Trafico Internacional "
    "de Escravos no Seculo XIX. No seculo XIX, o trafico transatlantico de "
    "escravizados foi um dos sistemas mais brutais e lucrativos."
)

print("COM ruido -> detectou?", _tem_ruido_ia(com_ruido))
print("SEM ruido -> detectou?", _tem_ruido_ia(sem_ruido))
