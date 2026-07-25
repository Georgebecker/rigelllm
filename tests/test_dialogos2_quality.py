import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "dialogos2.py"

spec = importlib.util.spec_from_file_location("dialogos2", MODULE_PATH)
dialogos2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dialogos2)


class Dialogos2QualityTests(unittest.TestCase):
    def test_gerar_pergunta_por_categoria_usa_prefixo_e_assunto(self):
        pergunta = dialogos2.gerar_pergunta_por_categoria("pessoa", "Ada Lovelace")
        self.assertIn("Ada Lovelace", pergunta)
        self.assertTrue(pergunta.endswith("?"))
        self.assertTrue(any(prefixo.lower() in pergunta.lower() for prefixo in dialogos2.PREFIXOS_POR_CATEGORIA["pessoa"]))

    def test_gerar_pergunta_por_categoria_para_lugar_é_natural(self):
        pergunta = dialogos2.gerar_pergunta_por_categoria("lugar", "Paris")
        self.assertIn("Paris", pergunta)
        self.assertTrue(pergunta.startswith(("Onde", "Como", "Qual", "Que", "Por", "Quais", "O")))

    def test_prompt_conversa_usa_tema_e_mantém_propriedades(self):
        tema = "música brasileira"
        prompt = dialogos2.gerar_prompt_conversa(tema)

        self.assertIn(tema, prompt)
        self.assertIn("Pessoa 1:", prompt)
        self.assertIn("Pessoa 2:", prompt)
        self.assertIn("NO MÍNIMO 250 palavras", prompt)

    def test_fallback_para_pergunta_resposta_nao_usa_modelo_genérico(self):
        texto, *_ = dialogos2.gerar_fallback("pergunta_resposta", "O que você sabe sobre ecologia?", "ecologia")
        self.assertIn("ecologia", texto.lower())
        self.assertNotIn("o tema ecologia é", texto.lower())

    def test_avaliador_rejeita_resposta_template_genérica(self):
        texto = "O tema ecologia é importante e envolve múltiplos aspectos. Em primeiro lugar, representa o contexto histórico e social, que moldou sua evolução. portanto, é essencial refletir sobre como isso impacta o futuro, contempla a necessidade de ações conscientes."
        valido, motivo = dialogos2.avaliar_qualidade(texto, tipo="pergunta_resposta")
        self.assertFalse(valido)
        self.assertIn("template", motivo)


if __name__ == "__main__":
    unittest.main()
