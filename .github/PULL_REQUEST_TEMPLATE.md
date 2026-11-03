## O que muda

(2 a 4 linhas)

## Tipo

- [ ] Código (pipeline, tools, build)
- [ ] Dados brutos novos (`data/raw/`)
- [ ] Relatório / documentação
- [ ] Experimento (pasta em `experiments/`)

## Lista de verificação

- [ ] `make test` passa localmente
- [ ] Dados novos validados: `python3 tools/validate_run.py <pasta>` sem FAIL (WARN comentados no README do experimento)
- [ ] **Nenhum dado bruto existente foi editado** (correções vão em "Desvios" do experimento)
- [ ] Nenhum `.gguf` ou `.kld` no commit
- [ ] Hash (sha256) do modelo usado está no `meta.txt` e foi comparado com o publicado, ou o relatório diz que não foi
- [ ] Commit do llama.cpp, build/flags e parâmetros do pipeline estão registrados
- [ ] Estimativas e hipóteses estão rotuladas como tal no texto
- [ ] `CHANGELOG.md` atualizado (se mudou código, protocolo ou perguntas)
- [ ] Experimento pré-registrado **antes** da coleta (ou marcado como exploratório)

## Para os revisores

(O que olhar com mais atenção; dúvidas.)
