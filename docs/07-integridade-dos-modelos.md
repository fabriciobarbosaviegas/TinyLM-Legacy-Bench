# Integridade dos modelos (sha256)

## Política

1. Todo arquivo `.gguf` do catálogo (`models/manifest.csv`) deve ter **tamanho e sha256 publicados** quando a fonte os fornece (no Hugging Face, na página do arquivo ou no ponteiro LFS `raw/`).
2. O pipeline calcula o sha256 **duas vezes** por modelo antes de medir; o modelo é **pulado** (`STRICT=1`) se o hash for instável ou não conferir com o esperado.
3. Para investigar instabilidade: `DROPCACHE=1` (terceira leitura após limpar o cache de páginas), `memtest86+`, `smartctl -a`, e `llama-gguf-hash` para comparar por tensor entre cópias.
4. Registre o sha256 em todo `meta.txt`. Dados de qualidade (acertos, perplexidade) de um arquivo sem hash verificado devem ser rotulados como tal.

## Registro histórico (em aberto)

Arquivo `qwen2.5-0.5b-instruct-q5_k_m.gguf` no Mac mini (tamanho de 522 186 592 bytes na rodada v3, igual ao publicado):

| Rodada | Script | sha256 registrado |
|---|---|---|
| 2026-10-03 14:51 | v1 | `e21b32bc0d99a4f45e782570250fabb64bf5fcb8e8c25fbbc82b6b97e331c120` |
| 2026-10-03 19:11 | v1 | `0c9f8f784d6fd40fdd7fba5e3131ba7ff0dc76804fb64be194a3168731ab82b8` |
| 2026-10-03 20:01 | v3 (2 leituras iguais) | `2dddab7bdc8df1a9d278196a496113325ade9bfdbe0b449428429124ac40e22d` |
| Publicado (Qwen, revisão 9217f5d) | | `041474553fcabfc2a2d67903f9d2c2e50bd92528e670da4f33b5d0ce6e59fd55` |

Fatos: os três hashes registrados são diferentes entre si e **nenhum** confere com o publicado; o tamanho do arquivo (rodada v3) confere. A data de modificação do arquivo (11:51 do dia 2026-10-03) é anterior às três rodadas.

O que isso pode significar (hipóteses, **não confirmadas**): corrupção intermitente de RAM ou disco (a leitura estável das duas últimas pode refletir o cache de páginas); cópias diferentes do arquivo; erro de transferência. A causa não foi investigada.

Impacto: a velocidade (t/s) provavelmente não depende dos valores dos pesos; resultados de **qualidade** (acertos, perplexidade) obtidos com esse arquivo não têm garantia de integridade. O estudo de hardware vs qualidade depende da resolução disto.

### Tarefas para resolver

- [ ] `sha256sum` do arquivo no PC e comparar com o publicado.
- [ ] No Mac mini: `sha256sum` antes e depois de `echo 3 | sudo tee /proc/sys/vm/drop_caches`.
- [ ] Recopiar o arquivo (`scp`) e calcular o hash logo em seguida.
- [ ] `memtest86+` (uma passada completa) e `sudo smartctl -a /dev/sda`.
- [ ] Se divergir: `llama-gguf-hash` por tensor nas duas cópias.

Enquanto não resolvido, o catálogo marca o Qwen 0.5B Q5_K_M com o hash publicado e o pipeline (`STRICT=1`) vai **pular** esse arquivo. Para medir só velocidade com consciência do risco, rode com `STRICT=0` e registre a ressalva.
