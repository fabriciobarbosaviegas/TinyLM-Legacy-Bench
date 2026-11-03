# Inventário de hardware

Um arquivo YAML por máquina em `hardware/<id>.yaml` (o `<id>` é o nome usado em `data/raw/<id>/`). Atualize o arquivo quando algo mudar (RAM, kernel, sistema) e cite a versão nos protocolos dos experimentos.

| id | Descrição | Estado |
|---|---|---|
| [macmini-1-1](macmini-1-1.yaml) | Mac mini 1,1, Core Duo T2300, 2 GB, Debian 12 i386 | em uso |
| [notebook-i5-1035g1](notebook-i5-1035g1.yaml) | Lenovo IdeaPad S145-15IIL, i5-1035G1, 8 GB | em uso |
| atom-n2600 | Intel Atom N2600 | **planejado** |
| rtx-5090 | GPU NVIDIA RTX 5090 | **planejado** |

Campos de potência (`tdp_w`) são **especificações**, não medidas. Se houver medição (RAPL ou medidor de tomada), registre em `potencia_medida` com método e data.
