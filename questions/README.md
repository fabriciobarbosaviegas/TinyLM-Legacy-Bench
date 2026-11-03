# Perguntas de avaliação

- **Automático (28 perguntas):** `pipeline/questions_pt.jsonl`. Formato: uma linha JSON por pergunta com `id`, `cat`, `q` e `accept` (lista de expressões regulares aplicadas à resposta normalizada: minúsculas, sem acentos).
- **Manual (20 perguntas):** `avaliacao_manual_cli/` (rubrica de 0 a 2 + marcadores, e planilha CSV).

## Como acrescentar perguntas ao conjunto automático

1. Acrescente a linha ao `pipeline/questions_pt.jsonl` com `id` único (prefixos: `f` fatos, `l` local, `a` aritmética, `g` linguagem, `r` raciocínio, `x` abstenção).
2. Escreva os padrões `accept` **sem acentos e em minúsculas**; use `\\b` para números (`"\\b4\\b"` não casa com "14").
3. Rode `make test`: os testes conferem JSON válido, ids únicos e regex compiláveis.
4. Atenção: mudar o conjunto invalida comparações com rodadas anteriores. Registre em `CHANGELOG.md` e use um novo nome de arquivo se a mudança for grande (por exemplo `questions_pt_v2.jsonl`).

Tamanho de amostra: ver `docs/04-avaliacao-de-qualidade.md` (28 perguntas é pouco para ranquear modelos parecidos).
