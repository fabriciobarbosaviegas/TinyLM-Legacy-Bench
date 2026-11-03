# Modelos

**Os arquivos `.gguf` não entram no Git** (estão no `.gitignore`). Aqui fica apenas o catálogo.

## Catálogo (`manifest.csv`)

Uma linha por modelo/quantização, com o hash e o tamanho **publicados** pela fonte (quando existirem), licença e status (`ativo`, `candidato`, `descartado`). Campos em [`docs/06-dicionario-de-dados.md`](../docs/06-dicionario-de-dados.md).

## Como adicionar um modelo

1. Baixe o arquivo no PC e calcule: `sha256sum arquivo.gguf` e `stat -c %s arquivo.gguf`.
2. Compare com o hash e o tamanho da página do modelo (no Hugging Face, o ponteiro LFS em `raw/<revisão>/<arquivo>` mostra `oid sha256` e `size`).
3. Só então preencha a linha do catálogo, registrando a **revisão** da fonte em `fonte`/`observacoes`, e abra um PR.
4. Envie ao Mac mini por `scp` e confira o hash **lá** também (`docs/07-integridade-dos-modelos.md`).

## Gerar o manifesto do pipeline

```bash
python3 tools/make_pipeline_manifest.py --models-dir /home/gaia/models --status ativo -o models.csv
```

Atenção: com a coluna `sha256` preenchida, o pipeline **pula** o modelo se o arquivo não conferir (`STRICT=1`).

## Licenças

Cada modelo tem a sua licença. Confirme antes de redistribuir resultados derivados e **não** inclua pesos no repositório.
