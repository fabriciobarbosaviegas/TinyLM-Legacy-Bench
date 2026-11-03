# Como contribuir

## Fluxo de trabalho

1. **Issue primeiro** para propostas de experimento (modelo `Proposta de experimento`) ou problemas.
2. **Branches** a partir de `main`: `exp/EXP-AAAA-NNN-slug`, `data/<maquina>-<descricao>`, `fix/<assunto>`, `docs/<assunto>`.
3. **Commits** curtos, em português, com prefixo: `feat:` (código), `fix:`, `data:` (dados brutos novos), `exp:` (protocolo/pré-registro), `docs:`, `test:`, `ci:`.
4. **Pull request** com o modelo do repositório. Pelo menos uma pessoa revisa; dados e protocolo pedem revisão de quem **não** coletou.
5. `main` deve estar sempre verde (`make test`).

## Regras que não se negociam

- **Dados brutos são imutáveis** depois do commit (`data/README.md`). Erros viram "Desvios" no README do experimento.
- **Pré-registre antes de coletar** (`experiments/_template/PREREGISTRO.md`). Coleta exploratória é permitida, mas rotulada como tal.
- **Valide toda execução** antes do commit: `python3 tools/validate_run.py <pasta>`.
- **Nunca versione** `.gguf` nem `.kld`.
- **Registre o ambiente**: commit do llama.cpp, build/flags, imagem do contêiner, kernel, governor, temperatura ambiente, sha256 do modelo.
- **Rotule estimativas e hipóteses** como tais (por exemplo, energia estimada por TDP não é consumo).
- Parâmetros térmicos (`TARGET`, `GATE_HS`...) devem ser iguais em rodadas que serão comparadas.

## Rodando localmente

```bash
make test        # unitários + autoteste do pipeline + validação dos dados + lint
make help
```

Requisitos: bash ≥ 5, python3 (biblioteca padrão; `matplotlib` só para figuras), `shellcheck` opcional. O pipeline completo exige o Mac mini com os binários 32 bits (ver `docs/01-ambiente-e-build.md`).

## Estilo

- **Shell:** `set -u`, aspas em variáveis, funções pequenas, comentário de cabeçalho com uso. Rode `shellcheck` quando possível.
- **Python:** só biblioteca padrão no pipeline e nas ferramentas (o Mac mini pode não ter pacotes extras); docstring de módulo com uso.
- **Texto:** português do Brasil, números com vírgula decimal nos relatórios, ponto nos dados e no código.
- **Relatórios:** separar fato, estimativa e hipótese; incluir limitações.

## Como adicionar...

| Para adicionar... | Veja |
|---|---|
| um modelo | `models/README.md` |
| uma máquina | novo `hardware/<id>.yaml` + linha em `hardware/README.md`; dados em `data/raw/<id>/` |
| perguntas | `questions/README.md` (e `CHANGELOG.md`) |
| um experimento | `tools/new_experiment.sh` e `experiments/README.md` |
| uma decisão de projeto | novo ADR em `docs/adr/` a partir de `0000-template.md` |
