# Atalhos do repositório. Requer bash >= 5 e python3. Use `make help`.
PY ?= python3

.PHONY: help test test-unit selftest validate lint tree new-exp figure

help:
	@echo "make test       # unitários + autoteste do pipeline + validação dos dados + lint"
	@echo "make test-unit  # testes unitários"
	@echo "make selftest   # autoteste do pipeline (binários simulados)"
	@echo "make validate   # valida data/raw/"
	@echo "make lint       # sintaxe de shell e python"
	@echo "make new-exp SLUG=meu-experimento TITULO='Título'   # cria experiments/EXP-AAAA-NNN-..."
	@echo "make figure RUN=data/raw/... OUT=reports/figures/x.png"

test: test-unit selftest validate lint
	@echo "== TUDO OK =="

test-unit:
	$(PY) -W ignore::ResourceWarning -m unittest discover -s tests -t . -v

selftest:
	bash pipeline/selftest.sh

validate:
	$(PY) tools/validate_run.py --all --quiet data/raw

lint:
	@for f in $$(find . -name '*.sh' -not -path './.git/*'); do bash -n $$f || exit 1; done
	@$(PY) -m py_compile $$(find . -name '*.py' -not -path './.git/*')
	@if command -v shellcheck >/dev/null; then shellcheck -S warning $$(find . -name '*.sh' -not -path './.git/*') || true; else echo "(shellcheck ausente: pulando)"; fi
	@echo "lint ok"

tree:
	@find . -path ./.git -prune -o -type d -print | sort | sed 's|[^/]*/|  |g'

new-exp:
	@test -n "$(SLUG)" || (echo "uso: make new-exp SLUG=... TITULO='...'"; exit 1)
	tools/new_experiment.sh "$(SLUG)" "$(TITULO)"

figure:
	@test -n "$(RUN)" || (echo "uso: make figure RUN=<pasta> OUT=<png>"; exit 1)
	$(PY) tools/plot_thermal.py "$(RUN)" -o "$(or $(OUT),curva_termica.png)"
