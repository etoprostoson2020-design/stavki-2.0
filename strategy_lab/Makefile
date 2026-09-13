.PHONY: help migrate slice test api worker lock fmt

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  %-10s %s\n",$$1,$$2}'

migrate:  ## применить миграции
	alembic upgrade head

slice:    ## прогнать первый vertical slice целиком
	python -m scripts.run_slice

test:     ## тесты, включая Red Team
	pytest -q

api:      ## поднять FastAPI
	uvicorn fsl.api.main:app --host 0.0.0.0 --port 8000

worker:   ## поднять Celery worker
	celery -A fsl.worker.celery_app.app worker -l info

lock:     ## пересобрать лок окружения
	python -m scripts.write_lock

validate: ## прогнать валидацию (фаза 6)
	python -m scripts.run_validation

memory:  ## отчёт исследовательской памяти (фаза 7)
	python -m scripts.run_memory
