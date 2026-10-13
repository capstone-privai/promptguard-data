ENV ?= staging

run:
	python3 -m payments.app

test:
	python3 -m unittest discover -s tests

deploy:
	@test -n "$$VAULT_TOKEN" || (echo "VAULT_TOKEN is not set" && exit 1)
	@echo "deploying payments-api to $(ENV)"
